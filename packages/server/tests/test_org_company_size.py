from contactsafe_server.services.org_company_size import (
    headcount_to_linkedin_band,
    linkedin_size_band_label,
    normalize_linkedin_size_band,
)
from contactsafe_server.services.org_enrichment_service import parse_org_enrichment_hits
from contactsafe_server.services.web_search_types import WebSearchHit


def test_headcount_to_linkedin_band() -> None:
    assert headcount_to_linkedin_band(1) == "1-10"
    assert headcount_to_linkedin_band(10) == "1-10"
    assert headcount_to_linkedin_band(11) == "11-50"
    assert headcount_to_linkedin_band(200) == "51-200"
    assert headcount_to_linkedin_band(500) == "201-500"
    assert headcount_to_linkedin_band(1000) == "501-1000"
    assert headcount_to_linkedin_band(5000) == "1001-5000"
    assert headcount_to_linkedin_band(10000) == "5001-10000"
    assert headcount_to_linkedin_band(10001) == "10001+"
    assert headcount_to_linkedin_band(250_000) == "10001+"


def test_normalize_linkedin_size_band() -> None:
    assert normalize_linkedin_size_band("1001-5000") == "1001-5000"
    assert normalize_linkedin_size_band("1001–5000") == "1001-5000"
    assert normalize_linkedin_size_band("10001+ employees") == "10001+"
    assert normalize_linkedin_size_band("unknown") is None


def test_linkedin_size_band_label() -> None:
    assert linkedin_size_band_label("51-200") == "51–200 employees"
    assert linkedin_size_band_label(None) == "—"


def test_parse_org_enrichment_hits_uses_exa_employee_count() -> None:
    company_hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Acme Corp",
            url="https://www.acme.com",
            text="Acme Corp builds widgets.",
            highlights=[],
            employee_count=420,
        ),
    ]

    parsed = parse_org_enrichment_hits(
        company_name="Acme Corp",
        company_hits=company_hits,
        careers_hits=[],
    )

    assert parsed.employee_count == 420
    assert parsed.company_size_band == "201-500"


def test_parse_org_enrichment_hits_uses_structured_size_band() -> None:
    company_hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Acme Corp",
            url="https://www.acme.com",
            text="Acme Corp builds widgets.",
            highlights=[],
            summary='{"description":"Acme builds widgets.","industries":["naics:51"],"company_size_band":"1001-5000","funding_stage":"series_b"}',
        ),
    ]

    parsed = parse_org_enrichment_hits(
        company_name="Acme Corp",
        company_hits=company_hits,
        careers_hits=[],
    )

    assert parsed.employee_count is None
    assert parsed.company_size_band == "1001-5000"
    assert parsed.funding_stage == "series_b"
