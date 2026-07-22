"""Tests for offline geocoding and mechanical location matching."""

from __future__ import annotations

from contactsafe_server.services.job_geocode import (
    geocode_location,
    haversine_km,
    location_match_score,
)


def test_geocode_san_francisco_ca() -> None:
    result = geocode_location("San Francisco, CA")
    assert result is not None
    lat, lng, label = result
    assert 37.0 < lat < 38.5
    assert -123.0 < lng < -122.0
    assert "San Francisco" in label
    assert "CA" in label


def test_geocode_bay_area_alias() -> None:
    result = geocode_location("SF Bay Area")
    assert result is not None
    lat, _lng, _label = result
    assert 37.0 < lat < 38.5


def test_geocode_remote_returns_none() -> None:
    assert geocode_location("Remote") is None
    assert geocode_location("Worldwide") is None
    assert geocode_location("") is None
    assert geocode_location(None) is None
    # "Remote - US" has a country token but no city → unresolvable.
    assert geocode_location("Remote - US") is None


def test_geocode_new_york() -> None:
    result = geocode_location("New York, NY, United States")
    assert result is not None
    lat, lng, label = result
    assert 40.0 < lat < 41.5
    assert -75.0 < lng < -73.0
    assert "New York" in label


def test_haversine_sf_to_sj() -> None:
    sf = geocode_location("San Francisco, CA")
    sj = geocode_location("San Jose, CA")
    assert sf is not None and sj is not None
    dist: float = haversine_km(sf[0], sf[1], sj[0], sj[1])
    assert 40.0 < dist < 80.0


def test_location_match_remote_job_remote_pref() -> None:
    assert (
        location_match_score(
            job_lat=None,
            job_lng=None,
            job_remote_status="remote",
            user_lat=37.7,
            user_lng=-122.4,
            user_pref="remote",
            commute_max_minutes=45,
        )
        == 100
    )


def test_location_match_remote_only_rejects_onsite() -> None:
    assert (
        location_match_score(
            job_lat=37.7,
            job_lng=-122.4,
            job_remote_status="onsite",
            user_lat=37.7,
            user_lng=-122.4,
            user_pref="remote",
            commute_max_minutes=45,
        )
        == 15
    )


def test_location_match_nearby_commute() -> None:
    sf = geocode_location("San Francisco, CA")
    assert sf is not None
    score: int = location_match_score(
        job_lat=sf[0],
        job_lng=sf[1],
        job_remote_status="onsite",
        user_lat=sf[0],
        user_lng=sf[1],
        user_pref="in_person",
        commute_max_minutes=45,
    )
    assert score >= 90


def test_location_match_far_away() -> None:
    sf = geocode_location("San Francisco, CA")
    nyc = geocode_location("New York, NY")
    assert sf is not None and nyc is not None
    score: int = location_match_score(
        job_lat=nyc[0],
        job_lng=nyc[1],
        job_remote_status="onsite",
        user_lat=sf[0],
        user_lng=sf[1],
        user_pref="in_person",
        commute_max_minutes=45,
    )
    assert score == 15


def test_location_match_unknown_neutral() -> None:
    assert (
        location_match_score(
            job_lat=None,
            job_lng=None,
            job_remote_status="onsite",
            user_lat=None,
            user_lng=None,
            user_pref="in_person",
            commute_max_minutes=45,
        )
        == 70
    )
