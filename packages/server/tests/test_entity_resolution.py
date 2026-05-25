"""Tests for EntityResolver — strict merge by email, linkedin_url, github_url."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Base, Org, OrgAlias, Person, PersonAlias
from contactsafe_server.services.entity_resolution import EntityResolver, MergeConflict

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
async def _setup_tables(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_resolve_person_creates_new(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    person = await resolver.resolve_person(
        emails=["alice@example.com"],
        display_name="Alice Smith",
    )
    assert person.id is not None
    assert person.canonical_name == "Alice Smith"
    assert person.primary_email == "alice@example.com"

    result = await db_session.execute(
        select(PersonAlias).where(PersonAlias.person_id == person.id)
    )
    aliases: list[PersonAlias] = list(result.scalars().all())
    emails: list[str] = [a.value for a in aliases if a.kind == "email"]
    assert "alice@example.com" in emails


async def test_resolve_person_returns_existing_by_email(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["bob@example.com"],
        display_name="Bob Jones",
    )
    p2 = await resolver.resolve_person(
        emails=["bob@example.com"],
        display_name="Robert Jones",
    )
    assert p1.id == p2.id


async def test_resolve_person_merges_by_linkedin(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["mchen@gmail.com"],
        display_name="Marcus Chen",
        linkedin_url="https://linkedin.com/in/mchen",
    )
    p2 = await resolver.resolve_person(
        emails=["marcus@horizon.vc"],
        display_name="Marcus Chen",
        linkedin_url="https://linkedin.com/in/mchen",
    )
    assert p1.id == p2.id

    result = await db_session.execute(
        select(PersonAlias).where(PersonAlias.person_id == p1.id, PersonAlias.kind == "email")
    )
    email_values: set[str] = {a.value for a in result.scalars().all()}
    assert "mchen@gmail.com" in email_values
    assert "marcus@horizon.vc" in email_values


async def test_resolve_person_merges_by_github(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["dev@example.com"],
        display_name="Dev User",
        github_url="https://github.com/devuser",
    )
    p2 = await resolver.resolve_person(
        emails=["developer@corp.com"],
        display_name="Dev User",
        github_url="https://github.com/devuser",
    )
    assert p1.id == p2.id


async def test_add_alias_raises_merge_conflict(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(emails=["a@test.com"], display_name="A")
    p2 = await resolver.resolve_person(emails=["b@test.com"], display_name="B")

    await resolver.add_person_alias(
        person_id=p1.id, kind="linkedin_url", value="https://linkedin.com/in/shared"
    )

    with pytest.raises(MergeConflict):
        await resolver.add_person_alias(
            person_id=p2.id, kind="linkedin_url", value="https://linkedin.com/in/shared"
        )


async def test_resolve_org_creates_and_reuses(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    org1 = await resolver.resolve_org(domain="horizon.vc", name="Horizon Ventures")
    org2 = await resolver.resolve_org(domain="horizon.vc")
    assert org1.id == org2.id
    assert org1.canonical_name == "Horizon Ventures"


async def test_resolve_org_by_name_only(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    org1 = await resolver.resolve_org(name="Acme Corp")
    org2 = await resolver.resolve_org(name="Acme Corp")
    assert org1.id == org2.id
