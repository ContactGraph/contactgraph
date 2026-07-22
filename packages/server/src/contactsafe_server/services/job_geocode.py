"""Offline city geocoding and mechanical location match scoring."""

from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Final

import geonamescache

# Neutral when either side can't be scored.
_NEUTRAL_SCORE: Final[int] = 70
_DEFAULT_COMMUTE_MINUTES: Final[int] = 45
# Rough urban straight-line km per commute minute.
_KM_PER_MINUTE: Final[float] = 1.2

_REMOTE_ONLY_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(remote|anywhere|worldwide|global|work\s+from\s+home|wfh)\s*$",
    re.IGNORECASE,
)
_NON_GEO_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(multiple|various|distributed|flexible|tbd|n/?a|unspecified)\b",
    re.IGNORECASE,
)
_US_STATE_CODES: Final[dict[str, str]] = {
    "al": "AL", "ak": "AK", "az": "AZ", "ar": "AR", "ca": "CA", "co": "CO",
    "ct": "CT", "de": "DE", "fl": "FL", "ga": "GA", "hi": "HI", "id": "ID",
    "il": "IL", "in": "IN", "ia": "IA", "ks": "KS", "ky": "KY", "la": "LA",
    "me": "ME", "md": "MD", "ma": "MA", "mi": "MI", "mn": "MN", "ms": "MS",
    "mo": "MO", "mt": "MT", "ne": "NE", "nv": "NV", "nh": "NH", "nj": "NJ",
    "nm": "NM", "ny": "NY", "nc": "NC", "nd": "ND", "oh": "OH", "ok": "OK",
    "or": "OR", "pa": "PA", "ri": "RI", "sc": "SC", "sd": "SD", "tn": "TN",
    "tx": "TX", "ut": "UT", "vt": "VT", "va": "VA", "wa": "WA", "wv": "WV",
    "wi": "WI", "wy": "WY", "dc": "DC",
}
_US_STATE_NAMES: Final[dict[str, str]] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
_COUNTRY_ALIASES: Final[dict[str, str]] = {
    "usa": "US", "us": "US", "u.s.": "US", "u.s.a.": "US",
    "united states": "US", "united states of america": "US",
    "uk": "GB", "u.k.": "GB", "united kingdom": "GB", "great britain": "GB",
    "england": "GB", "canada": "CA", "australia": "AU", "germany": "DE",
    "france": "FR", "india": "IN", "israel": "IL", "singapore": "SG",
    "netherlands": "NL", "ireland": "IE",
}

# Common metro / region aliases → anchor city.
_METRO_ALIASES: Final[dict[str, str]] = {
    "sf bay area": "San Francisco, CA",
    "san francisco bay area": "San Francisco, CA",
    "bay area": "San Francisco, CA",
    "silicon valley": "San Jose, CA",
    "nyc": "New York City, NY",
    "new york": "New York City, NY",
    "new york city": "New York City, NY",
    "greater seattle area": "Seattle, WA",
    "seattle area": "Seattle, WA",
    "la": "Los Angeles, CA",
    "los angeles area": "Los Angeles, CA",
    "greater boston": "Boston, MA",
    "washington dc": "Washington, DC",
    "washington, d.c.": "Washington, DC",
    "d.c.": "Washington, DC",
}

# City-name aliases when geonames uses a different official name.
_CITY_NAME_ALIASES: Final[dict[str, str]] = {
    "new york": "new york city",
    "nyc": "new york city",
}


@lru_cache(maxsize=1)
def _city_index() -> dict[str, list[dict[str, object]]]:
    """Lowercased city name → list of geonames city dicts (sorted by pop desc)."""
    gc: geonamescache.GeonamesCache = geonamescache.GeonamesCache()
    index: dict[str, list[dict[str, object]]] = {}
    for city in gc.get_cities().values():
        name: str = str(city["name"]).strip().lower()
        index.setdefault(name, []).append(city)
    for cities in index.values():
        cities.sort(key=lambda c: int(c.get("population") or 0), reverse=True)
    return index


def haversine_km(
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
) -> float:
    """Great-circle distance in kilometers."""
    r: float = 6371.0
    phi1: float = math.radians(lat1)
    phi2: float = math.radians(lat2)
    d_phi: float = math.radians(lat2 - lat1)
    d_lambda: float = math.radians(lng2 - lng1)
    a: float = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _normalize_raw(raw: str) -> str:
    text: str = raw.strip()
    text = re.sub(r"\s+", " ", text)
    # Drop trailing "United States" / country noise after metro aliases check.
    return text


