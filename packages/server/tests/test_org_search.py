from contactsafe_server.services.org_search import (
    email_matches_org_terms,
    expand_org_search_terms,
    is_automation_domain,
    org_name_from_email,
)


def test_org_name_from_email_vc_domain() -> None:
    assert org_name_from_email("danny@sticker.vc") == "Sticker VC"
    assert org_name_from_email("alice@aix.com") == "Aix"
    assert org_name_from_email("bob@gmail.com") is None


def test_expand_org_search_terms_sticker_vc() -> None:
    terms: list[str] = expand_org_search_terms("Sticker VC")
    assert "sticker vc" in terms
    assert "stickervc" in terms
    assert "sticker.vc" in terms
    assert "sticker" in terms
    assert "vc" in terms


def test_email_matches_org_terms() -> None:
    terms: list[str] = expand_org_search_terms("Sticker VC")
    assert email_matches_org_terms("danny@sticker.vc", terms)
    assert not email_matches_org_terms("alice@gmail.com", terms)


def test_automation_domain_skips_org_name() -> None:
    assert is_automation_domain("noreply.github.com") is True
    assert org_name_from_email("ci@noreply.github.com") is None
    assert org_name_from_email("vincent@basebase.com") == "Basebase"


def test_generic_consumer_domains_skip_org_name() -> None:
    assert org_name_from_email("reed@gmail.com") is None
    assert org_name_from_email("heather@mac.com") is None


def test_known_brand_domain_overrides_label_guess() -> None:
    assert org_name_from_email("hello@theinformation.com") is None
    assert org_name_from_email("editor@theinformation.com") is None
    assert org_name_from_email("jessica@theinformation.com") == "The Information"


def test_broadcast_local_part_skips_org_name() -> None:
    assert org_name_from_email("info@wayfair.com") is None
