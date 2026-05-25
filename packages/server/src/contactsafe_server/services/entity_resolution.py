"""Strict alias-based entity resolution for persons and orgs.

Lookup priority (first hit wins): linkedin_url → github_url → email → phone.
On miss: create a new entity and insert all provided aliases.
Never merges on name alone — that's the LLM merger's job (Phase 2).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Org, OrgAlias, Person, PersonAlias

logger: logging.Logger = logging.getLogger(__name__)

_PERSON_ALIAS_PRIORITY: list[str] = [
    "linkedin_url",
    "github_url",
    "email",
    "phone",
    "bluesky_handle",
    "twitter_handle",
]


class MergeConflict(Exception):
    """Raised when an alias is already mapped to a different entity."""

    def __init__(self, kind: str, value: str, existing_person_id: uuid.UUID) -> None:
        self.kind: str = kind
        self.value: str = value
        self.existing_person_id: uuid.UUID = existing_person_id
        super().__init__(f"Alias {kind}={value} already belongs to person {existing_person_id}")


class EntityResolver:
    def __init__(self, session: AsyncSession) -> None:
        self._session: AsyncSession = session

    async def resolve_person(
        self,
        *,
        emails: list[str],
        display_name: str,
        linkedin_url: str | None = None,
        github_url: str | None = None,
        phone: str | None = None,
        bluesky_handle: str | None = None,
        twitter_handle: str | None = None,
    ) -> Person:
        """Return an existing person or create a new one.

        Tries strong aliases in priority order; first hit wins.
        """
        candidates: list[tuple[str, str]] = []
        if linkedin_url:
            candidates.append(("linkedin_url", linkedin_url.lower().rstrip("/")))
        if github_url:
            candidates.append(("github_url", github_url.lower().rstrip("/")))
        for email in emails:
            candidates.append(("email", email.lower().strip()))
        if phone:
            candidates.append(("phone", phone.strip()))
        if bluesky_handle:
            candidates.append(("bluesky_handle", bluesky_handle.lower().strip()))
        if twitter_handle:
            candidates.append(("twitter_handle", twitter_handle.lower().strip()))

        matched_person: Person | None = None
        for kind, value in candidates:
            stmt = (
                select(PersonAlias)
                .where(PersonAlias.kind == kind, PersonAlias.value == value)
                .limit(1)
            )
            result = await self._session.execute(stmt)
            alias: PersonAlias | None = result.scalar_one_or_none()
            if alias is not None:
                person_stmt = select(Person).where(Person.id == alias.person_id)
                person_result = await self._session.execute(person_stmt)
                matched_person = person_result.scalar_one()
                break

        if matched_person is None:
            primary_email: str | None = emails[0].lower().strip() if emails else None
            matched_person = Person(
                canonical_name=display_name,
                primary_email=primary_email,
            )
            self._session.add(matched_person)
            await self._session.flush()

        await self._ensure_aliases(matched_person, candidates)
        return matched_person

    async def add_person_alias(
        self,
        *,
        person_id: uuid.UUID,
        kind: str,
        value: str,
        confidence: float = 0.9,
    ) -> bool:
        """Try to add an alias. Returns True if added, False if it already exists
        on this person. Raises MergeConflict if mapped to a different person."""
        normalised: str = value.lower().strip().rstrip("/")
        stmt = (
            select(PersonAlias)
            .where(PersonAlias.kind == kind, PersonAlias.value == normalised)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        existing: PersonAlias | None = result.scalar_one_or_none()
        if existing is not None:
            if existing.person_id == person_id:
                return False
            raise MergeConflict(kind, normalised, existing.person_id)

        self._session.add(PersonAlias(
            person_id=person_id,
            kind=kind,
            value=normalised,
            confidence=confidence,
        ))
        await self._session.flush()
        return True

    async def resolve_org(
        self,
        *,
        domain: str | None = None,
        name: str | None = None,
        linkedin_url: str | None = None,
    ) -> Org:
        """Return an existing org or create a new one."""
        candidates: list[tuple[str, str]] = []
        if linkedin_url:
            candidates.append(("linkedin_url", linkedin_url.lower().rstrip("/")))
        if domain:
            candidates.append(("domain", domain.lower().strip()))
        if name:
            candidates.append(("name", name.lower().strip()))

        for kind, value in candidates:
            stmt = (
                select(OrgAlias)
                .where(OrgAlias.kind == kind, OrgAlias.value == value)
                .limit(1)
            )
            result = await self._session.execute(stmt)
            alias: OrgAlias | None = result.scalar_one_or_none()
            if alias is not None:
                org_stmt = select(Org).where(Org.id == alias.org_id)
                org_result = await self._session.execute(org_stmt)
                return org_result.scalar_one()

        canonical: str = name or (domain or "Unknown")
        org = Org(
            canonical_name=canonical,
            primary_domain=domain,
        )
        self._session.add(org)
        await self._session.flush()

        for kind, value in candidates:
            self._session.add(OrgAlias(org_id=org.id, kind=kind, value=value))
        await self._session.flush()
        return org

    async def _ensure_aliases(
        self,
        person: Person,
        candidates: list[tuple[str, str]],
    ) -> None:
        """Insert any missing aliases for a person, skip conflicts."""
        for kind, value in candidates:
            try:
                await self.add_person_alias(
                    person_id=person.id,
                    kind=kind,
                    value=value,
                )
            except MergeConflict:
                logger.warning(
                    "Skipping alias %s=%s — already mapped to another person",
                    kind,
                    value,
                )
