"""Tests for EntityResolver — strict merge by email, linkedin_url, github_url."""

import logging
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Base, Org, OrgAlias, Person, PersonAlias
from contactsafe_server.services.entity_resolution import EntityResolver, MergeConflict

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


# ---------------------------------------------------------------------------
# New tests — phone, bluesky, twitter alias resolution
# ---------------------------------------------------------------------------


async def test_resolve_person_merges_by_canonical_name(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["heatherehughes@gmail.com"],
        display_name="Heather Hughes",
    )
    p2 = await resolver.resolve_person(
        emails=[],
        display_name="Heather Hughes",
        phone="510-393-4698",
    )
    assert p1.id == p2.id

    result = await db_session.execute(
        select(PersonAlias).where(PersonAlias.person_id == p1.id)
    )
    alias_kinds: set[str] = {alias.kind for alias in result.scalars().all()}
    assert "email" in alias_kinds
    assert "phone" in alias_kinds


async def test_resolve_person_name_match_is_case_insensitive(
    db_session: AsyncSession,
) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["alice@example.com"],
        display_name="Alice Smith",
    )
    p2 = await resolver.resolve_person(
        emails=[],
        display_name="  alice smith  ",
        phone="+14155551234",
    )
    assert p1.id == p2.id


async def test_resolve_person_different_names_remain_separate(
    db_session: AsyncSession,
) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["a@test.com"],
        display_name="Alice Smith",
    )
    p2 = await resolver.resolve_person(
        emails=["b@test.com"],
        display_name="Bob Jones",
    )
    assert p1.id != p2.id


async def test_resolve_person_by_phone(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["phone-user@example.com"],
        display_name="Phone User",
        phone="+14155551234",
    )
    p2 = await resolver.resolve_person(
        emails=["phone-user-alt@example.com"],
        display_name="Phone User",
        phone="+14155551234",
    )
    assert p1.id == p2.id


async def test_resolve_person_by_bluesky(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["sky@example.com"],
        display_name="Sky User",
        bluesky_handle="skyuser.bsky.social",
    )
    p2 = await resolver.resolve_person(
        emails=["sky-alt@example.com"],
        display_name="Sky User",
        bluesky_handle="skyuser.bsky.social",
    )
    assert p1.id == p2.id


async def test_resolve_person_by_twitter(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["twit@example.com"],
        display_name="Twitter User",
        twitter_handle="tweetmaster",
    )
    p2 = await resolver.resolve_person(
        emails=["twit-alt@example.com"],
        display_name="Twitter User",
        twitter_handle="tweetmaster",
    )
    assert p1.id == p2.id


# ---------------------------------------------------------------------------
# Multiple emails stored as aliases
# ---------------------------------------------------------------------------


