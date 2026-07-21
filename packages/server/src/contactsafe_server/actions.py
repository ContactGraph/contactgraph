"""Shared action functions backing both MCP tools and the REST API.

Each function accepts an ``AppContext`` and an already-resolved ``user_id``
(or ``None`` when unauthenticated) so callers only differ in *how* they
obtain those two values.
"""

from __future__ import annotations

import logging
from typing import Literal, cast
from uuid import UUID

from datetime import UTC, datetime

from contactsafe_core.contact_schemas import (
    AddWatchedCompanyRequest,
    AddWatchedCompanyResult,
    CancelOrgEnrichmentResult,
    CreateOrgListRequest,
    CreateOrgListResult,
    DedupPersonsResult,
    DeleteOrgListRequest,
    DeleteOrgListResult,
    EnrichOrgsResult,
    EnrichPersonResult,
    EnrichStrongTiesResult,
    ListOrgListsResult,
    ListOrgsResult,
    ListPeopleResult,
    ListStrongTiesResult,
    ModifyOrgListMembershipRequest,
    ModifyOrgListMembershipResult,
    NetworkStatusResult,
    OrgDetailResult,
    OrgEnrichmentStatusResult,
    PersonDetailResult,
    RenameOrgListRequest,
    RenameOrgListResult,
    ScrapingDogEnrichmentStatusResult,
    StrongTieCompaniesResult,
    StrongTieCountResult,
    FlatJobListResult,
    JobDetailResult,
    JobMonitorConfigResult,
    JobScanStatusResult,
    JobPreferencesResult,
    JobTargetScope,
    ListOrgJobsResult,
    NextStepsResult,
    NotificationPreferencesResult,
    SetJobInterestResult,
    SetJobMonitorConfigRequest,
    SetJobTargetScopeRequest,
    UpdateTaskStatusResult,
    UpdateOrgRequest,
    UpdatePersonRequest,
)
from datetime import date
from urllib.parse import urlparse

from contactsafe_core.enums import SessionStatus, SourceType, EnrichmentRunState, SyncState
from contactsafe_core.schemas import (
    ConnectSourceResult,
    DescribeGraphResult,
    EditTrustedUsersResult,
    EnrichmentStatusResult,
    ListContactEnrichmentStatusResult,
    ListSourcesResult,
    PersonMatch,
    PollConnectResult,
    QueryNetworkResult,
    SecondDegreeMatch,
    SecondDegreeTargetCompaniesResult,
    SecondDegreeTargetCompanySummary,
    SecondDegreeTargetInsiderSummary,
    SourceStatusResult,
    StartEnrichmentResult,
    SyncSourceResult,
    TargetCompaniesResult,
    TargetCompanyInsiderSummary,
    TargetCompanySummary,
    UpdateUserProfileRequest,
    UploadSourceResult,
    UserExperience,
    UserProfileResult,
    DeleteUserAccountResult,
    ViewTrustedUsersResult,
)

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import (
    ConnectSession,
    EmploymentClaim,
    Org,
    OrgAlias,
    OrgList,
    Person,
    PersonAlias,
    PersonAttributeClaim,
    Source,
    User,
)

JOB_PROSPECTS_LIST_NAME: str = "Job Prospects"


def _normalize_website_to_domain(website: str | None) -> str | None:
    """Extract a bare domain from a website URL or domain string."""
    if website is None:
        return None
    raw: str = website.strip()
    if not raw:
        return None
    candidate: str = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    host: str = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or "." not in host:
        # Bare-looking input without a parseable host (e.g. "hubspot.com/path")
        bare: str = raw.lower().removeprefix("www.").split("/")[0].split("?")[0]
        if "." in bare and " " not in bare:
            return bare
        return None
    return host
from contactsafe_server.services.claim_writer import record_employment, record_person_attribute
from contactsafe_server.services.contacts_service import normalize_social_platform
from contactsafe_server.services.entity_resolution import EntityResolver
from contactsafe_server.services.person_profile_recompute import PersonProfileRecompute
from contactsafe_server.services.phone_normalization import normalize_phone
from contactsafe_server.services.user_person_service import ensure_user_person
from contactsafe_server.deps import (
    AppContext,
    build_oauth_server_service,
    build_oauth_service,
    build_enrichment_service,
    build_source_service,
)
from contactsafe_server.services.contacts_service import ContactsService
from contactsafe_server.services.org_list_service import OrgListService
from contactsafe_server.services.strong_tie_api_service import StrongTieApiService
from contactsafe_server.services.graph_summary_service import GraphSummaryService
from contactsafe_server.services.network_query_service import NetworkQueryService
from contactsafe_server.services.person_dedup_service import PersonDedupService
from contactsafe_server.services.query_planner import QueryPlanner
from contactsafe_server.services.source_service import SourceService
from contactsafe_server.services.target_companies_service import (
    SecondDegreeTargetCompanyMatch,
    TargetCompaniesService,
    TargetCompanyMatch,
)
from contactsafe_server.services.connect_session_poll import verify_poll_secret
from contactsafe_server.services.trust_list_service import TrustListService
from contactsafe_server.services.upload_payload_crypto import build_upload_payload
from contactsafe_server.utils import parse_source_id

logger: logging.Logger = logging.getLogger(__name__)

_PHONE_CONTACTS_UPLOAD_INSTRUCTIONS: str = (
    "On iPhone: Settings > Contacts > Export, then upload the .vcf file. "
    "Or visit icloud.com/contacts, select all, export vCard."
)


async def connect_source(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    source_type: str = SourceType.GOOGLE_MAIL.value,
    user_token: str | None = None,
) -> ConnectSourceResult:
    try:
        parsed_type: SourceType = SourceType(source_type)
    except ValueError as exc:
        raise ValueError(f"Unknown source_type: {source_type}") from exc

    if parsed_type == SourceType.PHONE_CONTACTS_UPLOAD:
        if user_id is None:
            raise ValueError("Authentication required to add phone contacts.")
        async with ctx.session_factory() as db:
            user: User | None = await db.get(User, user_id)
            if user is None:
                raise ValueError("User not found")
            sources: SourceService = build_source_service(db)
            source = await sources.ensure_phone_contacts_source(user_id, user.email)
            upload_url: str = ctx.settings.upload_url_for_source(source.id)
            already_uploaded: bool = (
                source.upload_payload is not None
                and source.sync_state == SyncState.COMPLETE.value
            )
            await db.commit()
            return ConnectSourceResult(
                connect_session_id=source.id,
                oauth_url="",
                upload_url=upload_url,
                upload_instructions=_PHONE_CONTACTS_UPLOAD_INSTRUCTIONS,
                status=SessionStatus.CONNECTED,
                source_id=source.id,
                email=user.email,
                message="Upload your phone contacts at the URL above.",
                already_connected=already_uploaded,
            )

    if parsed_type == SourceType.GOOGLE_CONTACTS:
        parsed_type = SourceType.GOOGLE_MAIL

    async with ctx.session_factory() as db:
        oauth = build_oauth_service(db, ctx)
        result: ConnectSourceResult = await oauth.create_connect_session(
            user_token,
            source_type=parsed_type,
            authenticated_user_id=user_id,
        )
        if result.already_connected and result.source_id is not None:
            sources: SourceService = build_source_service(db)
            resolved_uid: UUID = await sources.resolve_user_id(source_id=result.source_id)
            if user_id is not None and resolved_uid == user_id:
                token_response = await build_oauth_server_service(db, ctx).mint_tokens_for_user(
                    resolved_uid, email=result.email
                )
                result = result.model_copy(
                    update={
                        "access_token": token_response.access_token,
                        "refresh_token": token_response.refresh_token,
                    }
                )
            else:
                logger.warning(
                    "Suppressing token mint for already-connected source due to unauthenticated or mismatched user",
                    extra={
                        "authenticated_user_id": str(user_id) if user_id is not None else None,
                        "resolved_user_id": str(resolved_uid),
                        "source_id": str(result.source_id),
                    },
                )
        await db.commit()
        return result