def _parse_location_parts(
    raw: str,
) -> tuple[str, str | None, str | None]:
    """Return (city, us_state_code_or_None, country_code_or_None)."""
    text: str = _normalize_raw(raw)
    lower: str = text.lower()

    alias: str | None = _METRO_ALIASES.get(lower)
    if alias is not None:
        text = alias
        lower = alias.lower()

    # Strip leading "Remote -" / "Hybrid -" prefixes.
    text = re.sub(
        r"^(remote|hybrid|onsite|in[\s-]?office)\s*[-–:/]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    lower = text.lower()

    parts: list[str] = [p.strip() for p in re.split(r"[,/|]", text) if p.strip()]
    if not parts:
        return text, None, None

    city: str = parts[0]
    state: str | None = None
    country: str | None = None

    for part in parts[1:]:
        pl: str = part.lower().strip()
        if pl in _US_STATE_CODES:
            state = _US_STATE_CODES[pl]
            country = country or "US"
            continue
        if pl in _US_STATE_NAMES:
            state = _US_STATE_NAMES[pl]
            country = country or "US"
            continue
        if pl in _COUNTRY_ALIASES:
            country = _COUNTRY_ALIASES[pl]
            continue
        # Two-letter country?
        if len(pl) == 2 and pl.isalpha():
            country = pl.upper()

    return city, state, country


def geocode_location(raw: str | None) -> tuple[float, float, str] | None:
    """Resolve a free-text location to (lat, lng, normalized_label) or None."""
    if raw is None:
        return None
    text: str = raw.strip()
    if not text:
        return None
    if _REMOTE_ONLY_RE.match(text):
        return None
    if _NON_GEO_RE.search(text) and "," not in text:
        return None

    city, state, country = _parse_location_parts(text)
    city_key: str = city.strip().lower()
    if not city_key:
        return None
    city_key = _CITY_NAME_ALIASES.get(city_key, city_key)

    candidates: list[dict[str, object]] = list(_city_index().get(city_key, []))
    if not candidates:
        # Try dropping "Area" / "Metro" suffixes.
        stripped: str = re.sub(
            r"\s+(area|metro|metropolitan|region)$",
            "",
            city_key,
        ).strip()
        stripped = _CITY_NAME_ALIASES.get(stripped, stripped)
        candidates = list(_city_index().get(stripped, []))
    if not candidates:
        return None

    filtered: list[dict[str, object]] = candidates
    if country is not None:
        by_country: list[dict[str, object]] = [
            c for c in filtered if str(c.get("countrycode")) == country
        ]
        if by_country:
            filtered = by_country
    if state is not None and country in (None, "US"):
        by_state: list[dict[str, object]] = [
            c
            for c in filtered
            if str(c.get("countrycode")) == "US"
            and str(c.get("admin1code")) == state
        ]
        if by_state:
            filtered = by_state
        elif country is None:
            # Prefer US when a state-like token was present.
            us_only: list[dict[str, object]] = [
                c for c in filtered if str(c.get("countrycode")) == "US"
            ]
            if us_only:
                filtered = us_only

    best: dict[str, object] = filtered[0]
    lat: float = float(best["latitude"])  # type: ignore[arg-type]
    lng: float = float(best["longitude"])  # type: ignore[arg-type]
    name: str = str(best["name"])
    cc: str = str(best.get("countrycode") or "")
    admin: str = str(best.get("admin1code") or "")
    if cc == "US" and admin:
        label: str = f"{name}, {admin}"
    elif cc:
        label = f"{name}, {cc}"
    else:
        label = name
    return lat, lng, label


def _job_is_remote(remote_status: str | None, location: str | None) -> bool:
    status: str = (remote_status or "").strip().lower()
    if status in {"remote", "fully_remote", "fully remote", "work_from_home"}:
        return True
    if status.startswith("remote"):
        return True
    if location and _REMOTE_ONLY_RE.match(location.strip()):
        return True
    return False


def location_match_score(
    *,
    job_lat: float | None,
    job_lng: float | None,
    job_remote_status: str | None,
    job_location: str | None = None,
    user_lat: float | None,
    user_lng: float | None,
    user_pref: str | None,
    commute_max_minutes: int | None,
) -> int:
    """Mechanical 0-100 location match for a user↔job pair."""
    remote_job: bool = _job_is_remote(job_remote_status, job_location)
    pref: str | None = (user_pref or "").strip().lower() or None
    accepts_remote: bool = pref in {None, "remote", "either"} or pref == ""
    requires_remote: bool = pref == "remote"
    requires_in_person: bool = pref == "in_person"

    if remote_job and accepts_remote and not requires_in_person:
        return 100
    if requires_remote and not remote_job:
        return 15
    if remote_job and requires_in_person:
        return 20

    if job_lat is None or job_lng is None or user_lat is None or user_lng is None:
        return _NEUTRAL_SCORE

    max_minutes: int = (
        commute_max_minutes
        if commute_max_minutes is not None and commute_max_minutes > 0
        else _DEFAULT_COMMUTE_MINUTES
    )
    distance_km: float = haversine_km(job_lat, job_lng, user_lat, user_lng)
    est_minutes: float = distance_km / _KM_PER_MINUTE

    if est_minutes <= max_minutes:
        # Within commute: 90–100, closer is better.
        ratio: float = est_minutes / max_minutes if max_minutes > 0 else 0.0
        return max(90, min(100, round(100 - 10 * ratio)))
    if est_minutes <= max_minutes * 1.5:
        return 60
    if est_minutes <= max_minutes * 2.5:
        return 35
    return 15


def location_match_reason(
    *,
    score: int,
    job_lat: float | None,
    job_lng: float | None,
    job_remote_status: str | None,
    job_location: str | None,
    job_location_normalized: str | None,
    user_lat: float | None,
    user_lng: float | None,
    user_pref: str | None,
    commute_max_minutes: int | None,
) -> str:
    remote_job: bool = _job_is_remote(job_remote_status, job_location)
    pref: str | None = (user_pref or "").strip().lower() or None
    if remote_job and score >= 90:
        return "Remote job matches remote preference."
    if pref == "remote" and not remote_job:
        return "Candidate wants remote-only; job is not remote."
    if job_lat is None or job_lng is None or user_lat is None or user_lng is None:
        label: str = job_location_normalized or job_location or "unknown"
        return f"Location incompletely geocoded ({label}); neutral score {score}."
    distance_km: float = haversine_km(job_lat, job_lng, user_lat, user_lng)
    max_minutes: int = (
        commute_max_minutes
        if commute_max_minutes is not None and commute_max_minutes > 0
        else _DEFAULT_COMMUTE_MINUTES
    )
    est_minutes: float = distance_km / _KM_PER_MINUTE
    place: str = job_location_normalized or job_location or "job location"
    return (
        f"~{est_minutes:.0f} min / {distance_km:.0f} km to {place} "
        f"(budget {max_minutes} min)."
    )
