"""Recomputes derived columns on ``Person`` from claims.

Called at the end of each enrichment batch to keep person rows in sync
with the append-only claim tables.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from sqlalchemy import bindparam, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings, get_settings
from contactsafe_server.db.models import (
    EmploymentClaim,
    Person,
    PersonAlias,
    PersonAttributeClaim,
    UserPersonObservation,
)
from contactsafe_server.services.category_inference import infer_categories_from_contact
from contactsafe_server.services.phone_normalization import normalize_phone
from contactsafe_server.services.employment_ranking import (
    employment_recency_window_days,
    normalize_employment_claims,
)

logger: logging.Logger = logging.getLogger(__name__)

# PostgreSQL exposes ``current_role`` as a session function; never persist it.
_INVALID_ROLE_VALUES: frozenset[str] = frozenset({"postgres", "contactsafe"})

_STRIP_QUOTE_RE: re.Pattern[str] = re.compile(
    r"""^[\s'"'\u2018\u2019\u201c\u201d]+|[\s'"'\u2018\u2019\u201c\u201d]+$"""
)


def sanitize_display_name(name: str) -> str:
    """Strip stray quote characters and whitespace from a display name."""
    return _STRIP_QUOTE_RE.sub("", name)


class PersonProfileRecompute:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session: AsyncSession = session
        self._settings: Settings = settings or get_settings()
        self._recency_days: int = employment_recency_window_days(
            configured_days=self._settings.employment_recency_days,
        )
        self._emp_cache: dict[uuid.UUID, list[EmploymentClaim]] = {}
        self._attr_cache: dict[uuid.UUID, list[PersonAttributeClaim]] = {}
        self._phone_alias_cache: dict[uuid.UUID, list[str]] = {}
        self._interaction_cache: dict[uuid.UUID, datetime | None] = {}
        self._person_cache: dict[uuid.UUID, Person] = {}
        self._org_name_cache: dict[uuid.UUID, str] = {}
        self._preloaded: bool = False

    async def recompute_for_user(self, user_id: uuid.UUID) -> int:
        """Recompute derived person columns for every person observed by *user_id*.

        Returns the number of persons updated.
        """
        obs_stmt = select(UserPersonObservation.person_id).where(
            UserPersonObservation.user_id == user_id,
        )
        result = await self._session.execute(obs_stmt)
        person_ids: list[uuid.UUID] = list(result.scalars().all())
        if not person_ids:
            return 0

        await self._bulk_preload(person_ids)

        count: int = 0
        for pid in person_ids:
            await self._recompute_person(pid)
            count += 1

        logger.info("Recomputed %d person profiles for user %s", count, user_id)
        return count

    async def _bulk_preload(self, person_ids: list[uuid.UUID]) -> None:
        """Pre-load all data needed for recompute into in-memory caches."""
        from contactsafe_server.db.models import Org

        emp_result = await self._session.execute(
            select(EmploymentClaim).where(EmploymentClaim.person_id.in_(person_ids)),
        )
        for claim in emp_result.scalars().all():
            self._emp_cache.setdefault(claim.person_id, []).append(claim)

        attr_result = await self._session.execute(
            select(PersonAttributeClaim).where(PersonAttributeClaim.person_id.in_(person_ids)),
        )
        for attr in attr_result.scalars().all():
            self._attr_cache.setdefault(attr.person_id, []).append(attr)

        alias_result = await self._session.execute(
            select(PersonAlias).where(
                PersonAlias.person_id.in_(person_ids),
                PersonAlias.kind == "phone",
            ),
        )
        for alias in alias_result.scalars().all():
            self._phone_alias_cache.setdefault(alias.person_id, []).append(alias.value)

        interaction_stmt = (
            select(
                UserPersonObservation.person_id,
                func.max(UserPersonObservation.last_genuine_interaction_at),
            )
            .where(UserPersonObservation.person_id.in_(person_ids))
            .group_by(UserPersonObservation.person_id)
        )
        interaction_result = await self._session.execute(interaction_stmt)
        for row in interaction_result:
            self._interaction_cache[row[0]] = row[1]

        person_result = await self._session.execute(
            select(Person).where(Person.id.in_(person_ids)),
        )
        for person in person_result.scalars().all():
            self._person_cache[person.id] = person

        org_ids: set[uuid.UUID] = set()
        for claims in self._emp_cache.values():
            for c in claims:
                if c.org_id:
                    org_ids.add(c.org_id)
        if org_ids:
            org_result = await self._session.execute(
                select(Org.id, Org.canonical_name).where(Org.id.in_(org_ids)),
            )
            for row in org_result:
                self._org_name_cache[row[0]] = row[1]

        self._preloaded = True

    async def recompute_persons(self, person_ids: list[uuid.UUID]) -> int:
        """Recompute derived columns for a specific set of person IDs."""
        if not self._preloaded:
            await self._bulk_preload(person_ids)
        count: int = 0
        for pid in person_ids:
            await self._recompute_person(pid)
            count += 1
        return count

    async def _recompute_person(self, person_id: uuid.UUID) -> None:
        all_claims: list[EmploymentClaim] = self._emp_cache.get(person_id, [])

        last_interaction: datetime | None = self._interaction_cache.get(person_id)
        best_emp: EmploymentClaim | None = normalize_employment_claims(
            all_claims,
            last_genuine_interaction_at=last_interaction,
            recency_days=self._recency_days,
        )

        current_org_id: uuid.UUID | None = best_emp.org_id if best_emp else None
        current_org_name: str | None = None
        current_role: str | None = best_emp.role_title if best_emp else None
        if current_role is not None and current_role.strip().lower() in _INVALID_ROLE_VALUES:
            current_role = None

        if best_emp and best_emp.org_id:
            current_org_name = self._org_name_cache.get(best_emp.org_id)

        attrs: list[PersonAttributeClaim] = self._attr_cache.get(person_id, [])

        social_profiles: dict[str, str] = {}
        categories: list[str] = []
        descriptive_tags: list[str] = []
        bio_summary: str | None = None
        location: str | None = None
        claim_phones: list[str] = []

        best_bio_len: int = 0
        for attr in attrs:
            if attr.kind.startswith("social_profile."):
                platform: str = attr.kind.removeprefix("social_profile.")
                social_profiles[platform] = attr.value
            elif attr.kind == "category":
                if attr.value not in categories:
                    categories.append(attr.value)
            elif attr.kind == "descriptive_tag":
                if attr.value not in descriptive_tags:
                    descriptive_tags.append(attr.value)
            elif attr.kind == "bio_summary":
                if len(attr.value) > best_bio_len:
                    bio_summary = attr.value
                    best_bio_len = len(attr.value)
            elif attr.kind == "location":
                location = attr.value
            elif attr.kind == "phone":
                if attr.value not in claim_phones:
                    claim_phones.append(attr.value)

        person_row: Person | None = self._person_cache.get(person_id)
        seen_phones: set[str] = set()
        phone_numbers: list[str] = []
        for raw_phone in [
            *(person_row.phone_numbers or [] if person_row is not None else []),
            *self._phone_alias_cache.get(person_id, []),
            *claim_phones,
        ]:
            normalized: str = normalize_phone(raw_phone)
            if normalized not in seen_phones:
                seen_phones.add(normalized)
                phone_numbers.append(normalized)

        if person_row is not None:
            sanitized_name: str = sanitize_display_name(person_row.canonical_name or "")
            if sanitized_name and sanitized_name != person_row.canonical_name:
                person_row.canonical_name = sanitized_name

            primary_email: str = person_row.primary_email or ""
            display_name: str = person_row.canonical_name or ""
            inferred: list[str] = infer_categories_from_contact(
                email=primary_email,
                display_name=display_name,
                org_name=current_org_name,
            )
            role_blob: str = f"{display_name} {current_role or ''} {current_org_name or ''}".lower()
            if re.search(r"\b(vc|venture capital|general partner|managing partner)\b", role_blob):
                if "vc" not in inferred:
                    inferred.append("vc")
            if "investor" in role_blob and "newsletter" not in role_blob:
                if "vc" not in inferred:
                    inferred.append("vc")
            if re.search(r"\bfounder\b|\bco-founder\b", role_blob):
                if "founder" not in inferred:
                    inferred.append("founder")
            if re.search(r"\bengineer\b|\bdeveloper\b|\bsoftware\b", role_blob):
                if "engineer" not in inferred:
                    inferred.append("engineer")

            for cat in inferred:
                if cat not in categories:
                    categories.append(cat)

        if current_role is None:
            for attr in attrs:
                if attr.kind == "role" and attr.value.strip():
                    candidate_role: str = attr.value.strip()
                    if candidate_role.lower() not in _INVALID_ROLE_VALUES:
                        current_role = candidate_role
                        break

        await self._session.execute(
            update(Person)
            .where(Person.id == person_id)
            .values(
                current_org_id=current_org_id,
                current_org_name=current_org_name,
                current_role=bindparam("recomputed_current_role"),
                bio_summary=bio_summary,
                social_profiles=social_profiles,
                inferred_categories=categories,
                descriptive_tags=descriptive_tags,
                phone_numbers=phone_numbers,
                location=location,
            ),
            {"recomputed_current_role": current_role},
        )
