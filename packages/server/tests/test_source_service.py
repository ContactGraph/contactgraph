import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import SourceConnectionStatus, SourceType, SyncState
from contactsafe_server.services.source_service import SourceService
from contactsafe_server.utils import parse_connect_session_id, parse_source_id


def test_parse_connect_session_id_json() -> None:
    session_id = uuid.uuid4()
    raw = json.dumps({"session_id": str(session_id)})
    assert parse_connect_session_id(raw) == session_id


def test_parse_source_id_json() -> None:
    source_id = uuid.uuid4()
    raw = json.dumps({"source_id": str(source_id)})
    assert parse_source_id(raw) == source_id


@pytest.mark.asyncio
async def test_ensure_google_mail_source(db_session: AsyncSession) -> None:
    from contactsafe_server.db.models import User

    user = User(email="test@example.com")
    db_session.add(user)
    await db_session.flush()

    service = SourceService(db_session)
    source = await service.ensure_google_mail_source(user.id, user.email)
    await db_session.commit()

    assert source.source_type == SourceType.GOOGLE_MAIL.value
    assert source.external_account_id == "test@example.com"
    assert source.connection_status == SourceConnectionStatus.CONNECTED.value
    assert source.sync_state == SyncState.PENDING.value

    again = await service.ensure_google_mail_source(user.id, user.email)
    assert again.id == source.id
