import json

from contactsafe_server.services.org_industry_taxonomy import (
    infer_industry_tags_from_text,
    normalize_industry_tags,
    parse_structured_company_summary,
    select_primary_industry_tag,
)
from contactsafe_server.services.org_enrichment_service import parse_org_enrichment_hits
from contactsafe_server.services.web_search_types import WebSearchHit


def test_normalize_industry_tags_accepts_naics_codes_and_aliases() -> None:
    tags: list[str] = normalize_industry_tags(
        ["51", "technology", "venture_capital", "naics:51", "invalid"],
        max_tags=10,
    )
    assert tags == ["naics:51", "venture_capital"]


def test_select_primary_industry_tag_prefers_naics_over_nonprofit() -> None:
    tags: list[str] = select_primary_industry_tag(["nonprofit", "naics:51"])
    assert tags == ["naics:51"]


def test_select_primary_industry_tag_returns_single_tag() -> None:
    tags: list[str] = select_primary_industry_tag(["naics:51", "naics:52", "legal"])
    assert tags == ["naics:51"]


def test_parse_structured_company_summary_reads_json_payload() -> None:
    payload: str = json.dumps(
        {
            "description": "Acme builds enterprise software for finance teams.",
            "industries": ["naics:51", "naics:52"],
        }
    )
    structured = parse_structured_company_summary(payload)
    assert structured is not None
    assert structured.description is not None
    assert "Acme builds" in structured.description
    assert structured.industries == ("naics:51",)


def test_infer_industry_tags_from_text_detects_healthcare_for_hospital() -> None:
    tags: list[str] = infer_industry_tags_from_text(
        "Regional nonprofit hospital network providing healthcare services."
    )
    assert tags == ["naics:62"]


def test_infer_industry_tags_from_text_does_not_tag_adobe_as_nonprofit() -> None:
    tags: list[str] = infer_industry_tags_from_text(
        "Adobe Inc. is a software company. The Adobe Foundation supports creativity."
    )
    assert tags == ["naics:51"]
    assert "nonprofit" not in tags


def test_parse_org_enrichment_hits_extracts_industry_tags() -> None:
    summary_payload: str = json.dumps(
        {
            "description": "Acme Corp builds enterprise widgets for global customers.",
            "industries": ["naics:31"],
        }
    )
    company_hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Acme Corp - Official Site",
            url="https://www.acme.com/about",
            text="Acme Corp is a leading widget company.",
            highlights=[],
            summary=summary_payload,
        ),
    ]

    parsed = parse_org_enrichment_hits(
        company_name="Acme Corp",
        company_hits=company_hits,
        careers_hits=[],
    )

    assert parsed.categories == ["naics:31"]
