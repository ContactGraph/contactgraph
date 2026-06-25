"""Tests for linkedin_profile_parser.py — PDF text extraction and heuristic parsing."""

from __future__ import annotations

import base64
import io
from datetime import date

import pytest
from pypdf import PdfWriter

from contactsafe_server.config import Settings, get_settings
from contactsafe_server.services.linkedin_profile_parser import (
    ParsedEducation,
    ParsedExperience,
    ParsedLinkedInProfile,
    _heuristic_parse,
    _parse_month_year,
    select_recent_experiences,
    suggest_ideal_roles_text,
)


def _settings_without_llm() -> Settings:
    return get_settings().model_copy(update={"openai_api_key": None})


def _make_pdf(text: str) -> str:
    """Create a minimal 1-page PDF with the given text, return base64."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Subject": "test"})

    buf = io.BytesIO()
    writer.write(buf)
    return base64.b64encode(buf.getvalue()).decode()


def test_parse_month_year_full() -> None:
    result: date | None = _parse_month_year("Jan 2020")
    assert result == date(2020, 1, 1)


def test_parse_month_year_long() -> None:
    result: date | None = _parse_month_year("September 2019")
    assert result == date(2019, 9, 1)


def test_parse_month_year_year_only() -> None:
    result: date | None = _parse_month_year("2023")
    assert result == date(2023, 1, 1)


def test_parse_month_year_invalid() -> None:
    assert _parse_month_year("hello world") is None


def test_heuristic_parse_header() -> None:
    text: str = (
        "John Smith\n"
        "VP Engineering at Acme Corp\n"
        "San Francisco Bay Area\n\n"
        "Experience\n"
        "VP Engineering\n"
        "Acme Corp\n"
        "Jan 2020 - Present\n\n"
        "Software Engineer\n"
        "StartupCo\n"
        "Jun 2017 - Dec 2019\n\n"
        "Education\n"
        "Stanford University\n"
        "BS, Computer Science\n"
        "2013 - 2017\n\n"
        "Skills\n"
        "Python · Java · Machine Learning\n"
    )

    result: ParsedLinkedInProfile = _heuristic_parse(text)

    assert result.name == "John Smith"
    assert result.headline == "VP Engineering at Acme Corp"
    assert len(result.experiences) >= 1
    assert result.experiences[0].company == "Acme Corp"
    assert result.experiences[0].is_current is True
    assert len(result.education) >= 1
    assert result.education[0].school == "Stanford University"
    assert "Python" in result.skills


def test_heuristic_parse_no_sections() -> None:
    text: str = "Just a name\nAnd a headline\n"
    result: ParsedLinkedInProfile = _heuristic_parse(text)
    assert result.experiences == []
    assert result.education == []


def test_heuristic_parse_linkedin_company_first_format() -> None:
    text: str = (
        "Jane Doe\nEngineer\n\n"
        "Experience\n"
        "BigCo · Full-time\n"
        "Senior Engineer\n"
        "Mar 2021 - Present\n"
        "San Francisco, CA\n\n"
        "BigCo · Full-time\n"
        "Engineer\n"
        "Jan 2018 - Feb 2021\n"
    )
    result: ParsedLinkedInProfile = _heuristic_parse(text)
    assert len(result.experiences) == 2
    assert result.experiences[0].company == "BigCo"
    assert result.experiences[0].title == "Senior Engineer"
    assert result.experiences[1].title == "Engineer"


def test_select_recent_experiences_orders_current_first() -> None:
    experiences: list[ParsedExperience] = [
        ParsedExperience(company="Old", title="Junior", start_date=date(2015, 1, 1)),
        ParsedExperience(company="Now", title="Lead", is_current=True),
        ParsedExperience(company="Mid", title="Senior", start_date=date(2019, 1, 1)),
    ]
    ordered: list[ParsedExperience] = select_recent_experiences(experiences, limit=2)
    assert [exp.company for exp in ordered] == ["Now", "Mid"]


@pytest.mark.asyncio
async def test_suggest_ideal_roles_heuristic_without_llm() -> None:
    profile = ParsedLinkedInProfile(
        experiences=[
            ParsedExperience(company="Acme", title="Staff Engineer", is_current=True),
        ],
        education=[ParsedEducation(school="MIT", field_of_study="Computer Science")],
    )
    suggestion: str | None = await suggest_ideal_roles_text(
        profile, _settings_without_llm()
    )
    assert suggestion is not None
    assert "Staff Engineer" in suggestion
    assert "Computer Science" in suggestion


@pytest.mark.asyncio
async def test_suggest_ideal_roles_returns_none_for_empty_profile() -> None:
    suggestion: str | None = await suggest_ideal_roles_text(
        ParsedLinkedInProfile(), _settings_without_llm()
    )
    assert suggestion is None


def test_heuristic_parse_experience_dates() -> None:
    text: str = (
        "Jane Doe\nEngineer\n\n"
        "Experience\n"
        "Senior Engineer\n"
        "BigCo\n"
        "Mar 2021 - Present\n"
        "San Francisco, CA\n"
    )
    result: ParsedLinkedInProfile = _heuristic_parse(text)
    assert len(result.experiences) >= 1
    exp = result.experiences[0]
    assert exp.company == "BigCo"
    assert exp.start_date == date(2021, 3, 1)
    assert exp.is_current is True
    assert exp.end_date is None