async def cancel_sync(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    source_id: str,
) -> "CancelSyncResult":
    from contactsafe_core.schemas import CancelSyncResult
    from contactsafe_core.enums import SyncState
    from contactsafe_server.services.import_scheduler import release_sync_lock

    if user_id is None:
        return CancelSyncResult(cancelled=False, message="Not authenticated.")
    async with ctx.session_factory() as db:
        from contactsafe_server.db.models import Source
        from sqlalchemy import select

        result = await db.execute(
            select(Source).where(Source.id == UUID(source_id), Source.user_id == user_id),
        )
        source: Source | None = result.scalar_one_or_none()
        if source is None:
            return CancelSyncResult(cancelled=False, message="Source not found.")
        if source.sync_state not in (SyncState.SYNCING.value, SyncState.PENDING.value):
            return CancelSyncResult(cancelled=False, message="No import in progress.")
        source.sync_state = SyncState.FAILED.value
        source.sync_error = "Import cancelled by user."
        await db.commit()
        from contactsafe_server.graph_event_publishers import publish_source_sync_update

        publish_source_sync_update(source)
        release_sync_lock(source.id, source.user_id)
        return CancelSyncResult(cancelled=True, message="Import cancelled.")


async def list_sources(
    ctx: AppContext,
    user_id: UUID | None,
) -> ListSourcesResult:
    if user_id is None:
        return ListSourcesResult(
            sources=[],
            message=(
                "Authentication required. Obtain a Bearer token via OAuth "
                f"({ctx.settings.base_url.rstrip('/')}/.well-known/oauth-protected-resource)."
            ),
        )
    async with ctx.session_factory() as db:
        sources: SourceService = build_source_service(db)
        result: ListSourcesResult = await sources.list_sources_for_user(user_id)
        await db.commit()
        return result


async def get_source_status(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    source_id: str | None = None,
) -> SourceStatusResult:
    async with ctx.session_factory() as db:
        sources: SourceService = build_source_service(db)
        if source_id is not None:
            if user_id is None:
                raise ValueError("Authentication required (Bearer token)")
            source_uuid: UUID = parse_source_id(source_id)
            await sources.require_source_owned_by(source_uuid, user_id)
            return await sources.get_source_status(source_uuid)
        elif user_id is not None:
            return await sources.get_source_status_for_user(user_id)
        else:
            raise ValueError("Authentication required (Bearer token)")


async def sync_source(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    source_id: str | None = None,
) -> SyncSourceResult:
    async with ctx.session_factory() as db:
        sources: SourceService = build_source_service(db)
        if source_id is not None:
            if user_id is None:
                raise ValueError("Authentication required (Bearer token)")
            source_uuid: UUID = parse_source_id(source_id)
            await sources.require_source_owned_by(source_uuid, user_id)
            result: SyncSourceResult = await sources.request_sync(source_uuid)
        elif user_id is not None:
            result = await sources.request_sync_for_user(user_id)
        else:
            raise ValueError("Authentication required (Bearer token)")
        await db.commit()
        return result


async def start_enrichment(
    ctx: AppContext,
    user_id: UUID | None,
) -> StartEnrichmentResult:
    if user_id is None:
        return StartEnrichmentResult(
            run_id=None,
            scheduled=False,
            state=EnrichmentRunState.PENDING,
            message="Authentication required. Provide a Bearer token.",
        )
    async with ctx.session_factory() as db:
        enrichment = build_enrichment_service(db)
        result: StartEnrichmentResult = await enrichment.start_enrichment(user_id)
        await db.commit()
        return result


async def get_enrichment_status(
    ctx: AppContext,
    user_id: UUID | None,
) -> EnrichmentStatusResult:
    if user_id is None:
        return EnrichmentStatusResult(
            run_id=None,
            state=EnrichmentRunState.PENDING,
            message="Authentication required. Provide a Bearer token.",
        )
    async with ctx.session_factory() as db:
        enrichment = build_enrichment_service(db)
        result = await enrichment.get_enrichment_status(user_id)
        await db.commit()
        return result


async def list_contact_enrichment_status(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    limit: int = 100,
) -> ListContactEnrichmentStatusResult:
    if user_id is None:
        return ListContactEnrichmentStatusResult(
            items=[],
            message="Authentication required. Provide a Bearer token.",
        )
    async with ctx.session_factory() as db:
        enrichment = build_enrichment_service(db)
        result = await enrichment.list_contact_enrichment_status(user_id, limit=limit)
        await db.commit()
        return result


async def _load_user_experiences(
    db: AsyncSession,
    user: User,
) -> list[UserExperience]:
    if user.person_id is None:
        return []
    result = await db.execute(
        select(EmploymentClaim, Org.canonical_name)
        .join(Org, EmploymentClaim.org_id == Org.id)
        .where(EmploymentClaim.person_id == user.person_id)
        .order_by(EmploymentClaim.is_current.desc(), EmploymentClaim.started_at.desc().nulls_last())
    )
    experiences: list[UserExperience] = []
    for claim, org_name in result.all():
        experiences.append(UserExperience(
            id=claim.id,
            company=org_name,
            role=claim.role_title,
            is_current=claim.is_current,
            started_at=claim.started_at,
            ended_at=claim.ended_at,
        ))
    return experiences


async def _load_user_headline(
    db: AsyncSession,
    user: User,
) -> str | None:
    if user.person_id is None:
        return None
    result = await db.execute(
        select(PersonAttributeClaim.value)
        .where(
            PersonAttributeClaim.person_id == user.person_id,
            PersonAttributeClaim.kind == "headline",
        )
        .order_by(PersonAttributeClaim.confidence.desc())
        .limit(1)
    )
    row: str | None = result.scalar_one_or_none()
    return row


async def _load_user_person_fields(
    db: AsyncSession,
    person_id: UUID,
) -> dict[str, object]:
    """Load phone, linkedin_url, bio_summary, social_profiles from the user's Person."""
    person: Person | None = await db.get(Person, person_id)
    if person is None:
        return {}

    phones: list[str] = list(dict.fromkeys(person.phone_numbers or []))
    social_profiles: dict[str, str] = dict(person.social_profiles or {})

    alias_result = await db.execute(
        select(PersonAlias.value).where(
            PersonAlias.person_id == person_id,
            PersonAlias.kind == "linkedin_url",
        ).order_by(PersonAlias.first_seen_at.desc()).limit(1)
    )
    linkedin_url: str | None = alias_result.scalar_one_or_none()
    if linkedin_url is None:
        linkedin_url = social_profiles.get("linkedin")

    return {
        "phone": phones[0] if phones else None,
        "linkedin_url": linkedin_url,
        "bio_summary": person.bio_summary,
        "social_profiles": social_profiles,
    }


async def get_user_profile(
    ctx: AppContext,
    user_id: UUID | None,
) -> UserProfileResult:
    if user_id is None:
        return UserProfileResult(message="Authentication required. Provide a Bearer token.")
    async with ctx.session_factory() as db:
        user: User | None = await db.get(User, user_id)
        if user is None:
            return UserProfileResult(message="User not found.")
        experiences: list[UserExperience] = await _load_user_experiences(db, user)
        headline: str | None = await _load_user_headline(db, user)

        person_fields: dict[str, object] = {}
        if user.person_id is not None:
            person_fields = await _load_user_person_fields(db, user.person_id)

        return UserProfileResult(
            email=user.email,
            display_name=user.display_name or user.google_profile_name,
            headline=headline,
            location=user.location,
            google_profile_name=user.google_profile_name,
            google_profile_picture=user.google_profile_picture,
            phone=person_fields.get("phone"),  # type: ignore[arg-type]
            linkedin_url=person_fields.get("linkedin_url"),  # type: ignore[arg-type]
            bio_summary=person_fields.get("bio_summary"),  # type: ignore[arg-type]
            social_profiles=person_fields.get("social_profiles", {}),  # type: ignore[arg-type]
            experiences=experiences,
            message="User profile loaded.",
        )


