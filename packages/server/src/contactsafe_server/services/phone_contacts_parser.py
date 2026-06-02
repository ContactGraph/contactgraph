"""Parse phone contact uploads (vCard or CSV)."""

from dataclasses import dataclass
import csv
import io
import re


@dataclass(frozen=True, slots=True)
class ParsedPhoneContact:
    display_name: str
    email: str | None = None
    phone: str | None = None


_EMAIL_RE: re.Pattern[str] = re.compile(
    r"EMAIL(?:;[^:]*)*:(?P<value>.+)", re.IGNORECASE
)
_TEL_RE: re.Pattern[str] = re.compile(
    r"TEL(?:;[^:]*)*:(?P<value>.+)", re.IGNORECASE
)
_FN_RE: re.Pattern[str] = re.compile(
    r"FN:(?P<value>.+)", re.IGNORECASE
)
_N_RE: re.Pattern[str] = re.compile(
    r"^N:(?P<value>.+)", re.IGNORECASE | re.MULTILINE
)


def parse_phone_contacts_upload(content: str, filename: str) -> list[ParsedPhoneContact]:
    lowered: str = filename.lower()
    if lowered.endswith(".vcf") or lowered.endswith(".vcard") or "BEGIN:VCARD" in content:
        return _parse_vcard(content)
    return _parse_csv(content)


def _parse_vcard(content: str) -> list[ParsedPhoneContact]:
    cards: list[str] = []
    current: list[str] = []
    for line in content.splitlines():
        if line.strip().upper() == "BEGIN:VCARD":
            current = [line]
            continue
        if line.strip().upper() == "END:VCARD":
            current.append(line)
            cards.append("\n".join(current))
            current = []
            continue
        if current:
            current.append(line)

    contacts: list[ParsedPhoneContact] = []
    for card in cards:
        fn_match = _FN_RE.search(card)
        n_match = _N_RE.search(card)
        display_name: str = (
            fn_match.group("value").strip()
            if fn_match
            else _name_from_n_field(n_match.group("value") if n_match else "")
        )
        email_match = _EMAIL_RE.search(card)
        tel_match = _TEL_RE.search(card)
        email: str | None = (
            email_match.group("value").strip().lower() if email_match else None
        )
        phone: str | None = tel_match.group("value").strip() if tel_match else None
        if not display_name and not email and not phone:
            continue
        if not display_name:
            display_name = email or phone or "Unknown"
        contacts.append(
            ParsedPhoneContact(display_name=display_name, email=email, phone=phone)
        )
    return contacts


def _name_from_n_field(raw: str) -> str:
    parts: list[str] = [p.strip() for p in raw.split(";")]
    family: str = parts[0] if parts else ""
    given: str = parts[1] if len(parts) > 1 else ""
    combined: str = f"{given} {family}".strip()
    return combined or raw.strip()


def _parse_csv(content: str) -> list[ParsedPhoneContact]:
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None:
        return []

    normalized_fields: dict[str, str] = {
        (name or "").strip().lower(): name or ""
        for name in reader.fieldnames
    }

    def field(*candidates: str) -> str | None:
        for candidate in candidates:
            key = candidate.lower()
            if key in normalized_fields:
                return normalized_fields[key]
        return None

    name_col: str | None = field("name", "display name", "full name")
    email_col: str | None = field("email", "e-mail", "email address")
    phone_col: str | None = field("phone", "mobile", "telephone", "phone number")

    contacts: list[ParsedPhoneContact] = []
    for row in reader:
        display_name: str = (row.get(name_col or "", "") or "").strip()
        email_raw: str = (row.get(email_col or "", "") or "").strip().lower()
        phone_raw: str = (row.get(phone_col or "", "") or "").strip()
        email: str | None = email_raw or None
        phone: str | None = phone_raw or None
        if not display_name and not email and not phone:
            continue
        if not display_name:
            display_name = email or phone or "Unknown"
        contacts.append(
            ParsedPhoneContact(display_name=display_name, email=email, phone=phone)
        )
    return contacts
