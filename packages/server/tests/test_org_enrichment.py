from contactsafe_server.services.org_enrichment import (
    has_domain_derived_org,
    is_rejected_org_name,
    org_names_equivalent,
    should_apply_enrichment_org,
)


def test_domain_derived_org_blocks_enrichment_overwrite() -> None:
    assert has_domain_derived_org("fatima@sparkcapital.com") is True
    assert (
        should_apply_enrichment_org(
            primary_email="fatima@sparkcapital.com",
            proposed_org="Bloomberg Markets",
        )
        is False
    )


def test_generic_domain_allows_enrichment_org() -> None:
    assert (
        should_apply_enrichment_org(
            primary_email="jane@gmail.com",
            proposed_org="Acme Ventures",
        )
        is True
    )


def test_rejects_consumer_provider_org_labels() -> None:
    assert is_rejected_org_name("Gmail") is True
    assert is_rejected_org_name("Mac") is True
    assert is_rejected_org_name("Repository") is True


def test_org_names_equivalent_strips_suffixes() -> None:
    assert org_names_equivalent("Northlight", "Northlight.io") is True
    assert org_names_equivalent("Northlight AI", "Northlight") is True