_MANUAL_SOURCE_KIND: str = "user_manual"
_MANUAL_CONFIDENCE: float = 1.0


async def _apply_user_person_attribute(
    db: AsyncSession,
    *,
    person_id: UUID,
    user_id: UUID,
    kind: str,
    value: str | None,
) -> None:
    if value is None:
        return
    cleaned: str = value.strip()
    if not cleaned:
        return
    await record_person_attribute(
        db,
        person_id=person_id,
        kind=kind,
        value=cleaned,
        contributor_user_id=user_id,
        contributor_source_kind=_MANUAL_SOURCE_KIND,
        confidence=_MANUAL_CONFIDENCE,
    )


async def _sync_user_social_profiles(
    db: AsyncSession,
    *,
    person_id: UUID,
    user_id: UUID,
    profiles: dict[str, str],
) -> None:
    await db.execute(
        delete(PersonAttributeClaim).where(
            PersonAttributeClaim.person_id == person_id,
            PersonAttributeClaim.kind.like("social_profile.%"),
            PersonAttributeClaim.kind != "social_profile.linkedin",
        )
    )
    seen_platforms: set[str] = set()
    for raw_platform, raw_url in profiles.items():
        platform: str | None = normalize_social_platform(raw_platform)
        if platform is None or platform in seen_platforms:
            continue
        url: str = raw_url.strip().rstrip("/")
        if not url:
            continue
        seen_platforms.add(platform)
        await record_person_attribute(
            db,
            person_id=person_id,
            kind=f"social_profile.{platform}",
            value=url,
            contributor_user_id=user_id,
            contributor_source_kind=_MANUAL_SOURCE_KIND,
            confidence=_MANUAL_CONFIDENCE,
        )


async def update_user_profile(
    ctx: AppContext,
    user_id: UUID | None,
    body: UpdateUserProfileRequest,
) -> UserProfileResult:
    if user_id is None:
        return UserProfileResult(message="Authentication required. Provide a Bearer token.")
    async with ctx.session_factory() as db:
        user: User | None = await db.get(User, user_id)
        if user is None:
            return UserProfileResult(message="User not found.")
        if body.display_name is not None:
            cleaned_name: str = body.display_name.strip()
            user.display_name = cleaned_name or None
        if body.location is not None:
            cleaned_location: str = body.location.strip()
            user.location = cleaned_location or None

        has_person_fields: bool = any(
            getattr(body, f) is not None
            for f in ("phone", "linkedin_url", "bio_summary", "social_profiles")
        )
        if has_person_fields:
            person: Person = await ensure_user_person(db, user)
            resolver: EntityResolver = EntityResolver(db)

            await _apply_user_person_attribute(
                db, person_id=person.id, user_id=user.id, kind="phone", value=body.phone,
            )
            if body.phone is not None and body.phone.strip():
                normalized_phone: str = normalize_phone(body.phone.strip())
                await resolver.add_person_alias(
                    person_id=person.id, kind="phone", value=normalized_phone, confidence=_MANUAL_CONFIDENCE,
                )

            await _apply_user_person_attribute(
                db, person_id=person.id, user_id=user.id, kind="bio_summary", value=body.bio_summary,
            )
            await _apply_user_person_attribute(
                db, person_id=person.id, user_id=user.id, kind="location", value=body.location,
            )

            if body.linkedin_url is not None:
                linkedin: str = body.linkedin_url.strip().rstrip("/")
                # Remove stale linkedin aliases/claims so the new value wins
                await db.execute(
                    delete(PersonAlias).where(
                        PersonAlias.person_id == person.id,
                        PersonAlias.kind == "linkedin_url",
                    )
                )
                await db.execute(
                    delete(PersonAttributeClaim).where(
                        PersonAttributeClaim.person_id == person.id,
                        PersonAttributeClaim.kind == "social_profile.linkedin",
                        PersonAttributeClaim.contributor_source_kind == _MANUAL_SOURCE_KIND,
                    )
                )
                if linkedin:
                    await record_person_attribute(
                        db,
                        person_id=person.id,
                        kind="social_profile.linkedin",
                        value=linkedin,
                        contributor_user_id=user.id,
                        contributor_source_kind=_MANUAL_SOURCE_KIND,
                        confidence=_MANUAL_CONFIDENCE,
                    )
                    await resolver.add_person_alias(
                        person_id=person.id, kind="linkedin_url", value=linkedin, confidence=_MANUAL_CONFIDENCE,
                    )

            if body.social_profiles is not None:
                await _sync_user_social_profiles(
                    db, person_id=person.id, user_id=user.id, profiles=body.social_profiles,
                )

            recompute: PersonProfileRecompute = PersonProfileRecompute(db)
            await recompute.recompute_persons([person.id])

        await db.commit()
        await db.refresh(user)

        person_fields: dict[str, object] = {}
        if user.person_id is not None:
            person_fields = await _load_user_person_fields(db, user.person_id)

        return UserProfileResult(
            email=user.email,
            display_name=user.display_name or user.google_profile_name,
            location=user.location,
            google_profile_name=user.google_profile_name,
            phone=person_fields.get("phone"),  # type: ignore[arg-type]
            linkedin_url=person_fields.get("linkedin_url"),  # type: ignore[arg-type]
            bio_summary=person_fields.get("bio_summary"),  # type: ignore[arg-type]
            social_profiles=person_fields.get("social_profiles", {}),  # type: ignore[arg-type]
            message="Profile updated.",
        )


async def save_user_experience(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    experience_id: UUID | None = None,
    company: str,
    role: str | None = None,
    is_current: bool = False,
    started_at: date | None = None,
    ended_at: date | None = None,
) -> UserProfileResult:
    if user_id is None:
        return UserProfileResult(message="Authentication required. Provide a Bearer token.")
    async with ctx.session_factory() as db:
        user: User | None = await db.get(User, user_id)
        if user is None:
            return UserProfileResult(message="User not found.")
        person = await ensure_user_person(db, user)
        resolver = EntityResolver(db)
        org = await resolver.resolve_org(domain=None, name=company.strip())
        if org is None:
            return UserProfileResult(
                message="That company name is not a real organization (e.g. Self Employed, Stealth Startup).",
            )

        if experience_id is not None:
            claim: EmploymentClaim | None = await db.get(EmploymentClaim, experience_id)
            if claim is not None and claim.person_id == person.id:
                claim.org_id = org.id
                claim.role_title = role
                claim.is_current = is_current
                claim.started_at = started_at
                claim.ended_at = ended_at
                await db.flush()
            else:
                raise ValueError("Experience not found or does not belong to user")
        else:
            await record_employment(
                db,
                person_id=person.id,
                org_id=org.id,
                role_title=role,
                is_current=is_current,
                started_at=started_at,
                ended_at=ended_at,
                contributor_user_id=user_id,
                contributor_source_kind="user_manual",
                confidence=1.0,
            )

        recompute = PersonProfileRecompute(db)
        await recompute.recompute_persons([person.id])
        await db.commit()
        await db.refresh(user)

        experiences: list[UserExperience] = await _load_user_experiences(db, user)
        headline: str | None = await _load_user_headline(db, user)
        return UserProfileResult(
            email=user.email,
            display_name=user.display_name or user.google_profile_name,
            headline=headline,
            location=user.location,
            google_profile_name=user.google_profile_name,
            experiences=experiences,
            message="Experience saved.",
        )


async def delete_user_experience(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    experience_id: UUID,
) -> UserProfileResult:
    if user_id is None:
        return UserProfileResult(message="Authentication required. Provide a Bearer token.")
    async with ctx.session_factory() as db:
        user: User | None = await db.get(User, user_id)
        if user is None:
            return UserProfileResult(message="User not found.")
        if user.person_id is None:
            raise ValueError("No profile exists yet")

        claim: EmploymentClaim | None = await db.get(EmploymentClaim, experience_id)
        if claim is None or claim.person_id != user.person_id:
            raise ValueError("Experience not found or does not belong to user")

        await db.delete(claim)
        recompute = PersonProfileRecompute(db)
        await recompute.recompute_persons([user.person_id])
        await db.commit()
        await db.refresh(user)

        experiences: list[UserExperience] = await _load_user_experiences(db, user)
        headline: str | None = await _load_user_headline(db, user)
        return UserProfileResult(
            email=user.email,
            display_name=user.display_name or user.google_profile_name,
            headline=headline,
            location=user.location,
            google_profile_name=user.google_profile_name,
            experiences=experiences,
            message="Experience deleted.",
        )


