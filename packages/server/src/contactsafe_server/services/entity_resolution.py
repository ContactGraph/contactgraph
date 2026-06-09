"""Alias-based entity resolution for persons and orgs.

Lookup priority (first hit wins): linkedin_url → github_url → email → phone.
On miss: fall back to exact canonical_name match, then create a new entity.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import Org, OrgAlias, Person, PersonAlias
from contactsafe_server.services.phone_normalization import normalize_phone

logger: logging.Logger = logging.getLogger(__name__)

_PERSON_ALIAS_PRIORITY: list[str] = [
    "linkedin_url",
    "github_url",
    "email",
    "phone",
    "bluesky_handle",
    "twitter_handle",
]


def _extract_first_name(canonical_name: str) -> str:
    """Extract the first name (everything before the last whitespace token)."""
    parts: list[str] = canonical_name.strip().split()
    if len(parts) <= 1:
        return canonical_name.strip()
    return " ".join(parts[:-1])


def _extract_last_name(canonical_name: str) -> str:
    """Extract the last name (the last whitespace-separated token)."""
    parts: list[str] = canonical_name.strip().split()
    return parts[-1] if parts else ""


def build_last_name_index(persons: list[Person]) -> dict[str, list[Person]]:
    """Build an in-memory index of persons keyed by lowered last-name token."""
    index: dict[str, list[Person]] = {}
    for person in persons:
        last: str = _extract_last_name(person.canonical_name).lower()
        if last:
            index.setdefault(last, []).append(person)
    return index


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
        self._person_alias_cache: dict[tuple[str, str], uuid.UUID] | None = None
        self._org_alias_cache: dict[tuple[str, str], uuid.UUID] | None = None
        self._person_cache: dict[uuid.UUID, Person] = {}
        self._org_cache: dict[uuid.UUID, Org] = {}

    async def preload_caches(self) -> None:
        """Load all person/org aliases into memory for fast bulk resolution."""
        pa_result = await self._session.execute(select(PersonAlias))
        self._person_alias_cache = {}
        for alias in pa_result.scalars().all():
            key: tuple[str, str] = (alias.kind, alias.value)
            self._person_alias_cache[key] = alias.person_id

        oa_result = await self._session.execute(select(OrgAlias))
        self._org_alias_cache = {}
        for alias in oa_result.scalars().all():
            key = (alias.kind, alias.value)
            self._org_alias_cache[key] = alias.org_id

        p_result = await self._session.execute(select(Person))
        for person in p_result.scalars().all():
            self._person_cache[person.id] = person

        o_result = await self._session.execute(select(Org))
        for org in o_result.scalars().all():
            self._org_cache[org.id] = org

    async def _get_person(self, person_id: uuid.UUID) -> Person | None:
        cached: Person | None = self._person_cache.get(person_id)
        if cached is not None:
            return cached
        result = await self._session.execute(
            select(Person).where(Person.id == person_id),
        )
        person: Person | None = result.scalar_one_or_none()
        if person is not None:
            self._person_cache[person.id] = person
        return person

    async def _get_org(self, org_id: uuid.UUID) -> Org | None:
        cached: Org | None = self._org_cache.get(org_id)
        if cached is not None:
            return cached
        result = await self._session.execute(
            select(Org).where(Org.id == org_id),
        )
        org: Org | None = result.scalar_one_or_none()
        if org is not None:
            self._org_cache[org.id] = org
        return org

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

        Tries strong aliases in priority order; falls back to canonical_name.
        """
        candidates: list[tuple[str, str]] = []
        if linkedin_url:
            candidates.append(("linkedin_url", linkedin_url.lower().rstrip("/")))
        if github_url:
            candidates.append(("github_url", github_url.lower().rstrip("/")))
        for email in emails:
            candidates.append(("email", email.lower().strip()))
        if phone:
            candidates.append(("phone", normalize_phone(phone)))
        if bluesky_handle:
            candidates.append(("bluesky_handle", bluesky_handle.lower().strip()))
        if twitter_handle:
            candidates.append(("twitter_handle", twitter_handle.lower().strip()))

        matched_person: Person | None = None
        for kind, value in candidates:
            if kind == "phone":
                alias = await self._find_phone_alias(value)
            else:
                alias = await self._find_alias(kind, value)
            if alias is not None:
                matched_person = await self._get_person(alias.person_id)
                if matched_person is not None:
                    break

        if matched_person is None and display_name.strip():
            normalized_name: str = display_name.strip().lower()
            name_stmt = (
                select(Person)
                .where(func.lower(Person.canonical_name) == normalized_name)
                .limit(1)
            )
            name_result = await self._session.execute(name_stmt)
            matched_person = name_result.scalar_one_or_none()

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

    async def resolve_linkedin_connection(
        self,
        *,
        linkedin_url: str,
        first_name: str,
        last_name: str,
        email: str | None = None,
        name_index: dict[str, list[Person]] | None = None,
    ) -> Person:
        """Resolver for LinkedIn connections CSV bulk import.

        Priority: linkedin_url alias -> email alias -> name match -> create.
        Name matching uses exact last name + nickname-aware first name.
        """
        display_name: str = f"{first_name} {last_name}".strip() or "Unknown"
        normalized_url: str = linkedin_url.lower().rstrip("/")
        url_alias: PersonAlias | None = await self._find_alias(
            "linkedin_url", normalized_url,
        )
        if url_alias is not None:
            matched: Person | None = await self._get_person(url_alias.person_id)
            if matched is not None:
                return matched

        candidates: list[tuple[str, str]] = [("linkedin_url", normalized_url)]
        matched_person: Person | None = None
        if email:
            normalized_email: str = email.lower().strip()
            candidates.append(("email", normalized_email))
            email_alias: PersonAlias | None = await self._find_alias(
                "email", normalized_email,
            )
            if email_alias is not None:
                matched_person = await self._get_person(email_alias.person_id)

        if matched_person is None and last_name.strip():
            matched_person = self._match_by_name_components(
                first_name, last_name, name_index,
            )

        if matched_person is None:
            primary_email: str | None = email.lower().strip() if email else None
            matched_person = Person(
                canonical_name=display_name,
                primary_email=primary_email,
            )
            self._session.add(matched_person)
            await self._session.flush()
            self._person_cache[matched_person.id] = matched_person

        await self._ensure_aliases(matched_person, candidates)
        return matched_person

    @staticmethod
    def _match_by_name_components(
        first_name: str,
        last_name: str,
        name_index: dict[str, list[Person]] | None,
    ) -> Person | None:
        """Match using exact last name + nickname-aware first name.

        Uses the pre-built name_index keyed by lowered last name token.
        """
        from contactsafe_server.services.nickname_table import first_names_match

        if name_index is None:
            return None

        last_key: str = last_name.strip().lower()
        candidates: list[Person] | None = name_index.get(last_key)
        if not candidates:
            return None

        target_first: str = first_name.strip()
        matches: list[Person] = []
        for person in candidates:
            person_first: str = _extract_first_name(person.canonical_name)
            if first_names_match(target_first, person_first):
                matches.append(person)

        if len(matches) == 1:
            return matches[0]
        return None

    async def _find_alias(self, kind: str, value: str) -> PersonAlias | None:
        if self._person_alias_cache is not None:
            person_id: uuid.UUID | None = self._person_alias_cache.get((kind, value))
            if person_id is None:
                return None
            return PersonAlias(person_id=person_id, kind=kind, value=value)
        stmt = (
            select(PersonAlias)
            .where(PersonAlias.kind == kind, PersonAlias.value == value)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_phone_alias(self, normalized_phone: str) -> PersonAlias | None:
        direct: PersonAlias | None = await self._find_alias("phone", normalized_phone)
        if direct is not None:
            return direct
        if self._person_alias_cache is not None:
            for (kind, value), person_id in self._person_alias_cache.items():
                if kind == "phone" and normalize_phone(value) == normalized_phone:
                    return PersonAlias(person_id=person_id, kind="phone", value=value)
            return None
        stmt = select(PersonAlias).where(PersonAlias.kind == "phone")
        result = await self._session.execute(stmt)
        for alias in result.scalars():
            if normalize_phone(alias.value) == normalized_phone:
                return alias
        return None

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
        normalised: str = (
            normalize_phone(value) if kind == "phone" else value.lower().strip().rstrip("/")
        )
        cache_key: tuple[str, str] = (kind, normalised)

        if self._person_alias_cache is not None:
            existing_id: uuid.UUID | None = self._person_alias_cache.get(cache_key)
            if existing_id is not None:
                if existing_id == person_id:
                    return False
                raise MergeConflict(kind, normalised, existing_id)
            self._person_alias_cache[cache_key] = person_id
            self._session.add(PersonAlias(
                person_id=person_id,
                kind=kind,
                value=normalised,
                confidence=confidence,
            ))
            return True

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
            if self._org_alias_cache is not None:
                org_id: uuid.UUID | None = self._org_alias_cache.get((kind, value))
                if org_id is not None:
                    org_hit: Org | None = await self._get_org(org_id)
                    if org_hit is not None:
                        return org_hit
            else:
                stmt = (
                    select(OrgAlias)
                    .where(OrgAlias.kind == kind, OrgAlias.value == value)
                    .limit(1)
                )
                result = await self._session.execute(stmt)
                alias: OrgAlias | None = result.scalar_one_or_none()
                if alias is not None:
                    org_hit = await self._get_org(alias.org_id)
                    if org_hit is not None:
                        return org_hit

        canonical: str = name or (domain or "Unknown")
        org = Org(
            canonical_name=canonical,
            primary_domain=domain,
        )
        self._session.add(org)
        await self._session.flush()
        self._org_cache[org.id] = org

        for kind, value in candidates:
            self._session.add(OrgAlias(org_id=org.id, kind=kind, value=value))
            if self._org_alias_cache is not None:
                self._org_alias_cache[(kind, value)] = org.id
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
