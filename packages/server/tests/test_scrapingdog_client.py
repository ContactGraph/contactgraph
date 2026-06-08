"""Tests for ScrapingDog client helpers."""

from __future__ import annotations

from contactsafe_server.services.scrapingdog_client import (
    extract_linkedin_slug,
    linkedin_profile_url,
    parse_scrapingdog_profile,
)


def test_extract_linkedin_slug_from_full_url() -> None:
    assert extract_linkedin_slug("https://www.linkedin.com/in/jane-doe/") == "jane-doe"


def test_extract_linkedin_slug_from_partial_url() -> None:
    assert extract_linkedin_slug("linkedin.com/in/john-smith") == "john-smith"


def test_parse_scrapingdog_profile_current_role() -> None:
    payload: dict[str, object] = {
        "name": "Jane Doe",
        "headline": "VP Engineering at Acme",
        "location": "San Francisco Bay Area",
        "experience": [
            {
                "company": "Acme Corp",
                "title": "VP Engineering",
                "duration": "Jan 2022 - Present",
            },
            {
                "company": "Old Co",
                "title": "Director",
                "end_date": "2021-12-01",
            },
        ],
    }
    profile = parse_scrapingdog_profile(payload, link_id="jane-doe")
    assert profile.name == "Jane Doe"
    assert profile.current_company == "Acme Corp"
    assert profile.current_title == "VP Engineering"
    assert profile.profile_url == linkedin_profile_url("jane-doe")
    assert len(profile.experiences) == 2
    assert profile.experiences[0].is_current is True
