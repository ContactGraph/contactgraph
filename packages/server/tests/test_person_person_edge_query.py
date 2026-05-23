from contactsafe_server.services.network_query_service import _is_cooccurrence_relationship_query


def test_is_cooccurrence_relationship_query_true() -> None:
    assert _is_cooccurrence_relationship_query(["cooccurrence"])
    assert _is_cooccurrence_relationship_query(["introduced"])


def test_is_cooccurrence_relationship_query_false() -> None:
    assert not _is_cooccurrence_relationship_query(["investor", "colleague"])