async def delete_user_account(
    ctx: AppContext,
    user_id: UUID | None,
) -> DeleteUserAccountResult:
    import asyncio
    from sqlalchemy import select
    from sqlalchemy.exc import DBAPIError
    from contactsafe_server.db.models import Source
    from contactsafe_server.services.import_scheduler import (
        is_source_sync_running,
        release_sync_lock,
    )

    if user_id is None:
        return DeleteUserAccountResult(
            deleted=False,
            message="Authentication required. Provide a Bearer token.",
        )

    # Cancel all running syncs, enrichment, and job discovery before deleting
    # to avoid deadlocks with background tasks writing to the same rows.
    async with ctx.session_factory() as db:
        sources = (
            await db.execute(select(Source).where(Source.user_id == user_id))
        ).scalars().all()
        for source in sources:
            if source.sync_state in (SyncState.SYNCING.value, SyncState.PENDING.value):
                source.sync_state = SyncState.FAILED.value
                source.sync_error = "Account deleted."
            if is_source_sync_running(source.id):
                release_sync_lock(source.id, user_id)
        await db.commit()

    # Brief yield so background tasks can observe the cancelled state and wind down.
    await asyncio.sleep(0.2)

    max_attempts: int = 3
    for attempt in range(1, max_attempts + 1):
        try:
            async with ctx.session_factory() as db:
                user: User | None = await db.get(User, user_id)
                if user is None:
                    return DeleteUserAccountResult(deleted=False, message="User not found.")
                await db.delete(user)
                await db.commit()
                return DeleteUserAccountResult(
                    deleted=True,
                    message="Your account and all associated data have been deleted.",
                )
        except DBAPIError as exc:
            is_deadlock: bool = "DeadlockDetectedError" in str(exc) or "deadlock" in str(exc).lower()
            if is_deadlock and attempt < max_attempts:
                logger.warning(
                    "Deadlock on account deletion attempt %d/%d for user %s, retrying",
                    attempt, max_attempts, user_id,
                )
                await asyncio.sleep(0.5 * attempt)
                continue
            logger.exception("Account deletion failed for user %s", user_id)
            raise

    return DeleteUserAccountResult(deleted=False, message="Deletion failed after retries.")


async def upload_source(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    source_type: str,
    filename: str,
    content: str,
    regenerate_role_suggestions: bool = True,
) -> UploadSourceResult:
    if user_id is None:
        raise ValueError("Authentication required. Provide a Bearer token.")
    if len(content.encode("utf-8")) > ctx.settings.upload_max_file_size_bytes:
        raise ValueError(
            f"File exceeds {ctx.settings.upload_max_file_size_mb}MB limit"
        )
    try:
        parsed_type: SourceType = SourceType(source_type)
    except ValueError as exc:
        raise ValueError(f"Unknown source_type: {source_type}") from exc

    if parsed_type not in {
        SourceType.PHONE_CONTACTS_UPLOAD,
        SourceType.LINKEDIN_CONNECTIONS_UPLOAD,
        SourceType.LINKEDIN_PROFILE_UPLOAD,
    }:
        raise ValueError(f"upload_source not supported for {source_type}")

    async with ctx.session_factory() as db:
        sources: SourceService = build_source_service(db)
        source = await sources.ensure_upload_source(
            user_id,
            source_type=parsed_type,
            filename=filename,
            content=content,
            encryptor=ctx.encryptor,
            regenerate_role_suggestions=regenerate_role_suggestions,
        )
        await db.commit()
        sync_result: SyncSourceResult = await sources.request_sync(source.id)
        await db.commit()
        return UploadSourceResult(
            source_id=source.id,
            scheduled=sync_result.scheduled,
            sync_state=sync_result.sync_state,
            message=sync_result.message,
        )


async def upload_contacts(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    source_id: str,
    filename: str,
    content: str,
) -> SyncSourceResult:
    """Upload a VCF/CSV file to an existing phone_contacts_upload source."""
    if user_id is None:
        raise ValueError("Authentication required. Provide a Bearer token.")
    if len(content.encode("utf-8")) > ctx.settings.upload_max_file_size_bytes:
        raise ValueError(
            f"File exceeds {ctx.settings.upload_max_file_size_mb}MB limit"
        )

    source_uuid: UUID = parse_source_id(source_id)
    async with ctx.session_factory() as db:
        source: Source | None = await db.get(Source, source_uuid)
        if source is None:
            raise ValueError(f"Unknown source_id: {source_id}")
        if source.user_id != user_id:
            raise ValueError(f"Unknown source_id: {source_id}")
        if source.source_type != SourceType.PHONE_CONTACTS_UPLOAD.value:
            raise ValueError("Source is not a phone contacts upload source")

        source.upload_payload = build_upload_payload(
            filename=filename,
            content=content,
            encryptor=ctx.encryptor,
        )
        source.sync_state = SyncState.PENDING.value
        source.sync_error = None
        await db.commit()

        sources: SourceService = build_source_service(db)
        result: SyncSourceResult = await sources.request_sync(source.id)
        await db.commit()
        return result


async def query_network(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    question: str,
) -> QueryNetworkResult:
    if user_id is None:
        return QueryNetworkResult(
            question=question,
            message="Authentication required. Provide a Bearer token.",
        )

    async with ctx.session_factory() as db:
        sources: SourceService = build_source_service(db)
        if not await sources.user_has_queryable_graph(user_id):
            return QueryNetworkResult(
                question=question,
                message=(
                    "Sync still running or not started. Call sync_source, then "
                    "get_source_status until sync_state is partial or complete."
                ),
            )

        planner = QueryPlanner(ctx.settings)
        plan = await planner.plan(question)
        executor = NetworkQueryService(db)
        matches: list[PersonMatch] = await executor.execute(user_id=user_id, plan=plan)

        trust_svc = TrustListService(db, ctx.settings.base_url)
        try:
            second_degree: list[SecondDegreeMatch] = await executor.execute_second_degree(
                user_id=user_id,
                plan=plan,
                trust_list_service=trust_svc,
                signing_key=ctx.settings.effective_jwt_signing_key,
            )
        except Exception:
            logger.debug("2nd-degree query failed, returning first-degree only", exc_info=True)
            second_degree = []

        try:
            system_messages: list[str] = await trust_svc.get_system_messages(user_id)
        except Exception:
            system_messages = []

        if not matches and not second_degree:
            has_filters: bool = bool(
                plan.name_tokens
                or plan.org_names
                or plan.categories_any
                or plan.role_keywords
                or plan.relationship_types_any
                or plan.semantic_query
                or plan.require_genuine_contact
            )
            message: str = (
                "No matching contacts found in your graph for that question."
                if has_filters
                else (
                    "Could not translate that question into specific filters. "
                    "Try asking about a person by name, a company, a role, or a category "
                    "(e.g. 'show me VCs', 'who works at Stripe', 'find engineers')."
                )
            )
            return QueryNetworkResult(
                question=question,
                matches=[],
                second_degree_matches=[],
                applied_plan=plan,
                message=message,
                system_messages=system_messages,
            )

        parts: list[str] = []
        if matches:
            parts.append(f"{len(matches)} direct contact(s)")
        if second_degree:
            parts.append(f"{len(second_degree)} contact(s) via trusted connections")
        return QueryNetworkResult(
            question=question,
            matches=matches,
            second_degree_matches=second_degree,
            applied_plan=plan,
            message=f"Found {' and '.join(parts)}.",
            system_messages=system_messages,
        )


