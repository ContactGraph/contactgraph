from contactsafe_server.db.models import Person
from contactsafe_server.services.exa_client import ExaSearchHit, _build_person_query, _parse_results
from contactsafe_server.services.exa_enrichment import (
    apply_exa_hints_to_person,
    extract_hints_from_exa_hits,
)


def test_build_person_query_includes_domain() -> None:
    query: str = _build_person_query("Jane Doe", "jane@acmeventures.com", "Acme Ventures")
    assert "Jane Doe" in query
    assert "acmeventures.com" in query
    assert "investor" in query


def test_parse_exa_results() -> None:
    data: dict[str, object] = {
        "results": [
            {
                "title": "Jane Doe - General Partner - Acme Ventures",
                "url": "https://linkedin.com/in/janedoe",
                "text": "Jane Doe is a General Partner at Acme Ventures.",
                "highlights": ["venture capital investor"],
            }
        ]
    }
    hits = _parse_results(data)
    assert len(hits) == 1
    assert hits[0].title.startswith("Jane Doe")
    assert "venture capital" in hits[0].highlights[0]


def test_extract_vc_hints_from_exa_hits() -> None:
    hits: list[ExaSearchHit] = [
        ExaSearchHit(
            title="Jane Doe - General Partner - Acme Ventures | LinkedIn",
            url="https://linkedin.com/in/janedoe",
            text="Jane Doe is a General Partner at Acme Ventures, a seed-stage venture capital firm.",
            highlights=["venture capital investor focused on enterprise software"],
        )
    ]
    hints = extract_hints_from_exa_hits(
        hits=hits,
        email="jane@acmeventures.com",
        display_name="Jane Doe",
        org_hint=None,
    )
    assert "vc" in hints.categories
    assert hints.current_role == "General Partner"
    assert hints.org_name == "Acme Ventures"


def test_apply_exa_hints_respects_domain_derived_org() -> None:
    person = Person(
        user_id=__import__("uuid").uuid4(),
        canonical_name="Santo",
        email_addresses=["santo@sparkcapital.com"],
        current_org_name="Spark Capital",
        inferred_categories=[],
    )
    apply_exa_hints_to_person(
        person,
        extract_hints_from_exa_hits(
            hits=[
                ExaSearchHit(
                    title="Santo - Partner - Bloomberg Markets",
                    url="https://example.com",
                    text="Santo at Bloomberg Markets",
                    highlights=[],
                )
            ],
            email="santo@sparkcapital.com",
            display_name="Santo",
            org_hint="Spark Capital",
        ),
    )
    assert person.current_org_name == "Spark Capital"
