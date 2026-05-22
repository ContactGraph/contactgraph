from contactsafe_server.services.category_inference import infer_categories_from_contact


def test_vc_from_ventures_domain() -> None:
    cats = infer_categories_from_contact(
        email="jane@acmeventures.com",
        display_name="Jane Doe",
        org_name="Acme Ventures",
    )
    assert "vc" in cats


def test_vc_from_pitch_outbound_count() -> None:
    cats = infer_categories_from_contact(
        email="partner@randomfirm.com",
        display_name="Alex Kim",
        org_name="Random Firm",
        pitch_outbound_count=2,
    )
    assert "vc" in cats


def test_vc_not_from_generic_gmail() -> None:
    cats = infer_categories_from_contact(
        email="jane@gmail.com",
        display_name="Jane Doe",
        org_name=None,
    )
    assert "vc" not in cats
