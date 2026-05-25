"""Recomputes derived columns on ``Person`` from claims.

Called at the end of each enrichment batch to keep person rows in sync
with the append-only claim tables.
"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    EmploymentClaim,
    Person,
    PersonAttributeClaim,
    UserPersonObservation,
)
from contactsafe_server.services.category_inference import infer_categories_from_contact

logger: logging.Logger = logging.getLogger(__name__)


class PersonProfileRecompute:
    def __init__(self, session: AsyncSession) -> None:
        self._session: AsyncSession = session

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

        count: int = 0
        for pid in person_ids:
            await self._recompute_person(pid)
            count += 1

        logger.info("Recomputed %d person profiles for user %s", count, user_id)
        return count

    async def recompute_persons(self, person_ids: list[uuid.UUID]) -> int:
        """Recompute derived columns for a specific set of person IDs."""
        count: int = 0
        for pid in person_ids:
            await self._recompute_person(pid)
            count += 1
        return count

    async def _recompute_person(self, person_id: uuid.UUID) -> None:
        # --- Employment: highest-confidence current employment ---
        emp_stmt = (
            select(EmploymentClaim)
            .where(
                EmploymentClaim.person_id == person_id,
                EmploymentClaim.is_current.is_(True),
            )
            .order_by(EmploymentClaim.confidence.desc(), EmploymentClaim.observed_at.desc())
            .limit(1)
        )
        emp_result = await self._session.execute(emp_stmt)
        best_emp: EmploymentClaim | None = emp_result.scalar_one_or_none()

        current_org_id: uuid.UUID | None = best_emp.org_id if best_emp else None
        current_org_name: str | None = None
        current_role: str | None = best_emp.role_title if best_emp else None

        if best_emp and best_emp.org_id:
            from contactsafe_server.db.models import Org
            org_stmt = select(Org.canonical_name).where(Org.id == best_emp.org_id)
            org_result = await self._session.execute(org_stmt)
            current_org_name = org_result.scalar_one_or_none()

        # --- Attribute claims ---
        attr_stmt = select(PersonAttributeClaim).where(
            PersonAttributeClaim.person_id == person_id,
        )
        attr_result = await self._session.execute(attr_stmt)
        attrs: list[PersonAttributeClaim] = list(attr_result.scalars().all())

        social_profiles: dict[str, str] = {}
        categories: list[str] = []
        bio_summary: str | None = None
        location: str | None = None
        phone_numbers: list[str] = []

        best_bio_len: int = 0
        for attr in attrs:
            if attr.kind.startswith("social_profile."):
                platform: str = attr.kind.removeprefix("social_profile.")
                social_profiles[platform] = attr.value
            elif attr.kind == "category":
                if attr.value not in categories:
                    categories.append(attr.value)
            elif attr.kind == "bio_summary":
                if len(attr.value) > best_bio_len:
                    bio_summary = attr.value
                    best_bio_len = len(attr.value)
            elif attr.kind == "location":
                location = attr.value
            elif attr.kind == "phone":
                if attr.value not in phone_numbers:
                    phone_numbers.append(attr.value)

        # Re-infer categories from the now-resolved person data so that
        # contacts whose org/role was only populated after initial heuristic
        # enrichment still get properly categorized.
        person_row: Person | None = await self._session.get(Person, person_id)
        if person_row is not None:
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

        await self._session.execute(
            update(Person)
            .where(Person.id == person_id)
            .values(
                current_org_id=current_org_id,
                current_org_name=current_org_name,
                current_role=current_role,
                bio_summary=bio_summary,
                social_profiles=social_profiles,
                inferred_categories=categories,
                phone_numbers=phone_numbers,
                location=location,
            )
        )
