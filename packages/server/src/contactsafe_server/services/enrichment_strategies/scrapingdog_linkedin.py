"""ScrapingDog LinkedIn profile enrichment strategy."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings
from contactsafe_server.db.models import Person, PersonAlias
from contactsafe_server.services.claim_writer import record_employment, record_person_attribute
from contactsafe_server.services.enrichment_attempt_tracker import EnrichmentAttemptTracker
from contactsafe_server.services.entity_resolution import EntityResolver
from contactsafe_server.services.scrapingdog_client import (
    ScrapedLinkedInExperience,
    ScrapedLinkedInProfile,
    ScrapingDogClient,
    ScrapingDogError,
    ScrapingDogPendingError,
    ScrapingDogRateLimitError,
    extract_linkedin_slug,
    linkedin_profile_url,
)
from contactsafe_server.services.strong_tie_matcher import SCRAPINGDOG_SOURCE_KIND

logger: logging.Logger = logging.getLogger(__name__)

SOURCE_KIND: str = SCRAPINGDOG_SOURCE_KIND


async def load_person_linkedin_url(
    session: AsyncSession,
    person_id: uuid.UUID,
) -> str | None:
    result = await session.execute(
        select(PersonAlias.value).where(
            PersonAlias.person_id == person_id,
            PersonAlias.kind == "linkedin_url",
        ).limit(1)
    )
    value: str | None = result.scalar_one_or_none()
    return value.rstrip("/") if value else None


async def apply_scraped_profile(
    session: AsyncSession,
    *,
    person: Person,
    profile: ScrapedLinkedInProfile,
    user_id: uuid.UUID,
    resolver: EntityResolver,
) -> bool:
    applied: bool = False

    if profile.name and (
        not person.canonical_name
        or person.canonical_name == (person.primary_email or "")
    ):
        person.canonical_name = profile.name
        applied = True

    if profile.headline:
        await record_person_attribute(
            session,
            person_id=person.id,
            kind="headline",
            value=profile.headline,
            contributor_user_id=user_id,
            contributor_source_kind=SOURCE_KIND,
            confidence=0.9,
        )
        if not person.bio_summary:
            person.bio_summary = profile.headline
        applied = True

    if profile.location:
        await record_person_attribute(
            session,
            person_id=person.id,
            kind="location",
            value=profile.location,
            contributor_user_id=user_id,
            contributor_source_kind=SOURCE_KIND,
            confidence=0.85,
        )
        if not person.location:
            person.location = profile.location
        applied = True

    profile_url: str = profile.profile_url or linkedin_profile_url(profile.link_id)
    try:
        await resolver.add_person_alias(
            person_id=person.id,
            kind="linkedin_url",
            value=profile_url,
        )
    except Exception:
        logger.debug("LinkedIn alias already present for person %s", person.id)

    social_profiles: dict[str, str] = dict(person.social_profiles or {})
    if social_profiles.get("linkedin") != profile_url:
        social_profiles["linkedin"] = profile_url
        person.social_profiles = social_profiles
        applied = True

    for experience in profile.experiences:
        await _record_experience(
            session,
            person=person,
            experience=experience,
            user_id=user_id,
            resolver=resolver,
        )
        applied = True

    if not profile.experiences and profile.current_company:
        org = await resolver.resolve_org(domain=None, name=profile.current_company)
        await record_employment(
            session,
            person_id=person.id,
            org_id=org.id,
            role_title=profile.current_title,
            is_current=True,
            contributor_user_id=user_id,
            contributor_source_kind=SOURCE_KIND,
            confidence=0.9,
            evidence={"headline": profile.headline, "source": "scrapingdog"},
        )
        applied = True

    return applied


async def _record_experience(
    session: AsyncSession,
    *,
    person: Person,
    experience: ScrapedLinkedInExperience,
    user_id: uuid.UUID,
    resolver: EntityResolver,
) -> None:
    org = await resolver.resolve_org(domain=None, name=experience.company)
    await record_employment(
        session,
        person_id=person.id,
        org_id=org.id,
        role_title=experience.title,
        is_current=experience.is_current,
        started_at=experience.start_date,
        ended_at=experience.end_date,
        contributor_user_id=user_id,
        contributor_source_kind=SOURCE_KIND,
        confidence=0.9 if experience.is_current else 0.75,
        evidence={"location": experience.location},
    )


async def run_scrapingdog_linkedin_strategy(
    session: AsyncSession,
    settings: Settings,
    *,
    person: Person,
    user_id: uuid.UUID,
    resolver: EntityResolver,
    tracker: EnrichmentAttemptTracker,
) -> bool:
    client: ScrapingDogClient = ScrapingDogClient(settings)
    if not client.is_configured:
        return False

    if not await tracker.should_attempt(person_id=person.id, source_kind=SOURCE_KIND):
        return False

    linkedin_url: str | None = await load_person_linkedin_url(session, person.id)
    if linkedin_url is None:
        return False

    slug: str | None = extract_linkedin_slug(linkedin_url)
    if slug is None:
        return False

    try:
        profile: ScrapedLinkedInProfile = await client.fetch_profile(slug)
    except ScrapingDogPendingError:
        raise
    except ScrapingDogRateLimitError as exc:
        await tracker.record_attempt(
            person_id=person.id,
            source_kind=SOURCE_KIND,
            user_id=user_id,
            succeeded=False,
            error=str(exc),
        )
        raise
    except ScrapingDogError as exc:
        await tracker.record_attempt(
            person_id=person.id,
            source_kind=SOURCE_KIND,
            user_id=user_id,
            succeeded=False,
            error=str(exc),
        )
        logger.info("ScrapingDog enrichment failed for %s: %s", person.id, exc)
        return False

    applied: bool = await apply_scraped_profile(
        session,
        person=person,
        profile=profile,
        user_id=user_id,
        resolver=resolver,
    )
    await tracker.record_attempt(
        person_id=person.id,
        source_kind=SOURCE_KIND,
        user_id=user_id,
        succeeded=applied,
        error=None if applied else "no_profile_fields",
    )
    return applied
