from contactsafe_server.services.org_enrichment_service import (
    _pick_description,
    _summarize_description,
    parse_org_enrichment_hits,
)
from contactsafe_server.services.web_search_types import WebSearchHit


def test_summarize_description_strips_exa_ellipsis_markers() -> None:
    raw: str = (
        "Effortlessly scrape and control any site with inexpensive and scalable "
        "AI-powered cloud browsers [...] Enjoy the ease of running a massive fleet."
    )
    summary: str = _summarize_description(raw)
    assert "[...]" not in summary
    assert summary.endswith("…") or summary.endswith(".")
    assert "Enjoy the ease" in summary or "Effortlessly scrape" in summary


def test_summarize_description_prefers_sentences_over_markdown() -> None:
    raw: str = (
        "Basebase: Multiplayer AI [...] # Multiplayer AI in Slack.\n"
        "## Your team and Basebase, right in Slack\n"
        "One channel for your team and your AI agents."
    )
    summary: str = _summarize_description(raw)
    assert "#" not in summary
    assert "[...]" not in summary
    assert "Slack" in summary


def test_pick_description_prefers_exa_summary() -> None:
    hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Basebase",
            url="https://basebase.com",
            text=(
                "# Multiplayer AI in Slack.\n"
                "## Your team and Basebase, right in Slack\n"
                "One channel for your team and your AI agents."
            ),
            highlights=[
                "Basebase: Multiplayer AI [...] # Multiplayer AI in Slack. [...] Ask. Automate."
            ],
            summary=(
                "Basebase brings multiplayer AI into Slack so teams can ask questions, "
                "automate workflows, and collaborate in one place."
            ),
        ),
    ]
    description: str | None = _pick_description(hits, "Basebase")
    assert description is not None
    assert "[...]" not in description
    assert "#" not in description
    assert "Slack" in description
    assert "automate workflows" in description


def test_pick_description_falls_back_to_clean_page_text() -> None:
    hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Basebase",
            url="https://basebase.com",
            text=(
                "Basebase brings multiplayer AI into Slack. "
                "Your team can ask questions, automate workflows, and collaborate in one place."
            ),
            highlights=[
                "Basebase: Multiplayer AI [...] # Multiplayer AI in Slack. [...] Ask. Automate."
            ],
        ),
    ]
    description: str | None = _pick_description(hits, "Basebase")
    assert description is not None
    assert "[...]" not in description
    assert "#" not in description
    assert "Slack" in description


def test_parse_org_enrichment_hits_extracts_company_fields() -> None:
    company_hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Acme Corp | LinkedIn",
            url="https://www.linkedin.com/company/acme-corp",
            text="Acme Corp builds widgets for enterprise customers.",
            highlights=["Acme Corp builds widgets for enterprise customers."],
        ),
        WebSearchHit(
            title="Acme Corp - Official Site",
            url="https://www.acme.com/about",
            text="Acme Corp is a leading widget company.",
            highlights=[],
        ),
    ]
    careers_hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Careers at Acme",
            url="https://www.acme.com/careers",
            text="Join Acme Corp.",
            highlights=[],
        ),
    ]
    description_hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Acme Corp",
            url="https://www.acme.com",
            text="",
            highlights=[],
            summary="Acme Corp builds enterprise widgets for global customers.",
        ),
    ]

    parsed = parse_org_enrichment_hits(
        company_name="Acme Corp",
        company_hits=company_hits,
        careers_hits=careers_hits,
        description_hits=description_hits,
    )

    assert parsed.linkedin_url == "https://www.linkedin.com/company/acme-corp"
    assert parsed.careers_url == "https://www.acme.com/careers"
    assert parsed.primary_domain == "acme.com"
    assert parsed.description is not None
    assert "Acme Corp" in parsed.description
