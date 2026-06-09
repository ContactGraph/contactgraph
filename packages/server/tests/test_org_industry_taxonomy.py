import json

from contactsafe_server.services.org_industry_taxonomy import (
    infer_industry_tags_from_text,
    normalize_industry_tags,
    parse_structured_company_summary,
)
from contactsafe_server.services.org_enrichment_service import parse_org_enrichment_hits
from contactsafe_server.services.web_search_types import WebSearchHit


def test_normalize_industry_tags_accepts_naics_codes_and_aliases() -> None:
    tags: list[str] = normalize_industry_tags(
        ["51", "technology", "venture_capital", "naics:51", "invalid"]
    )
    assert tags == ["naics:51", "venture_capital"]


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
    assert structured.industries == ("naics:51", "naics:52")


def test_infer_industry_tags_from_text_detects_healthcare_and_nonprofit() -> None:
    tags: list[str] = infer_industry_tags_from_text(
        "Regional nonprofit hospital network providing healthcare services."
    )
    assert "naics:62" in tags
    assert "nonprofit" in tags


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