async def test_resolve_person_multiple_emails_stored(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    person = await resolver.resolve_person(
        emails=["first@example.com", "second@example.com", "third@example.com"],
        display_name="Multi Email",
    )
    result = await db_session.execute(
        select(PersonAlias).where(
            PersonAlias.person_id == person.id, PersonAlias.kind == "email"
        )
    )
    stored_emails: set[str] = {a.value for a in result.scalars().all()}
    assert stored_emails == {"first@example.com", "second@example.com", "third@example.com"}


# ---------------------------------------------------------------------------
# Priority: linkedin > github > email
# ---------------------------------------------------------------------------


async def test_resolve_person_linkedin_takes_priority_over_email(
    db_session: AsyncSession,
) -> None:
    resolver = EntityResolver(db_session)
    person_a = await resolver.resolve_person(
        emails=["a-only@example.com"],
        display_name="Person A",
        linkedin_url="https://linkedin.com/in/priority-person",
    )
    person_b = await resolver.resolve_person(
        emails=["shared@example.com"],
        display_name="Person B",
    )
    # Now resolve with linkedin pointing to A and email pointing to B
    resolved = await resolver.resolve_person(
        emails=["shared@example.com"],
        display_name="Priority Test",
        linkedin_url="https://linkedin.com/in/priority-person",
    )
    assert resolved.id == person_a.id
    assert resolved.id != person_b.id


async def test_resolve_person_github_takes_priority_over_email(
    db_session: AsyncSession,
) -> None:
    resolver = EntityResolver(db_session)
    person_a = await resolver.resolve_person(
        emails=["gh-user@example.com"],
        display_name="GH Person",
        github_url="https://github.com/priority-gh",
    )
    person_b = await resolver.resolve_person(
        emails=["shared-email@example.com"],
        display_name="Email Person",
    )
    resolved = await resolver.resolve_person(
        emails=["shared-email@example.com"],
        display_name="Prio GH",
        github_url="https://github.com/priority-gh",
    )
    assert resolved.id == person_a.id
    assert resolved.id != person_b.id


# ---------------------------------------------------------------------------
# add_person_alias — duplicate on same person returns False
# ---------------------------------------------------------------------------


async def test_add_person_alias_returns_false_when_duplicate(
    db_session: AsyncSession,
) -> None:
    resolver = EntityResolver(db_session)
    person = await resolver.resolve_person(
        emails=["dup@example.com"],
        display_name="Dup Person",
        linkedin_url="https://linkedin.com/in/dup",
    )
    added: bool = await resolver.add_person_alias(
        person_id=person.id,
        kind="linkedin_url",
        value="https://linkedin.com/in/dup",
    )
    assert added is False


# ---------------------------------------------------------------------------
# add_person_alias — normalization (uppercase, trailing slash, whitespace)
# ---------------------------------------------------------------------------


async def test_add_person_alias_normalizes_value(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    person = await resolver.resolve_person(
        emails=["norm@example.com"],
        display_name="Norm Person",
    )
    added: bool = await resolver.add_person_alias(
        person_id=person.id,
        kind="linkedin_url",
        value="  HTTPS://LinkedIn.com/in/NormPerson/  ",
    )
    assert added is True

    # Should detect as duplicate after normalization
    duplicate: bool = await resolver.add_person_alias(
        person_id=person.id,
        kind="linkedin_url",
        value="https://linkedin.com/in/normperson",
    )
    assert duplicate is False


# ---------------------------------------------------------------------------
# resolve_org by linkedin_url
# ---------------------------------------------------------------------------


async def test_resolve_org_by_linkedin_url(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    org1 = await resolver.resolve_org(
        linkedin_url="https://linkedin.com/company/testcorp",
        name="TestCorp",
    )
    org2 = await resolver.resolve_org(
        linkedin_url="https://linkedin.com/company/testcorp",
    )
    assert org1.id == org2.id


# ---------------------------------------------------------------------------
# resolve_org with all three identifiers
# ---------------------------------------------------------------------------


async def test_resolve_org_all_identifiers(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    org = await resolver.resolve_org(
        domain="allthree.io",
        name="All Three Inc",
        linkedin_url="https://linkedin.com/company/allthree",
    )
    result = await db_session.execute(
        select(OrgAlias).where(OrgAlias.org_id == org.id)
    )
    alias_kinds: set[str] = {a.kind for a in result.scalars().all()}
    assert alias_kinds == {"domain", "name", "linkedin_url"}


# ---------------------------------------------------------------------------
# resolve_org creates separate orgs for different domains
# ---------------------------------------------------------------------------


async def test_resolve_org_different_domains_are_separate(
    db_session: AsyncSession,
) -> None:
    resolver = EntityResolver(db_session)
    org_a = await resolver.resolve_org(domain="alpha.com", name="Alpha")
    org_b = await resolver.resolve_org(domain="beta.com", name="Beta")
    assert org_a.id != org_b.id


# ---------------------------------------------------------------------------
# _ensure_aliases skips conflicts silently (logs warning)
# ---------------------------------------------------------------------------


async def test_ensure_aliases_skips_conflicts(db_session: AsyncSession) -> None:
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["owner@example.com"],
        display_name="Owner",
        linkedin_url="https://linkedin.com/in/conflict-alias",
    )
    p2 = await resolver.resolve_person(
        emails=["other@example.com"],
        display_name="Other",
    )
    # Resolve p2 again with linkedin pointing to p1 — should not raise,
    # the conflict is swallowed and p2 is resolved via email.
    resolved = await resolver.resolve_person(
        emails=["other@example.com"],
        display_name="Other",
        linkedin_url="https://linkedin.com/in/conflict-alias",
    )
    # linkedin wins priority, so resolved is actually p1
    assert resolved.id == p1.id
    # But _ensure_aliases is called with emails=["other@example.com"]
    # which belongs to p2 — that conflict is silently skipped


async def test_ensure_aliases_logs_warning_on_conflict(
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify that _ensure_aliases logs a warning when skipping a conflict."""
    resolver = EntityResolver(db_session)
    p1 = await resolver.resolve_person(
        emails=["log-owner@example.com"],
        display_name="Log Owner",
        github_url="https://github.com/log-owner",
    )
    _p2 = await resolver.resolve_person(
        emails=["log-other@example.com"],
        display_name="Log Other",
    )
    # Resolve with github pointing to p1, but email pointing to p2
    with caplog.at_level(logging.WARNING, logger="contactsafe_server.services.entity_resolution"):
        await resolver.resolve_person(
            emails=["log-other@example.com"],
            display_name="Conflict",
            github_url="https://github.com/log-owner",
        )
    assert any("already mapped to another person" in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# MergeConflict exception attributes
# ---------------------------------------------------------------------------


async def test_merge_conflict_attributes() -> None:
    person_id: uuid.UUID = uuid.uuid4()
    exc = MergeConflict(kind="email", value="x@test.com", existing_person_id=person_id)
    assert exc.kind == "email"
    assert exc.value == "x@test.com"
    assert exc.existing_person_id == person_id
    assert "email" in str(exc)
    assert "x@test.com" in str(exc)
    assert str(person_id) in str(exc)
