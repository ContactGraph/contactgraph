from contactsafe_server.services.org_search import (
    email_matches_org_terms,
    expand_org_search_terms,
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
