"""Daily/weekly job-match email digest builder and sender."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.enums import JobDigestFrequency
from contactsafe_server.config import Settings
from contactsafe_server.db.models import Org, OrgJob, User, UserJobRelevance
from contactsafe_server.services.email_service import EmailService, EmailSendResult
from contactsafe_server.services.jwt_service import JWTService

logger: logging.Logger = logging.getLogger(__name__)

_templates_dir: Path = Path(__file__).resolve().parents[1] / "templates" / "email"
_templates: Jinja2Templates = Jinja2Templates(directory=str(_templates_dir))


@dataclass(frozen=True, slots=True)
class DigestJobEntry:
    job_id: uuid.UUID
    org_id: uuid.UUID
    title: str
    company_name: str
    location: str | None
    match_score: int
    url: str
    classified_at: datetime
    contact_blurb: str | None = None


@dataclass(frozen=True, slots=True)
class DigestCompanyGroup:
    company_name: str
    jobs: tuple[DigestJobEntry, ...]
    contact_blurb: str | None = None


@dataclass(frozen=True, slots=True)
class DigestBuildResult:
    jobs: tuple[DigestJobEntry, ...]
    total_new_matches: int


@dataclass(frozen=True, slots=True)
class DigestSendResult:
    sent: bool
    job_count: int
    message: str


def digest_watermark(user: User) -> datetime:
    if user.job_digest_last_sent_at is not None:
        return user.job_digest_last_sent_at
    return user.created_at


def is_user_due_for_digest(
    user: User,
    *,
    now: datetime,
    send_hour_utc: int,
) -> bool:
    if not user.job_monitor_enabled:
        return False
    if user.job_digest_frequency == JobDigestFrequency.OFF:
        return False
    if now.hour != send_hour_utc:
        return False

    watermark: datetime = digest_watermark(user)
    if user.job_digest_frequency == JobDigestFrequency.WEEKLY:
        return now - watermark >= timedelta(days=7)
    return now - watermark >= timedelta(days=1)


def _build_contact_blurb(
    *,
    own_summary: tuple[str, int] | None,
    shared_summary: tuple[str, str, int] | None,
) -> str | None:
    """Build a human-readable contact line like "Phil T., friend of Cynthia, and 2 others"."""
    parts: list[str] = []
    total_extra: int = 0

    if own_summary is not None:
        name, count = own_summary
        parts.append(name)
        total_extra += count - 1

    if shared_summary is not None:
        shared_name, bridge_name, shared_count = shared_summary
        parts.append(f"{shared_name}, friend of {bridge_name}")
        total_extra += shared_count - 1

    if not parts:
        return None

    blurb: str = parts[0]
    if len(parts) > 1:
        blurb = f"{parts[0]}, {parts[1]}"
        # first part already consumed 1, second consumed 1 — extras accounted for above

    if total_extra > 0:
        blurb += f", and {total_extra} other{'s' if total_extra != 1 else ''}"

    return blurb


class JobDigestService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        *,
        email_service: EmailService | None = None,
        jwt_service: JWTService | None = None,
    ) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._email: EmailService = email_service or EmailService(settings)
        self._jwt: JWTService | None = jwt_service

    async def collect_users_due(self, *, now: datetime | None = None) -> list[uuid.UUID]:
        current: datetime = now or datetime.now(tz=UTC)
        result = await self._db.execute(
            select(User).where(
                User.job_monitor_enabled.is_(True),
                User.job_digest_frequency != JobDigestFrequency.OFF,
            ),
        )
        users: list[User] = list(result.scalars().all())
        due_ids: list[uuid.UUID] = []
        for user in users:
            if is_user_due_for_digest(
                user,
                now=current,
                send_hour_utc=self._settings.email_digest_send_hour_utc,
            ):
                due_ids.append(user.id)
        return due_ids

    async def build_digest(self, user_id: uuid.UUID) -> DigestBuildResult | None:
        user: User | None = await self._db.get(User, user_id)
        if user is None:
            return None

        watermark: datetime = digest_watermark(user)
        min_score: int = self._settings.email_digest_min_match_score

        count_result = await self._db.execute(
            select(func.count())
            .select_from(UserJobRelevance)
            .join(OrgJob, OrgJob.id == UserJobRelevance.job_id)
            .where(
                UserJobRelevance.user_id == user_id,
                UserJobRelevance.is_relevant.is_(True),
                UserJobRelevance.match_score.is_not(None),
                UserJobRelevance.match_score >= min_score,
                UserJobRelevance.classified_at > watermark,
                OrgJob.is_active.is_(True),
            ),
        )
        total_new_matches: int = int(count_result.scalar() or 0)
        if total_new_matches == 0:
            return DigestBuildResult(jobs=(), total_new_matches=0)

        rows_result = await self._db.execute(
            select(UserJobRelevance, OrgJob, Org)
            .join(OrgJob, OrgJob.id == UserJobRelevance.job_id)
            .join(Org, Org.id == OrgJob.org_id)
            .where(
                UserJobRelevance.user_id == user_id,
                UserJobRelevance.is_relevant.is_(True),
                UserJobRelevance.match_score.is_not(None),
                UserJobRelevance.match_score >= min_score,
                UserJobRelevance.classified_at > watermark,
                OrgJob.is_active.is_(True),
            )
            .order_by(
                UserJobRelevance.match_score.desc(),
                Org.canonical_name.asc(),
                OrgJob.title.asc(),
            )
            .limit(self._settings.email_digest_max_jobs),
        )

        jobs: list[DigestJobEntry] = []
        for relevance, job, org in rows_result.all():
            match_score: int | None = relevance.match_score
            if match_score is None:
                continue
            jobs.append(
                DigestJobEntry(
                    job_id=job.id,
                    org_id=org.id,
                    title=job.title,
                    company_name=org.canonical_name,
                    location=job.location,
                    match_score=match_score,
                    url=job.url,
                    classified_at=relevance.classified_at,
                ),
            )

        org_ids: list[uuid.UUID] = list({job.org_id for job in jobs})
        contact_blurbs: dict[uuid.UUID, str] = await self._load_contact_blurbs(
            user_id, org_ids,
        )
        for entry in jobs:
            object.__setattr__(entry, "contact_blurb", contact_blurbs.get(entry.org_id))

        return DigestBuildResult(jobs=tuple(jobs), total_new_matches=total_new_matches)

    async def _load_contact_blurbs(
        self,
        user_id: uuid.UUID,
        org_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, str]:
        if not org_ids:
            return {}

        from contactsafe_server.services.contacts_service import ContactsService
        from contactsafe_server.services.job_discovery_service import JobDiscoveryService

        discovery: JobDiscoveryService = JobDiscoveryService(self._db, self._settings)
        own_summaries: dict[uuid.UUID, tuple[str, int]] = (
            await discovery._load_user_contact_summaries_by_org(user_id, org_ids)
        )

        contacts_service: ContactsService = ContactsService(self._db)
        shared_summaries: dict[uuid.UUID, tuple[str, str, int]] = (
            await contacts_service.load_shared_contact_summaries_by_org(user_id, org_ids)
        )

        blurbs: dict[uuid.UUID, str] = {}
        for org_id in org_ids:
            blurb: str | None = _build_contact_blurb(
                own_summary=own_summaries.get(org_id),
                shared_summary=shared_summaries.get(org_id),
            )
            if blurb is not None:
                blurbs[org_id] = blurb
        return blurbs

    def _group_jobs_by_company(self, jobs: tuple[DigestJobEntry, ...]) -> list[DigestCompanyGroup]:
        grouped: dict[str, list[DigestJobEntry]] = {}
        blurbs: dict[str, str | None] = {}
        order: list[str] = []
        for job in jobs:
            if job.company_name not in grouped:
                grouped[job.company_name] = []
                blurbs[job.company_name] = job.contact_blurb
                order.append(job.company_name)
            grouped[job.company_name].append(job)
        return [
            DigestCompanyGroup(
                company_name=name,
                jobs=tuple(grouped[name]),
                contact_blurb=blurbs.get(name),
            )
            for name in order
        ]

    def _unsubscribe_url(self, user_id: uuid.UUID) -> str:
        if self._jwt is None:
            raise RuntimeError("JWT service required to build unsubscribe URLs")
        token: str = self._jwt.create_unsubscribe_token(user_id)
        return f"{self._settings.base_url.rstrip('/')}/api/unsubscribe?token={token}"

    def render_digest_html(
        self,
        *,
        user_id: uuid.UUID,
        digest: DigestBuildResult,
    ) -> str:
        company_groups: list[DigestCompanyGroup] = self._group_jobs_by_company(digest.jobs)
        overflow_count: int = max(0, digest.total_new_matches - len(digest.jobs))
        job_count: int = digest.total_new_matches
        subject: str = (
            f"{job_count} new job match"
            if job_count == 1
            else f"{job_count} new job matches"
        )
        template = _templates.env.get_template("job_digest.html")
        return template.render(
            subject=subject,
            job_count=job_count,
            company_groups=company_groups,
            overflow_count=overflow_count,
            jobs_url=f"{self._settings.effective_web_base_url}/jobs",
            profile_url=f"{self._settings.effective_web_base_url}/profile",
            unsubscribe_url=self._unsubscribe_url(user_id),
        )

    async def send_digest_for_user(self, user_id: uuid.UUID) -> DigestSendResult:
        user: User | None = await self._db.get(User, user_id)
        if user is None:
            return DigestSendResult(sent=False, job_count=0, message="User not found.")

        digest: DigestBuildResult | None = await self.build_digest(user_id)
        if digest is None:
            return DigestSendResult(sent=False, job_count=0, message="User not found.")
        if digest.total_new_matches == 0:
            return DigestSendResult(sent=False, job_count=0, message="No new matches.")

        if self._jwt is None:
            return DigestSendResult(sent=False, job_count=0, message="JWT service not configured.")

        html: str = self.render_digest_html(user_id=user_id, digest=digest)
        subject: str = (
            f"{digest.total_new_matches} new job match"
            if digest.total_new_matches == 1
            else f"{digest.total_new_matches} new job matches"
        )
        unsubscribe_url: str = self._unsubscribe_url(user_id)
        send_result: EmailSendResult = await self._email.send_html_email(
            to=user.email,
            subject=subject,
            html=html,
            unsubscribe_url=unsubscribe_url,
        )
        if not send_result.sent:
            return DigestSendResult(
                sent=False,
                job_count=digest.total_new_matches,
                message=send_result.message,
            )

        user.job_digest_last_sent_at = datetime.now(tz=UTC)
        await self._db.commit()
        return DigestSendResult(
            sent=True,
            job_count=digest.total_new_matches,
            message="OK",
        )

    async def unsubscribe_user(self, user_id: uuid.UUID) -> bool:
        user: User | None = await self._db.get(User, user_id)
        if user is None:
            return False
        user.job_digest_frequency = JobDigestFrequency.OFF
        await self._db.commit()
        return True