async def describe_graph(
    ctx: AppContext,
    user_id: UUID | None,
) -> DescribeGraphResult:
    if user_id is None:
        return DescribeGraphResult(
            message="Authentication required. Provide a Bearer token.",
        )

    async with ctx.session_factory() as db:
        sources: SourceService = build_source_service(db)
        if not await sources.user_has_queryable_graph(user_id):
            return DescribeGraphResult(
                message=(
                    "Sync still running or not started. Call sync_source, then "
                    "get_source_status until sync_state is partial or complete."
                ),
            )

        result: DescribeGraphResult = await GraphSummaryService(db).describe(user_id)
        try:
            trust_svc = TrustListService(db, ctx.settings.base_url)
            result.system_messages = await trust_svc.get_system_messages(user_id)
        except Exception:
            pass
        return result


async def get_target_companies(
    ctx: AppContext,
    user_id: UUID | None,
) -> TargetCompaniesResult:
    if user_id is None:
        return TargetCompaniesResult(
            message="Authentication required. Provide a Bearer token.",
        )

    async with ctx.session_factory() as db:
        sources: SourceService = build_source_service(db)
        if not await sources.user_has_queryable_graph(user_id):
            return TargetCompaniesResult(
                message=(
                    "Sync still running or not started. Complete onboarding and enrichment first."
                ),
            )

        dedup_service: PersonDedupService = PersonDedupService(db)
        await dedup_service.dedup_for_user(user_id)
        recompute: PersonProfileRecompute = PersonProfileRecompute(db)
        await recompute.recompute_for_user(user_id)
        await db.commit()

        service = TargetCompaniesService(db)
        matches: list[TargetCompanyMatch] = await service.list_first_degree(user_id)
        companies: list[TargetCompanySummary] = [
            TargetCompanySummary(
                org_id=match.org_id,
                org_name=match.org_name,
                best_trust_score=match.best_trust_score,
                insiders=[
                    TargetCompanyInsiderSummary(
                        person_id=insider.person_id,
                        person_name=insider.person_name,
                        person_role=insider.person_role,
                        trust_score=insider.trust_score,
                        relationship_kind=insider.relationship_kind,
                    )
                    for insider in match.insiders
                ],
            )
            for match in matches
        ]
        return TargetCompaniesResult(
            companies=companies,
            message=f"Found {len(companies)} companies with high-trust connections.",
        )


async def get_second_degree_target_companies(
    ctx: AppContext,
    user_id: UUID | None,
) -> SecondDegreeTargetCompaniesResult:
    if user_id is None:
        return SecondDegreeTargetCompaniesResult(
            message="Authentication required. Provide a Bearer token.",
        )

    async with ctx.session_factory() as db:
        trust_svc = TrustListService(db, ctx.settings.base_url)
        member_ids: list[UUID] = await trust_svc.get_trust_member_user_ids(user_id)
        if not member_ids:
            return SecondDegreeTargetCompaniesResult(
                message="Add trusted friends on the Trust List to unlock second-degree companies.",
            )

        private_by_member: dict[UUID, set[UUID]] = {}
        for member_id in member_ids:
            private_by_member[member_id] = await trust_svc.get_private_person_ids(member_id)

        service = TargetCompaniesService(db)
        matches: list[SecondDegreeTargetCompanyMatch] = await service.list_second_degree(
            user_id,
            member_ids,
            private_person_ids_by_member=private_by_member,
        )
        companies: list[SecondDegreeTargetCompanySummary] = [
            SecondDegreeTargetCompanySummary(
                org_id=match.org_id,
                org_name=match.org_name,
                best_trust_score=match.best_trust_score,
                insiders=[
                    SecondDegreeTargetInsiderSummary(
                        person_id=insider.person_id,
                        person_name=insider.person_name,
                        person_role=insider.person_role,
                        bridge_user_id=insider.bridge_user_id,
                        bridge_name=insider.bridge_name,
                        trust_score=insider.trust_score,
                    )
                    for insider in match.insiders
                ],
            )
            for match in matches
        ]
        return SecondDegreeTargetCompaniesResult(
            companies=companies,
            message=f"Found {len(companies)} companies via trusted friends' networks.",
        )


async def view_trusted_users(
    ctx: AppContext,
    user_id: UUID | None,
) -> ViewTrustedUsersResult:
    if user_id is None:
        return ViewTrustedUsersResult(
            message="Authentication required. Provide a Bearer token.",
        )

    async with ctx.session_factory() as db:
        trust_svc = TrustListService(db, ctx.settings.base_url)
        return await trust_svc.view(user_id)


async def edit_trusted_users(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    accept: list[str] | None = None,
    decline: list[str] | None = None,
    set_privacy: list[dict[str, str]] | None = None,
) -> EditTrustedUsersResult:
    if user_id is None:
        return EditTrustedUsersResult(
            message="Authentication required. Provide a Bearer token.",
        )

    async with ctx.session_factory() as db:
        trust_svc = TrustListService(db, ctx.settings.base_url)
        result: EditTrustedUsersResult = await trust_svc.edit(
            user_id,
            add=add,
            remove=remove,
            accept=accept,
            decline=decline,
            set_privacy=set_privacy,
        )
        await db.commit()
        return result


async def poll_connect(
    ctx: AppContext,
    *,
    connect_session_id: UUID,
    poll_secret: str,
) -> PollConnectResult:
    async with ctx.session_factory() as db:
        session: ConnectSession | None = await db.get(ConnectSession, connect_session_id)
        if session is None:
            raise ValueError(f"Unknown connect_session_id: {connect_session_id}")
        if not verify_poll_secret(session, poll_secret):
            raise ValueError("Invalid poll credentials")

        status: str = session.status
        if status == SessionStatus.PENDING.value:
            return PollConnectResult(
                status="pending",
                message="Waiting for user to complete OAuth in their browser...",
            )

        if status == SessionStatus.FAILED.value:
            return PollConnectResult(status="failed", message="OAuth flow failed.")

        if session.user_id is None:
            return PollConnectResult(
                status="pending",
                message="OAuth callback received but user not yet created.",
            )

        if session.token_dispensed_at is not None:
            return PollConnectResult(
                status="connected",
                message="Tokens already dispensed. Use refresh_token to get new access tokens via POST /oauth/token.",
            )

        user: User | None = await db.get(User, session.user_id)
        email: str | None = user.email if user else None

        token_response = await build_oauth_server_service(db, ctx).mint_tokens_for_user(
            session.user_id, email=email
        )

        session.token_dispensed_at = datetime.now(tz=UTC)
        await db.commit()

        return PollConnectResult(
            status="connected",
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            email=email,
            message="Connected! Use the access_token as your Bearer token.",
        )


