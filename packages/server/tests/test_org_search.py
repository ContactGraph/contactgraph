from contactsafe_server.services.org_search import (
    email_matches_org_terms,
    expand_org_search_terms,
    is_automation_domain,
    is_automation_or_generic_domain,
    is_non_company_domain,
    is_placeholder_org_name,
    normalize_org_name_key,
    org_name_from_domain,
    org_name_from_email,
)


def test_org_name_from_email_vc_domain() -> None:
    assert org_name_from_email("kenji@horizon.vc") == "Horizon VC"
    assert org_name_from_email("alice@novaworks.com") == "Novaworks"
    assert org_name_from_email("bob@gmail.com") is None


def test_expand_org_search_terms_horizon_vc() -> None:
    terms: list[str] = expand_org_search_terms("Horizon VC")
    assert "horizon vc" in terms
    assert "horizonvc" in terms
    assert "horizon.vc" in terms
    assert "horizon" in terms
    assert "vc" in terms


def test_email_matches_org_terms() -> None:
    terms: list[str] = expand_org_search_terms("Horizon VC")
    assert email_matches_org_terms("kenji@horizon.vc", terms)
    assert not email_matches_org_terms("alice@gmail.com", terms)


def test_automation_domain_skips_org_name() -> None:
    assert is_automation_domain("noreply.github.com") is True
    assert org_name_from_email("ci@noreply.github.com") is None
    assert org_name_from_email("priya@northlight.io") == "Northlight"


def test_generic_consumer_domains_skip_org_name() -> None:
    assert org_name_from_email("sofia@gmail.com") is None
    assert org_name_from_email("diego@mac.com") is None


def test_known_brand_domain_overrides_label_guess() -> None:
    assert org_name_from_email("hello@theinformation.com") is None
    assert org_name_from_email("editor@theinformation.com") is None
    assert org_name_from_email("elena@theinformation.com") == "The Information"


def test_broadcast_local_part_skips_org_name() -> None:
    assert org_name_from_email("info@wayfair.com") is None


# ---------------------------------------------------------------------------
# Non-company domain detection (.gov, .edu, .mil, etc.)
# ---------------------------------------------------------------------------


def test_gov_domain_is_non_company() -> None:
    assert is_non_company_domain("cityofmillvalley.ca.gov") is True
    assert is_non_company_domain("whitehouse.gov") is True
    assert is_non_company_domain("irs.gov") is True


def test_edu_domain_is_non_company() -> None:
    assert is_non_company_domain("stanford.edu") is True
    assert is_non_company_domain("cs.stanford.edu") is True


def test_mil_domain_is_non_company() -> None:
    assert is_non_company_domain("army.mil") is True


def test_normal_company_domain_is_not_non_company() -> None:
    assert is_non_company_domain("acme.com") is False
    assert is_non_company_domain("horizon.vc") is False
    assert is_non_company_domain("northlight.io") is False


def test_gov_edu_blocked_in_automation_or_generic() -> None:
    assert is_automation_or_generic_domain("stanford.edu") is True
    assert is_automation_or_generic_domain("whitehouse.gov") is True
    assert is_automation_or_generic_domain("acme.com") is False


def test_org_name_from_email_gov_edu_returns_none() -> None:
    assert org_name_from_email("planning@cityofmillvalley.ca.gov") is None
    assert org_name_from_email("prof@stanford.edu") is None


def test_normalize_org_name_key_collapses_punctuation() -> None:
    assert normalize_org_name_key("Acme, Inc.") == "acme inc"
    assert normalize_org_name_key("Self-Employed") == "self employed"


def test_is_placeholder_org_name() -> None:
    assert is_placeholder_org_name("Self Employed") is True
    assert is_placeholder_org_name("self-employed") is True
    assert is_placeholder_org_name("Stealth Startup") is True
    assert is_placeholder_org_name("Stealth Mode AI") is True
    assert is_placeholder_org_name("Freelance") is True
    assert is_placeholder_org_name("Horizon Ventures") is False


def test_org_name_from_domain() -> None:
    assert org_name_from_domain("horizon.vc") == "Horizon VC"
    assert org_name_from_domain("gmail.com") is None
