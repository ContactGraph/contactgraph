"""Export strong-tie contacts as CSV for downstream job-search workflows."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass

from sqlalchemy import Select, and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import EmploymentClaim, Person, PersonAlias, UserPersonObservation
from contactsafe_server.services.strong_tie_matcher import (
    SCRAPINGDOG_SOURCE_KIND,
    _linkedin_alias_exists,
    _linkedin_observation_exists,
    _personal_observation_exists,
)

CLOSE_COLLEAGUE_HEADERS: tuple[str, ...] = (
    "name",
    "email",
    "phone",
    "current_company",
    "current_role",
    "linkedin_url",
    "tie_strength",
    "scrapingdog_enriched",
)


@dataclass(frozen=True, slots=True)
class CloseColleagueRow:
    name: str
    email: str
    phone: str
    current_company: str
    current_role: str
    linkedin_url: str
    tie_strength: str
    scrapingdog_enriched: str


def _build_export_query(user_id: uuid.UUID) -> Select[tuple[Person, UserPersonObservation, str, bool]]:
    linkedin_alias = (
        select(PersonAlias.value)
        .where(
            PersonAlias.person_id == Person.id,
            PersonAlias.kind == "linkedin_url",
        )
        .order_by(PersonAlias.first_seen_at.asc())
        .limit(1)
        .scalar_subquery()
    )
    scrapingdog_exists = exists(
        select(EmploymentClaim.person_id).where(
            EmploymentClaim.person_id == Person.id,
            EmploymentClaim.contributor_source_kind == SCRAPINGDOG_SOURCE_KIND,
        )
    )

    return (
        select(
            Person,
            UserPersonObservation,
            linkedin_alias.label("linkedin_url"),
            scrapingdog_exists.label("scrapingdog_enriched"),
        )
        .join(
            UserPersonObservation,
            and_(
                UserPersonObservation.person_id == Person.id,
                UserPersonObservation.user_id == user_id,
            ),
        )
        .where(
            _linkedin_observation_exists(user_id),
            _personal_observation_exists(user_id),
            _linkedin_alias_exists(),
            UserPersonObservation.is_human.is_(True),
            UserPersonObservation.is_broadcast.is_(False),
            UserPersonObservation.is_automated.is_(False),
        )
        .order_by(UserPersonObservation.tie_strength_score.desc())
    )


def _row_to_csv_values(row: CloseColleagueRow) -> list[str]:
    return [
        row.name,
        row.email,
        row.phone,
        row.current_company,
        row.current_role,
        row.linkedin_url,
        row.tie_strength,
        row.scrapingdog_enriched,
    ]


async def fetch_close_colleague_rows(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list[CloseColleagueRow]:
    result = await session.execute(_build_export_query(user_id))
    rows: list[CloseColleagueRow] = []

    for person, obs, linkedin_url, scrapingdog_enriched in result.all():
        phone: str = person.phone_numbers[0] if person.phone_numbers else ""
        url: str = linkedin_url if isinstance(linkedin_url, str) else ""
        rows.append(
            CloseColleagueRow(
                name=person.canonical_name,
                email=person.primary_email or "",
                phone=phone,
                current_company=person.current_org_name or "",
                current_role=person.current_role or "",
                linkedin_url=url.rstrip("/"),
                tie_strength=f"{obs.tie_strength_score:.3f}",
                scrapingdog_enriched="yes" if scrapingdog_enriched else "no",
            )
        )

    return rows


async def build_close_colleague_csv(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> str:
    rows: list[CloseColleagueRow] = await fetch_close_colleague_rows(session, user_id)
    buffer: io.StringIO = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(list(CLOSE_COLLEAGUE_HEADERS))
    for row in rows:
        writer.writerow(_row_to_csv_values(row))
    return buffer.getvalue()


async def export_close_colleagues_to_file(
    session: AsyncSession,
    user_id: uuid.UUID,
    output_path: str,
) -> int:
    rows: list[CloseColleagueRow] = await fetch_close_colleague_rows(session, user_id)
    buffer: io.StringIO = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(list(CLOSE_COLLEAGUE_HEADERS))
    for row in rows:
        writer.writerow(_row_to_csv_values(row))
    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(buffer.getvalue())
    return len(rows)