async def list_people(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    network_only: bool = True,
    include_shared: bool = True,
) -> ListPeopleResult:
    if user_id is None:
        return ListPeopleResult(
            people=[],
            total=0,
            strong_tie_count=0,
            enriched_count=0,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        service: ContactsService = ContactsService(db)
        return await service.list_people(
            user_id, network_only=network_only, include_shared=include_shared
        )


async def list_strong_ties(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    limit: int | None = None,
) -> ListStrongTiesResult:
    if user_id is None:
        return ListStrongTiesResult(message="Authentication required.")
    async with ctx.session_factory() as db:
        service = StrongTieApiService(db, ctx.settings)
        return await service.list_strong_ties(user_id, limit=limit)


async def count_strong_ties(
    ctx: AppContext,
    user_id: UUID | None,
) -> StrongTieCountResult:
    if user_id is None:
        return StrongTieCountResult(message="Authentication required.")
    async with ctx.session_factory() as db:
        service = StrongTieApiService(db, ctx.settings)
        return await service.count_strong_ties(user_id)


async def list_strong_tie_companies(
    ctx: AppContext,
    user_id: UUID | None,
) -> StrongTieCompaniesResult:
    if user_id is None:
        return StrongTieCompaniesResult(message="Authentication required.")
    async with ctx.session_factory() as db:
        service = StrongTieApiService(db, ctx.settings)
        return await service.list_companies(user_id)


async def enrich_strong_ties(
    ctx: AppContext,
    user_id: UUID | None,
) -> EnrichStrongTiesResult:
    if user_id is None:
        return EnrichStrongTiesResult(message="Authentication required.")
    async with ctx.session_factory() as db:
        service = StrongTieApiService(db, ctx.settings)
        result = await service.enrich_strong_ties(user_id)
        await db.commit()
        return result


async def get_scrapingdog_enrichment_status(
    ctx: AppContext,
    user_id: UUID | None,
) -> ScrapingDogEnrichmentStatusResult:
    if user_id is None:
        return ScrapingDogEnrichmentStatusResult(
            state="idle",
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        service = StrongTieApiService(db, ctx.settings)
        return await service.scrapingdog_status(user_id)


async def get_network_status(
    ctx: AppContext,
    user_id: UUID | None,
) -> NetworkStatusResult:
    if user_id is None:
        return NetworkStatusResult(message="Authentication required.")
    async with ctx.session_factory() as db:
        service = StrongTieApiService(db, ctx.settings)
        return await service.network_status(user_id)


async def get_person(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    person_id: str,
) -> PersonDetailResult:
    if user_id is None:
        raise ValueError("Authentication required")
    parsed_id: UUID = UUID(person_id)
    async with ctx.session_factory() as db:
        service: ContactsService = ContactsService(db)
        detail: PersonDetailResult | None = await service.get_person(user_id, parsed_id)
        if detail is None:
            raise ValueError(f"Person not found: {person_id}")
        return detail


async def update_person(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    body: UpdatePersonRequest,
) -> PersonDetailResult:
    if user_id is None:
        raise ValueError("Authentication required")
    async with ctx.session_factory() as db:
        service: ContactsService = ContactsService(db)
        detail: PersonDetailResult | None = await service.update_person(user_id, body)
        if detail is None:
            raise ValueError(f"Person not found: {body.person_id}")
        await db.commit()
        return detail


async def enrich_person(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    person_id: str,
) -> EnrichPersonResult:
    if user_id is None:
        raise ValueError("Authentication required")
    parsed_id: UUID = UUID(person_id)
    async with ctx.session_factory() as db:
        from contactsafe_server.services.enrichment_queue_service import enqueue_enrichment

        await enqueue_enrichment(
            db,
            ctx.settings,
            person_id=parsed_id,
            trigger_user_id=user_id,
        )
        await db.commit()

        from contactsafe_server.services.contact_enrichment_worker import ContactEnrichmentWorker
        from contactsafe_server.db.models import EnrichmentQueueItem

        item: EnrichmentQueueItem | None = (
            await db.execute(
                select(EnrichmentQueueItem).where(
                    EnrichmentQueueItem.person_id == parsed_id,
                    EnrichmentQueueItem.status == "pending",
                ).order_by(EnrichmentQueueItem.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()

        if item is None:
            return EnrichPersonResult(message="No enrichment needed.", queued=False)

        await db.commit()

        worker = ContactEnrichmentWorker(db, ctx.settings)
        refreshed: EnrichmentQueueItem | None = await db.get(EnrichmentQueueItem, item.id)
        if refreshed is not None:
            await worker.enrich_one(refreshed, skip_org_rebuild=True)

        return EnrichPersonResult(message="Enrichment complete.", queued=True)


async def list_orgs(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    include_shared: bool = True,
) -> ListOrgsResult:
    if user_id is None:
        return ListOrgsResult(
            orgs=[],
            total=0,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        service: ContactsService = ContactsService(db)
        return await service.list_orgs(user_id, include_shared=include_shared)


async def get_org(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    org_id: str,
) -> OrgDetailResult:
    if user_id is None:
        raise ValueError("Authentication required")
    parsed_id: UUID = UUID(org_id)
    async with ctx.session_factory() as db:
        service: ContactsService = ContactsService(db)
        detail: OrgDetailResult | None = await service.get_org(user_id, parsed_id)
        if detail is None:
            raise ValueError(f"Organization not found: {org_id}")
        return detail


async def update_org(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    body: UpdateOrgRequest,
) -> OrgDetailResult:
    if user_id is None:
        raise ValueError("Authentication required")
    async with ctx.session_factory() as db:
        service: ContactsService = ContactsService(db)
        detail: OrgDetailResult | None = await service.update_org(user_id, body)
        if detail is None:
            raise ValueError(f"Organization not found: {body.org_id}")
        await db.commit()
        return detail


async def enrich_orgs(ctx: AppContext, user_id: UUID | None) -> EnrichOrgsResult:
    if user_id is None:
        return EnrichOrgsResult(
            scheduled=False,
            state="failed",
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_server.services.org_enrichment_service import OrgEnrichmentService

        service = OrgEnrichmentService(db, ctx.settings)
        result = await service.start_enrichment(user_id)
        await db.commit()
        return result


async def get_org_enrichment_status(
    ctx: AppContext,
    user_id: UUID | None,
) -> OrgEnrichmentStatusResult:
    if user_id is None:
        return OrgEnrichmentStatusResult(
            state="failed",
            orgs_total=0,
            orgs_enriched=0,
            error="Authentication required.",
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_server.services.org_enrichment_service import OrgEnrichmentService

        service = OrgEnrichmentService(db, ctx.settings)
        return await service.get_status(user_id)


async def cancel_org_enrichment(
    ctx: AppContext,
    user_id: UUID | None,
) -> CancelOrgEnrichmentResult:
    if user_id is None:
        return CancelOrgEnrichmentResult(
            cancelled=False,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_server.services.org_enrichment_service import OrgEnrichmentService

        service = OrgEnrichmentService(db, ctx.settings)
        result = await service.cancel_enrichment(user_id)
        await db.commit()
        return result


async def dedup_persons(
    ctx: AppContext,
    user_id: UUID | None,
) -> DedupPersonsResult:
    if user_id is None:
        raise ValueError("Authentication required. Provide a Bearer token.")
    async with ctx.session_factory() as db:
        service: PersonDedupService = PersonDedupService(db)
        result: DedupPersonsResult = await service.dedup_for_user(user_id)
        await db.commit()
        return result


async def list_org_lists(
    ctx: AppContext,
    user_id: UUID | None,
) -> ListOrgListsResult:
    if user_id is None:
        return ListOrgListsResult(lists=[], message="Authentication required.")
    async with ctx.session_factory() as db:
        service: OrgListService = OrgListService(db)
        return await service.list_org_lists(user_id)


async def create_org_list(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    body: CreateOrgListRequest,
) -> CreateOrgListResult:
    if user_id is None:
        raise ValueError("Authentication required.")
    async with ctx.session_factory() as db:
        service: OrgListService = OrgListService(db)
        result: CreateOrgListResult = await service.create_org_list(
            user_id,
            name=body.name,
        )
        await db.commit()
        return result


async def rename_org_list(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    body: RenameOrgListRequest,
) -> RenameOrgListResult:
    if user_id is None:
        raise ValueError("Authentication required.")
    async with ctx.session_factory() as db:
        service: OrgListService = OrgListService(db)
        result: RenameOrgListResult = await service.rename_org_list(
            user_id,
            list_id=UUID(body.list_id),
            name=body.name,
        )
        await db.commit()
        return result


async def delete_org_list(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    body: DeleteOrgListRequest,
) -> DeleteOrgListResult:
    if user_id is None:
        raise ValueError("Authentication required.")
    async with ctx.session_factory() as db:
        service: OrgListService = OrgListService(db)
        result: DeleteOrgListResult = await service.delete_org_list(
            user_id,
            list_id=UUID(body.list_id),
        )
        await db.commit()
        return result


async def add_orgs_to_list(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    body: ModifyOrgListMembershipRequest,
) -> ModifyOrgListMembershipResult:
    if user_id is None:
        raise ValueError("Authentication required.")
    async with ctx.session_factory() as db:
        service: OrgListService = OrgListService(db)
        result: ModifyOrgListMembershipResult = await service.add_orgs_to_list(
            user_id,
            list_id=UUID(body.list_id),
            org_ids=[UUID(org_id) for org_id in body.org_ids],
        )
        await db.commit()

        # If the list is the user's job monitor list, immediately scrape new orgs
        from contactsafe_server.config import get_settings
        from contactsafe_server.db.models import User

        from sqlalchemy import select

        user_row = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if (
            user_row is not None
            and user_row.job_monitor_list_id is not None
            and str(user_row.job_monitor_list_id) == body.list_id
            and get_settings().use_arq_worker
        ):
            from contactsafe_server.queue import enqueue_background_job

            for org_id_str in body.org_ids:
                await enqueue_background_job(
                    "scrape_org_jobs",
                    org_id_str,
                    force=True,
                    trigger_user_id=str(user_id),
                    _job_id=f"scrape-org-{org_id_str}",
                )

        return result


async def remove_orgs_from_list(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    body: ModifyOrgListMembershipRequest,
) -> ModifyOrgListMembershipResult:
    if user_id is None:
        raise ValueError("Authentication required.")
    async with ctx.session_factory() as db:
        service: OrgListService = OrgListService(db)
        result: ModifyOrgListMembershipResult = await service.remove_orgs_from_list(
            user_id,
            list_id=UUID(body.list_id),
            org_ids=[UUID(org_id) for org_id in body.org_ids],
        )
        await db.commit()
        return result


async def add_watched_company(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    body: AddWatchedCompanyRequest,
) -> AddWatchedCompanyResult:
    """Create/resolve an org by name (+ optional website) and add it to Job Prospects."""
    if user_id is None:
        raise ValueError("Authentication required.")

    name: str = body.name.strip()
    if not name:
        return AddWatchedCompanyResult(
            org_id=None,
            name="",
            added=False,
            message="Company name is required.",
        )

    domain: str | None = _normalize_website_to_domain(body.website)

    async with ctx.session_factory() as db:
        resolver: EntityResolver = EntityResolver(db)
        org: Org | None = await resolver.resolve_org(domain=domain, name=name)
        if org is None:
            return AddWatchedCompanyResult(
                org_id=None,
                name=name,
                added=False,
                message=(
                    f"\"{name}\" does not look like a real company "
                    "(e.g. Self Employed, Stealth Startup)."
                ),
            )

        if domain is not None and org.primary_domain is None:
            org.primary_domain = domain
            existing_alias = await db.execute(
                select(OrgAlias.id).where(
                    OrgAlias.kind == "domain",
                    OrgAlias.value == domain,
                ),
            )
            if existing_alias.scalar_one_or_none() is None:
                db.add(OrgAlias(org_id=org.id, kind="domain", value=domain))
            await db.flush()

        # Apply user-supplied metadata as hints. Only fill fields the org does
        # not already have so we never clobber existing/enriched data; a later
        # enrichment run may still refine these with authoritative values.
        industry_tags: list[str] = [
            tag.strip() for tag in body.industry_tags if tag.strip()
        ]
        if industry_tags and not org.categories:
            org.categories = industry_tags
        if body.company_size_band is not None and org.company_size_band is None:
            band: str = body.company_size_band.strip()
            if band:
                org.company_size_band = band
        if body.employee_count is not None and org.employee_count is None:
            if body.employee_count > 0:
                org.employee_count = body.employee_count
        await db.flush()

        list_service: OrgListService = OrgListService(db)
        existing_list_result = await db.execute(
            select(OrgList).where(
                OrgList.user_id == user_id,
                OrgList.name == JOB_PROSPECTS_LIST_NAME,
            ),
        )
        org_list: OrgList | None = existing_list_result.scalar_one_or_none()
        list_id: UUID
        if org_list is None:
            created: CreateOrgListResult = await list_service.create_org_list(
                user_id,
                name=JOB_PROSPECTS_LIST_NAME,
            )
            list_id = created.list_id
        else:
            list_id = org_list.id

        membership: ModifyOrgListMembershipResult = await list_service.add_orgs_to_list(
            user_id,
            list_id=list_id,
            org_ids=[org.id],
        )
        await db.commit()

        from contactsafe_server.config import get_settings

        if get_settings().use_arq_worker:
            from contactsafe_server.queue import enqueue_background_job

            org_id_str: str = str(org.id)
            await enqueue_background_job(
                "enrich_org",
                org_id_str,
                _job_id=f"enrich-org-{org_id_str}",
            )
            await enqueue_background_job(
                "scrape_org_jobs",
                org_id_str,
                force=True,
                trigger_user_id=str(user_id),
                _job_id=f"scrape-org-{org_id_str}",
            )

        already_on_list: bool = membership.affected_count == 0
        message: str
        if already_on_list:
            message = f"\"{org.canonical_name}\" is already on your job search list."
        else:
            message = (
                f"Watching \"{org.canonical_name}\". "
                "Jobs will appear after the next scan."
            )
        return AddWatchedCompanyResult(
            org_id=org.id,
            name=org.canonical_name,
            added=True,
            message=message,
        )


async def get_job_monitor_config(
    ctx: AppContext,
    user_id: UUID | None,
) -> JobMonitorConfigResult:
    if user_id is None:
        return JobMonitorConfigResult(
            enabled=False,
            list_id=None,
            list_name=None,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_server.services.job_discovery_service import JobDiscoveryService

        service = JobDiscoveryService(db, ctx.settings)
        return await service.get_monitor_config(user_id)


async def set_job_monitor_config(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    body: SetJobMonitorConfigRequest,
) -> JobMonitorConfigResult:
    if user_id is None:
        raise ValueError("Authentication required.")
    async with ctx.session_factory() as db:
        from contactsafe_server.services.job_discovery_service import JobDiscoveryService

        service = JobDiscoveryService(db, ctx.settings)
        result: JobMonitorConfigResult = await service.set_monitor_config(user_id, body)
        await db.commit()

        # When monitoring is enabled, immediately enqueue scrapes for unscraped orgs
        from contactsafe_server.config import get_settings

        if result.enabled and result.list_id and get_settings().use_arq_worker:
            from contactsafe_server.queue import enqueue_background_job

            orgs_needing: list[UUID] = await service.collect_orgs_needing_scrape()
            for org_id in orgs_needing:
                await enqueue_background_job(
                    "scrape_org_jobs",
                    str(org_id),
                    force=False,
                    trigger_user_id=str(user_id),
                    _job_id=f"scrape-org-{org_id}",
                )

        return result


async def get_job_scan_status(
    ctx: AppContext,
    user_id: UUID | None,
) -> JobScanStatusResult:
    if user_id is None:
        return JobScanStatusResult(
            scanned=0,
            total=0,
            scanning_active=False,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_server.services.job_discovery_service import JobDiscoveryService

        service = JobDiscoveryService(db, ctx.settings)
        return await service.get_scan_status(user_id)


async def start_single_org_job_discovery(
    ctx: AppContext,
    user_id: UUID | None,
    org_id: UUID,
) -> "StartSingleOrgDiscoveryResult":
    from contactsafe_core.contact_schemas import StartSingleOrgDiscoveryResult

    if user_id is None:
        return StartSingleOrgDiscoveryResult(
            scheduled=False,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_server.services.job_discovery_service import JobDiscoveryService

        service = JobDiscoveryService(db, ctx.settings)
        return await service.discover_single_org(user_id, org_id)


async def list_org_jobs(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    relevant_only: bool = False,
) -> ListOrgJobsResult:
    if user_id is None:
        return ListOrgJobsResult(
            companies=[],
            total_jobs=0,
            total_relevant=0,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_server.services.job_discovery_service import JobDiscoveryService

        service = JobDiscoveryService(db, ctx.settings)
        return await service.list_jobs_for_user(user_id, relevant_only=relevant_only)


async def list_flat_jobs(
    ctx: AppContext,
    user_id: UUID | None,
) -> FlatJobListResult:
    if user_id is None:
        return FlatJobListResult(
            jobs=[],
            total_jobs=0,
            total_relevant=0,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_server.services.job_discovery_service import JobDiscoveryService

        service = JobDiscoveryService(db, ctx.settings)
        return await service.list_flat_jobs_for_user(user_id)


async def get_job_detail(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    job_id: UUID,
) -> JobDetailResult:
    if user_id is None:
        raise ValueError("Authentication required.")
    async with ctx.session_factory() as db:
        from contactsafe_server.services.job_discovery_service import JobDiscoveryService

        service = JobDiscoveryService(db, ctx.settings)
        result: JobDetailResult | None = await service.get_job_detail(user_id, job_id)
        if result is None:
            raise ValueError("Job not found.")
        return result


async def get_job_preferences(
    ctx: AppContext,
    user_id: UUID | None,
) -> JobPreferencesResult:
    if user_id is None:
        return JobPreferencesResult(text=None, classified_job_count=0, message="Authentication required.")
    async with ctx.session_factory() as db:
        from contactsafe_server.db.models import User, UserJobRelevance

        user: User | None = await db.get(User, user_id)
        if user is None:
            return JobPreferencesResult(text=None, classified_job_count=0, message="User not found.")
        from sqlalchemy import func, select

        count_result = await db.execute(
            select(func.count()).select_from(UserJobRelevance).where(UserJobRelevance.user_id == user_id),
        )
        count: int = count_result.scalar() or 0
        raw_scope: dict | None = user.job_target_scope
        target_scope: JobTargetScope | None = None
        if raw_scope is not None:
            target_scope = JobTargetScope(
                industry_tags=list(raw_scope.get("industry_tags") or []),
                sharer_names=list(raw_scope.get("sharer_names") or []),
                size_bands=list(raw_scope.get("size_bands") or []),
            )
        return JobPreferencesResult(
            text=user.job_preferences_text,
            suggested_text=user.job_suggested_roles,
            location_pref=user.job_location_pref,
            location_city=user.job_location_city,
            commute_max_minutes=user.job_commute_max_minutes,
            commute_note=user.job_commute_note,
            target_scope=target_scope,
            classified_job_count=count,
            message="OK",
        )


async def set_job_preferences(
    ctx: AppContext,
    user_id: UUID | None,
    text: str,
    location_pref: str | None = None,
    location_city: str | None = None,
    commute_max_minutes: int | None = None,
    commute_note: str | None = None,
) -> JobPreferencesResult:
    if user_id is None:
        return JobPreferencesResult(text=None, classified_job_count=0, message="Authentication required.")
    async with ctx.session_factory() as db:
        from contactsafe_server.db.models import User

        user: User | None = await db.get(User, user_id)
        if user is None:
            return JobPreferencesResult(text=None, classified_job_count=0, message="User not found.")
        user.job_preferences_text = text.strip() or None
        user.job_location_pref = location_pref
        user.job_location_city = location_city.strip() if location_city else None
        user.job_commute_max_minutes = commute_max_minutes
        user.job_commute_note = commute_note.strip() if commute_note else None
        suggested_text: str | None = user.job_suggested_roles
        await db.commit()

    import asyncio

    from contactsafe_server.services.job_relevance_service import cancel_scoring

    cancel_scoring(user_id)

    from contactsafe_server.config import get_settings
    from contactsafe_server.queue import enqueue_background_job

    if get_settings().use_arq_worker:
        await enqueue_background_job(
            "score_jobs_for_user",
            str(user_id),
            reclassify=True,
            _job_id=f"score-user-{user_id}",
        )
    else:

        async def _reclassify_background() -> None:
            async with ctx.session_factory() as bg_db:
                from contactsafe_server.services.job_relevance_service import JobRelevanceService

                svc = JobRelevanceService(bg_db, ctx.settings)
                await svc.reclassify_all(user_id)

        asyncio.ensure_future(_reclassify_background())

    return JobPreferencesResult(
        text=text.strip() or None,
        suggested_text=suggested_text,
        location_pref=location_pref,
        location_city=location_city.strip() if location_city else None,
        commute_max_minutes=commute_max_minutes,
        commute_note=commute_note.strip() if commute_note else None,
        classified_job_count=0,
        message="Preferences saved. Rescoring jobs in background…",
    )


async def set_job_target_scope(
    ctx: AppContext,
    user_id: UUID | None,
    target_scope: JobTargetScope,
) -> JobPreferencesResult:
    if user_id is None:
        return JobPreferencesResult(text=None, classified_job_count=0, message="Authentication required.")
    async with ctx.session_factory() as db:
        from contactsafe_server.db.models import User

        user: User | None = await db.get(User, user_id)
        if user is None:
            return JobPreferencesResult(text=None, classified_job_count=0, message="User not found.")
        user.job_target_scope = {
            "industry_tags": target_scope.industry_tags,
            "sharer_names": target_scope.sharer_names,
            "size_bands": target_scope.size_bands,
        }
        await db.commit()

    return await get_job_preferences(ctx, user_id)


async def get_notification_preferences(
    ctx: AppContext,
    user_id: UUID | None,
) -> NotificationPreferencesResult:
    if user_id is None:
        return NotificationPreferencesResult(
            job_digest_frequency="off",
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_core.enums import JobDigestFrequency
        from contactsafe_server.db.models import User

        user: User | None = await db.get(User, user_id)
        if user is None:
            return NotificationPreferencesResult(
                job_digest_frequency="off",
                message="User not found.",
            )
        frequency: str = user.job_digest_frequency
        if frequency not in {item.value for item in JobDigestFrequency}:
            frequency = JobDigestFrequency.DAILY
        return NotificationPreferencesResult(
            job_digest_frequency=cast(Literal["daily", "weekly", "off"], frequency),
            message="OK",
        )


async def set_notification_preferences(
    ctx: AppContext,
    user_id: UUID | None,
    frequency: str,
) -> NotificationPreferencesResult:
    if user_id is None:
        return NotificationPreferencesResult(
            job_digest_frequency="off",
            message="Authentication required.",
        )
    from contactsafe_core.enums import JobDigestFrequency

    if frequency not in {item.value for item in JobDigestFrequency}:
        return NotificationPreferencesResult(
            job_digest_frequency="off",
            message="Invalid digest frequency.",
        )

    async with ctx.session_factory() as db:
        from contactsafe_server.db.models import User

        user: User | None = await db.get(User, user_id)
        if user is None:
            return NotificationPreferencesResult(
                job_digest_frequency="off",
                message="User not found.",
            )
        user.job_digest_frequency = frequency
        await db.commit()

    return await get_notification_preferences(ctx, user_id)


async def get_next_steps(
    ctx: AppContext,
    user_id: UUID | None,
) -> NextStepsResult:
    if user_id is None:
        return NextStepsResult(tasks=[], message="Authentication required.")
    async with ctx.session_factory() as db:
        from contactsafe_server.services.next_steps_service import NextStepsService

        service = NextStepsService(db)
        return await service.get_next_steps(user_id)


async def update_task_status(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    dedup_key: str,
    status: Literal["done", "skipped"],
) -> UpdateTaskStatusResult:
    if user_id is None:
        return UpdateTaskStatusResult(
            dedup_key=dedup_key,
            status="open",
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_server.services.next_steps_service import NextStepsService

        service = NextStepsService(db)
        try:
            return await service.update_task_status(
                user_id,
                dedup_key=dedup_key,
                status=status,
            )
        except ValueError as exc:
            return UpdateTaskStatusResult(
                dedup_key=dedup_key,
                status="open",
                message=str(exc),
            )


async def set_job_interest(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    job_id: UUID,
    interest: Literal["interested", "dismissed"],
) -> SetJobInterestResult:
    if user_id is None:
        return SetJobInterestResult(
            job_id=job_id,
            interest=interest,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        from contactsafe_server.services.next_steps_service import NextStepsService

        service = NextStepsService(db)
        try:
            await service.set_job_interest(user_id, job_id=job_id, interest=interest)
        except ValueError as exc:
            return SetJobInterestResult(
                job_id=job_id,
                interest=interest,
                message=str(exc),
            )
    return SetJobInterestResult(job_id=job_id, interest=interest, message="OK")
