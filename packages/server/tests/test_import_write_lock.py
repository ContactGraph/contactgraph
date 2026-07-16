import uuid

from contactsafe_server.services.import_write_lock import user_import_lock_keys


def test_user_import_lock_keys_are_stable() -> None:
    user_id: uuid.UUID = uuid.UUID("a47e4469-1bf4-4fae-836b-83e06c81ce31")
    assert user_import_lock_keys(user_id) == user_import_lock_keys(user_id)


def test_user_import_lock_keys_use_namespace() -> None:
    user_id: uuid.UUID = uuid.UUID("00000000-0000-4000-8000-000000000001")
    namespace, key2 = user_import_lock_keys(user_id)
    assert namespace == 0x635F_0001
    assert 0 <= key2 < 2**31
