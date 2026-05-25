import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import get_settings
from contactsafe_server.db.models import Person, PersonEdge, User
from contactsafe_server.services.email_parse import ContactAccumulator
from contactsafe_server.services.ingest_enrichment_service import IngestEnrichmentService
from contactsafe_server.services.person_discovery_service import PersonDiscoveryResult
from contactsafe_server.services.platform_activity import PlatformPost
from contactsafe_server.services.web_search_types import WebSearchHit


@pytest.mark.asyncio
async def test_ingest_web_enrichment_tags_investor(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXA_API_KEY", "exa-test-key")
    get_settings.cache_clear()
    settings = get_settings()

    user = User(email=f"exa-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    person = Person(
        user_id=user.id,
        canonical_name="Jane Doe",
        email_addresses=["jane@acmeventures.com"],
        last_seen_in_email=datetime.now(tz=UTC),
    )
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        PersonEdge(
            user_id=user.id,
            person_id=person.id,
            tie_strength_score=0.95,
            is_broadcast=False,
            is_automated=False,
        )
    )
    await db_session.flush()

    mock_hits: list[WebSearchHit] = [
        WebSearchHit(
            title="Jane Doe - General Partner - Acme Ventures",
            url="https://linkedin.com/in/janedoe",
            text="Jane Doe is a General Partner at Acme Ventures, a venture capital firm.",
            highlights=["venture capital investor"],
            provider="exa",
        )
    ]
    mock_discovery = PersonDiscoveryResult(
        employer_hits=mock_hits,
        activity_hits=[],
        posts=[],
        providers_used=["exa:people"],
    )

    mock_discover = AsyncMock(return_value=mock_discovery)
    with patch(
        "contactsafe_server.services.ingest_enrichment_service.PersonDiscoveryService.discover_person",
        mock_discover,
    ):
        acc = ContactAccumulator(email="jane@acmeventures.com", display_name="Jane Doe")
        await IngestEnrichmentService(db_session, settings).enrich_after_import(
            user_id=user.id,
            contact_by_email={"jane@acmeventures.com": acc},
        )

    await db_session.refresh(person)
    assert "vc" in person.inferred_categories
    assert person.current_role == "General Partner"
    assert person.current_org_name == "Acmeventures"
    mock_discover.assert_awaited_once()


@pytest.mark.asyncio
async def test_enrich_after_import_skips_automated_without_lazy_load(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXA_API_KEY", "exa-test-key")
    get_settings.cache_clear()
    settings = get_settings()

    user = User(email=f"auto-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    person = Person(
        user_id=user.id,
        canonical_name="GitHub",
        email_addresses=["notifications@github.com"],
        last_seen_in_email=datetime.now(tz=UTC),
    )
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        PersonEdge(
            user_id=user.id,
            person_id=person.id,
            tie_strength_score=0.05,
            is_broadcast=False,
            is_automated=True,
        )
    )
    await db_session.flush()

    mock_discover = AsyncMock(return_value=PersonDiscoveryResult([], [], [], []))
    with patch(
        "contactsafe_server.services.ingest_enrichment_service.PersonDiscoveryService.discover_person",
        mock_discover,
    ):
        acc = ContactAccumulator(email="notifications@github.com", display_name="GitHub")
        await IngestEnrichmentService(db_session, settings).enrich_after_import(
            user_id=user.id,
            contact_by_email={"notifications@github.com": acc},
        )

    await db_session.refresh(person)
    assert person.inferred_categories == []
    assert person.current_role is None
    mock_discover.assert_not_awaited()


@pytest.mark.asyncio
async def test_signature_enrichment_from_inbound_snippets(
    db_session: AsyncSession,
) -> None:
    get_settings.cache_clear()
    settings = get_settings()

    user = User(email=f"sig-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    person = Person(
        user_id=user.id,
        canonical_name="Sam Rivera",
        email_addresses=["sam@example.com"],
        last_seen_in_email=datetime.now(tz=UTC),
    )
    db_session.add(person)
    await db_session.flush()
    db_session.add(
        PersonEdge(
            user_id=user.id,
            person_id=person.id,
            tie_strength_score=0.8,
            is_broadcast=False,
            is_automated=False,
        )
    )
    await db_session.flush()

    acc = ContactAccumulator(
        email="sam@example.com",
        display_name="Sam Rivera",
        inbound_snippets=[
            "Thanks for the intro.\nSam Rivera\nGeneral Partner at Horizon Capital\n415-555-0100",
        ],
    )
    await IngestEnrichmentService(db_session, settings).enrich_after_import(
        user_id=user.id,
        contact_by_email={"sam@example.com": acc},
    )

    await db_session.refresh(person)
    assert person.current_role == "General Partner"
    assert person.current_org_name == "Horizon Capital"
    assert person.phone_numbers
