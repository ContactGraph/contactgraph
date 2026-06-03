from contactsafe_server.services.web_hit_verification import verify_web_hits
from contactsafe_server.services.web_search_types import WebSearchHit


def test_verify_skips_employment_for_generic_email_without_anchors() -> None:
    hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Heather Hughes - Partner - Wrong VC",
            url="https://linkedin.com/in/wrong-heather",
            text="Venture capital investor in New York",
            highlights=[],
            provider="exa",
        )
    ]
    verified = verify_web_hits(
        hits=hits,
        email="heather@gmail.com",
        display_name="Heather Hughes",
        org_hint=None,
        known_linkedin_url=None,
        social_profiles={"linkedin": "https://linkedin.com/in/wrong-heather"},
    )
    assert verified.skip_employment is True
    assert verified.skip_categories is True
    assert verified.employer_hits == []


def test_verify_accepts_linkedin_url_match() -> None:
    known_url: str = "https://www.linkedin.com/in/heather-hughes-sf"
    hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Heather Hughes",
            url=known_url,
            text="Works at Example Co",
            highlights=[],
            provider="exa",
        )
    ]
    verified = verify_web_hits(
        hits=hits,
        email="heather@gmail.com",
        display_name="Heather Hughes",
        org_hint=None,
        known_linkedin_url=known_url,
        social_profiles={"linkedin": known_url},
    )
    assert verified.skip_employment is False
    assert verified.confidence >= 0.85
    assert len(verified.employer_hits) == 1


def test_verify_rejects_conflicting_linkedin_profile() -> None:
    hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Heather Hughes",
            url="https://linkedin.com/in/different-heather",
            text="Investor",
            highlights=[],
            provider="exa",
        )
    ]
    verified = verify_web_hits(
        hits=hits,
        email="heather@gmail.com",
        display_name="Heather Hughes",
        org_hint=None,
        known_linkedin_url="https://linkedin.com/in/my-heather",
        social_profiles={},
    )
    assert verified.skip_employment is True
    assert verified.employer_hits == []


def test_verify_work_email_domain_is_anchor() -> None:
    hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Jane Doe at Acme",
            url="https://acme.com/team/jane",
            text="Jane Doe leads product at Acme Corp",
            highlights=[],
            provider="exa",
        )
    ]
    verified = verify_web_hits(
        hits=hits,
        email="jane@acme.com",
        display_name="Jane Doe",
        org_hint=None,
        known_linkedin_url=None,
        social_profiles={},
    )
    assert verified.skip_employment is False
    assert len(verified.employer_hits) == 1
