"""Shared action functions backing both MCP tools and the REST API.

Each function accepts an ``AppContext`` and an already-resolved ``user_id``
(or ``None`` when unauthenticated) so callers only differ in *how* they
obtain those two values.
"""

from __future__ import annotations

import logging
from uuid import UUID

from datetime import UTC, datetime

from contactsafe_core.contact_schemas import (
    DedupPersonsResult,
    ListOrgsResult,
    ListPeopleResult,
    OrgDetailResult,
    PersonDetailResult,
)
from datetime import date

from contactsafe_core.enums import SessionStatus, SourceType, EnrichmentRunState, SyncState
from contactsafe_core.schemas import (
    ConnectSourceResult,
    DescribeGraphResult,
    EditTrustedUsersResult,
    EnrichmentStatusResult,
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
    ViewTrustedUsersResult,
)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.db.models import ConnectSession, EmploymentClaim, Org, PersonAttributeClaim, Source, User
from contactsafe_server.services.claim_writer import record_employment
from contactsafe_server.services.entity_resolution import EntityResolver
from contactsafe_server.services.person_profile_recompute import PersonProfileRecompute
from contactsafe_server.services.user_person_service import ensure_user_person
from contactsafe_server.deps import (
    AppContext,
    build_oauth_server_service,
    build_oauth_service,
    build_enrichment_service,
    build_source_service,
)
from contactsafe_server.services.contacts_service import ContactsService
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
from contactsafe_server.services.trust_list_service import TrustListService
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
                    resolved_uid
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
        return await sources.list_sources_for_user(user_id)


async def get_source_status(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    source_id: str | None = None,
) -> SourceStatusResult:
    async with ctx.session_factory() as db:
        sources: SourceService = build_source_service(db)
        if source_id is not None:
            source_uuid: UUID = parse_source_id(source_id)
            return await sources.get_source_status(source_uuid)
        elif user_id is not None:
            return await sources.get_source_status_for_user(user_id)
        else:
            raise ValueError("Authentication required (Bearer token) or provide source_id")


async def sync_source(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    source_id: str | None = None,
) -> SyncSourceResult:
    async with ctx.session_factory() as db:
        sources: SourceService = build_source_service(db)
        if source_id is not None:
            source_uuid: UUID = parse_source_id(source_id)
            result: SyncSourceResult = await sources.request_sync(source_uuid)
        elif user_id is not None:
            result = await sources.request_sync_for_user(user_id)
        else:
            raise ValueError("Authentication required (Bearer token) or provide source_id")
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
        return UserProfileResult(
            email=user.email,
            display_name=user.display_name or user.google_profile_name,
            headline=headline,
            location=user.location,
            google_profile_name=user.google_profile_name,
            experiences=experiences,
            message="User profile loaded.",
        )


async def update_user_profile(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    display_name: str | None = None,
    location: str | None = None,
) -> UserProfileResult:
    if user_id is None:
        return UserProfileResult(message="Authentication required. Provide a Bearer token.")
    async with ctx.session_factory() as db:
        user: User | None = await db.get(User, user_id)
        if user is None:
            return UserProfileResult(message="User not found.")
        if display_name is not None:
            cleaned_name: str = display_name.strip()
            user.display_name = cleaned_name or None
        if location is not None:
            cleaned_location: str = location.strip()
            user.location = cleaned_location or None
        await db.commit()
        await db.refresh(user)
        return UserProfileResult(
            email=user.email,
            display_name=user.display_name or user.google_profile_name,
            location=user.location,
            google_profile_name=user.google_profile_name,
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


async def upload_source(
    ctx: AppContext,
    user_id: UUID | None,
    *,
    source_type: str,
    filename: str,
    content: str,
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

        source.upload_payload = {"filename": filename, "content": content}
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
) -> PollConnectResult:
    async with ctx.session_factory() as db:
        session: ConnectSession | None = await db.get(ConnectSession, connect_session_id)
        if session is None:
            raise ValueError(f"Unknown connect_session_id: {connect_session_id}")

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

        token_response = await build_oauth_server_service(db, ctx).mint_tokens_for_user(
            session.user_id
        )
        session.token_dispensed_at = datetime.now(tz=UTC)
        await db.commit()

        user: User | None = await db.get(User, session.user_id)
        email: str | None = user.email if user else None

        return PollConnectResult(
            status="connected",
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            email=email,
            message="Connected! Use the access_token as your Bearer token.",
        )


async def list_people(ctx: AppContext, user_id: UUID | None) -> ListPeopleResult:
    if user_id is None:
        return ListPeopleResult(
            people=[],
            total=0,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        service: ContactsService = ContactsService(db)
        return await service.list_people(user_id)


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


async def list_orgs(ctx: AppContext, user_id: UUID | None) -> ListOrgsResult:
    if user_id is None:
        return ListOrgsResult(
            orgs=[],
            total=0,
            message="Authentication required.",
        )
    async with ctx.session_factory() as db:
        service: ContactsService = ContactsService(db)
        return await service.list_orgs(user_id)


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
