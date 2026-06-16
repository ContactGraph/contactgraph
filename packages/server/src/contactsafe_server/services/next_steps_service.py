"""User-scoped next steps task queue for job-seeking workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import (
    NextStepActionLink,
    NextStepContactCandidate,
    NextStepItem,
    NextStepPayload,
    NextStepsResult,
    UpdateTaskStatusResult,
)
from contactsafe_core.enums import (
    JobInterest,
    SourceType,
    SyncState,
    UserTaskKind,
    UserTaskStatus,
)
from contactsafe_server.db.models import (
    Org,
    OrgJob,
    OrgList,
    OrgListMembership,
    Person,
    Source,
    User,
    UserJobFeedback,
    UserJobRelevance,
    UserPersonObservation,
    UserTask,
)

JOB_PROSPECTS_LIST_NAME: str = "Job Prospects"

DEDUP_UPLOAD_PHONE: str = "upload_phone"
DEDUP_UPLOAD_LINKEDIN: str = "upload_linkedin"
DEDUP_UPLOAD_PROFILE: str = "upload_profile"
DEDUP_SET_JOB_CRITERIA: str = "set_job_criteria"
DEDUP_REVIEW_JOBS: str = "review_jobs"


def outreach_dedup_key(job_id: uuid.UUID) -> str:
    return f"job_outreach:{job_id}"


@dataclass(frozen=True, slots=True)
class SetupState:
    phone_complete: bool
    linkedin_complete: bool
    profile_complete: bool
    has_target_companies: bool
    has_job_preferences: bool
    job_monitor_enabled: bool

    @property
    def graph_ready(self) -> bool:
        return self.phone_complete and self.linkedin_complete

    @property
    def job_criteria_complete(self) -> bool:
        return (
            self.has_target_companies
            and self.has_job_preferences
            and self.job_monitor_enabled
        )

    @property
    def job_setup_complete(self) -> bool:
        return self.profile_complete and self.job_criteria_complete


class NextStepsService:
    def __init__(self, db: AsyncSession) -> None:
        self._db: AsyncSession = db

    async def get_next_steps(self, user_id: uuid.UUID) -> NextStepsResult:
        await self._reconcile_outreach_tasks(user_id)
        setup: SetupState = await self._load_setup_state(user_id)
        overrides: dict[str, UserTask] = await self._load_task_overrides(user_id)
        outreach_tasks: list[UserTask] = await self._load_open_outreach_tasks(user_id)
        unreviewed_count: int = await self._count_unreviewed_jobs(user_id)

        tasks: list[NextStepItem] = []
        tasks.extend(self._derive_onboarding_tasks(setup, overrides, unreviewed_count))
        tasks.extend(self._outreach_tasks_to_items(outreach_tasks))

        tasks.sort(key=lambda task: (task.status != "open", task.sort_rank, task.title))
        open_tasks: list[NextStepItem] = [task for task in tasks if task.status == "open"]
        return NextStepsResult(
            tasks=open_tasks,
            message="OK" if open_tasks else "All caught up!",
        )

    async def update_task_status(
        self,
        user_id: uuid.UUID,
        *,
        dedup_key: str,
        status: Literal["done", "skipped"],
    ) -> UpdateTaskStatusResult:
        existing_result = await self._db.execute(
            select(UserTask).where(
                UserTask.user_id == user_id,
                UserTask.dedup_key == dedup_key,
            ),
        )
        existing: UserTask | None = existing_result.scalar_one_or_none()
        if existing is not None:
            existing.status = status
            await self._db.commit()
            return UpdateTaskStatusResult(
                dedup_key=dedup_key,
                status=status,
                message="OK",
            )

        kind: UserTaskKind = self._kind_for_dedup_key(dedup_key)
        title, detail, sort_rank = self._derived_task_metadata(kind, unreviewed_count=0)
        task = UserTask(
            user_id=user_id,
            dedup_key=dedup_key,
            kind=kind.value,
            status=status,
            title=title,
            detail=detail,
            sort_rank=sort_rank,
        )
        self._db.add(task)
        await self._db.commit()
        return UpdateTaskStatusResult(dedup_key=dedup_key, status=status, message="OK")

    async def set_job_interest(
        self,
        user_id: uuid.UUID,
        *,
        job_id: uuid.UUID,
        interest: Literal["interested", "dismissed"],
    ) -> None:
        job: OrgJob | None = await self._db.get(OrgJob, job_id)
        if job is None:
            raise ValueError("Job not found.")

        existing_result = await self._db.execute(
            select(UserJobFeedback).where(
                UserJobFeedback.user_id == user_id,
                UserJobFeedback.job_id == job_id,
            ),
        )
        existing: UserJobFeedback | None = existing_result.scalar_one_or_none()
        if existing is not None:
            existing.interest = interest
        else:
            self._db.add(
                UserJobFeedback(
                    user_id=user_id,
                    job_id=job_id,
                    interest=interest,
                ),
            )

        if interest == JobInterest.DISMISSED.value:
            outreach_result = await self._db.execute(
                select(UserTask).where(
                    UserTask.user_id == user_id,
                    UserTask.dedup_key == outreach_dedup_key(job_id),
                ),
            )
            outreach: UserTask | None = outreach_result.scalar_one_or_none()
            if outreach is not None and outreach.status == UserTaskStatus.OPEN.value:
                outreach.status = UserTaskStatus.SKIPPED.value

        await self._db.commit()
        await self._reconcile_outreach_tasks(user_id)

    async def _reconcile_outreach_tasks(self, user_id: uuid.UUID) -> None:
        interested_result = await self._db.execute(
            select(UserJobFeedback, OrgJob, Org)
            .join(OrgJob, OrgJob.id == UserJobFeedback.job_id)
            .join(Org, Org.id == OrgJob.org_id)
            .where(
                UserJobFeedback.user_id == user_id,
                UserJobFeedback.interest == JobInterest.INTERESTED.value,
                OrgJob.is_active.is_(True),
            ),
        )
        interested_rows = list(interested_result.all())

        existing_result = await self._db.execute(
            select(UserTask).where(
                UserTask.user_id == user_id,
                UserTask.kind == UserTaskKind.JOB_OUTREACH.value,
            ),
        )
        existing_by_key: dict[str, UserTask] = {
            task.dedup_key: task for task in existing_result.scalars().all()
        }

        viewer_user: User | None = await self._db.get(User, user_id)
        viewer_person_id: uuid.UUID | None = (
            viewer_user.person_id if viewer_user is not None else None
        )

        for row in interested_rows:
            _feedback: UserJobFeedback = row[0]
            job: OrgJob = row[1]
            org: Org = row[2]
            dedup_key: str = outreach_dedup_key(job.id)
            existing: UserTask | None = existing_by_key.get(dedup_key)
            if existing is not None and existing.status != UserTaskStatus.OPEN.value:
                continue

            contacts: list[NextStepContactCandidate] = await self._load_outreach_contacts(
                user_id,
                job.org_id,
                viewer_person_id,
            )
            primary_contact: NextStepContactCandidate | None = (
                contacts[0] if contacts else None
            )
            proposed_message: str = self._build_outreach_message(
                job_title=job.title,
                org_name=org.canonical_name,
                contact=primary_contact,
            )
            payload: dict[str, object] = {
                "job_id": str(job.id),
                "job_title": job.title,
                "org_name": org.canonical_name,
                "job_url": job.url,
                "proposed_message": proposed_message,
                "contacts": [contact.model_dump(mode="json") for contact in contacts],
                "action_links": [
                    {"label": "View job", "href": job.url},
                    {"label": "Review in Jobs", "href": "/jobs"},
                ],
            }

            rel_result = await self._db.execute(
                select(UserJobRelevance.match_score).where(
                    UserJobRelevance.user_id == user_id,
                    UserJobRelevance.job_id == job.id,
                ),
            )
            match_score: int | None = rel_result.scalar_one_or_none()
            sort_rank: int = 100 + (100 - (match_score or 0))

            title: str = f"Reach out about {job.title} at {org.canonical_name}"
            detail: str = (
                "Send a text to someone in your network who works at this company."
            )
            if existing is not None:
                existing.title = title
                existing.detail = detail
                existing.sort_rank = sort_rank
                existing.job_id = job.id
                existing.org_id = job.org_id
                existing.payload = payload
            else:
                self._db.add(
                    UserTask(
                        user_id=user_id,
                        dedup_key=dedup_key,
                        kind=UserTaskKind.JOB_OUTREACH.value,
                        status=UserTaskStatus.OPEN.value,
                        title=title,
                        detail=detail,
                        sort_rank=sort_rank,
                        job_id=job.id,
                        org_id=job.org_id,
                        payload=payload,
                    ),
                )

        await self._db.commit()

    async def _load_setup_state(self, user_id: uuid.UUID) -> SetupState:
        sources_result = await self._db.execute(
            select(Source).where(Source.user_id == user_id),
        )
        sources: list[Source] = list(sources_result.scalars().all())
        phone_complete: bool = self._is_source_complete(sources, SourceType.PHONE_CONTACTS_UPLOAD)
        linkedin_complete: bool = self._is_source_complete(
            sources,
            SourceType.LINKEDIN_CONNECTIONS_UPLOAD,
        )
        profile_complete: bool = self._is_source_complete(
            sources,
            SourceType.LINKEDIN_PROFILE_UPLOAD,
        )

        user: User | None = await self._db.get(User, user_id)
        has_job_preferences: bool = bool((user.job_preferences_text or "").strip()) if user else False
        job_monitor_enabled: bool = bool(user.job_monitor_enabled) if user else False

        org_count_result = await self._db.execute(
            select(OrgListMembership.org_id)
            .join(OrgList, OrgList.id == OrgListMembership.org_list_id)
            .where(
                OrgList.user_id == user_id,
                OrgList.name == JOB_PROSPECTS_LIST_NAME,
            ),
        )
        has_target_companies: bool = org_count_result.first() is not None

        return SetupState(
            phone_complete=phone_complete,
            linkedin_complete=linkedin_complete,
            profile_complete=profile_complete,
            has_target_companies=has_target_companies,
            has_job_preferences=has_job_preferences,
            job_monitor_enabled=job_monitor_enabled,
        )

    async def _count_unreviewed_jobs(self, user_id: uuid.UUID) -> int:
        user: User | None = await self._db.get(User, user_id)
        if user is None or not user.job_monitor_enabled or user.job_monitor_list_id is None:
            return 0

        memberships_result = await self._db.execute(
            select(OrgListMembership.org_id).where(
                OrgListMembership.org_list_id == user.job_monitor_list_id,
            ),
        )
        org_ids: list[uuid.UUID] = [row[0] for row in memberships_result.all()]
        if not org_ids:
            return 0

        unreviewed_result = await self._db.execute(
            select(OrgJob.id)
            .join(
                UserJobRelevance,
                (UserJobRelevance.job_id == OrgJob.id)
                & (UserJobRelevance.user_id == user_id)
                & UserJobRelevance.is_relevant.is_(True),
            )
            .outerjoin(
                UserJobFeedback,
                (UserJobFeedback.job_id == OrgJob.id)
                & (UserJobFeedback.user_id == user_id),
            )
            .where(
                OrgJob.org_id.in_(org_ids),
                OrgJob.is_active.is_(True),
                UserJobFeedback.job_id.is_(None),
            ),
        )
        return len(unreviewed_result.all())

    async def _load_task_overrides(self, user_id: uuid.UUID) -> dict[str, UserTask]:
        result = await self._db.execute(
            select(UserTask).where(
                UserTask.user_id == user_id,
                UserTask.status.in_(
                    [UserTaskStatus.DONE.value, UserTaskStatus.SKIPPED.value],
                ),
            ),
        )
        return {task.dedup_key: task for task in result.scalars().all()}

    async def _load_open_outreach_tasks(self, user_id: uuid.UUID) -> list[UserTask]:
        result = await self._db.execute(
            select(UserTask)
            .where(
                UserTask.user_id == user_id,
                UserTask.kind == UserTaskKind.JOB_OUTREACH.value,
                UserTask.status == UserTaskStatus.OPEN.value,
            )
            .order_by(UserTask.sort_rank.asc(), UserTask.title.asc()),
        )
        return list(result.scalars().all())

    def _derive_onboarding_tasks(
        self,
        setup: SetupState,
        overrides: dict[str, UserTask],
        unreviewed_count: int,
    ) -> list[NextStepItem]:
        derived: list[tuple[str, UserTaskKind, bool, int]] = []

        if not setup.phone_complete:
            derived.append((DEDUP_UPLOAD_PHONE, UserTaskKind.UPLOAD_PHONE, True, 0))
        if not setup.linkedin_complete:
            derived.append((DEDUP_UPLOAD_LINKEDIN, UserTaskKind.UPLOAD_LINKEDIN, True, 10))
        if setup.graph_ready and not setup.profile_complete:
            derived.append((DEDUP_UPLOAD_PROFILE, UserTaskKind.UPLOAD_PROFILE, True, 20))
        if setup.graph_ready and not setup.job_criteria_complete:
            derived.append((DEDUP_SET_JOB_CRITERIA, UserTaskKind.SET_JOB_CRITERIA, True, 30))
        if setup.job_setup_complete and unreviewed_count > 0:
            derived.append((DEDUP_REVIEW_JOBS, UserTaskKind.REVIEW_JOBS, True, 40))

        tasks: list[NextStepItem] = []
        for dedup_key, kind, needed, sort_rank in derived:
            if not needed:
                continue
            override: UserTask | None = overrides.get(dedup_key)
            if override is not None:
                continue
            title, detail, rank = self._derived_task_metadata(
                kind,
                unreviewed_count=unreviewed_count,
                sort_rank=sort_rank,
            )
            payload = self._derived_payload(kind, unreviewed_count=unreviewed_count)
            tasks.append(
                NextStepItem(
                    dedup_key=dedup_key,
                    kind=kind.value,
                    status="open",
                    title=title,
                    detail=detail,
                    sort_rank=rank,
                    payload=payload,
                ),
            )
        return tasks

    def _outreach_tasks_to_items(self, outreach_tasks: list[UserTask]) -> list[NextStepItem]:
        items: list[NextStepItem] = []
        for task in outreach_tasks:
            payload_data: dict[str, object] = task.payload or {}
            contacts_raw: object = payload_data.get("contacts", [])
            contacts: list[NextStepContactCandidate] = []
            if isinstance(contacts_raw, list):
                for entry_obj in cast(list[object], contacts_raw):
                    if isinstance(entry_obj, dict):
                        contacts.append(
                            NextStepContactCandidate.model_validate(entry_obj),
                        )

            action_links_raw: object = payload_data.get("action_links", [])
            action_links: list[NextStepActionLink] = []
            if isinstance(action_links_raw, list):
                for link_obj in cast(list[object], action_links_raw):
                    if isinstance(link_obj, dict):
                        action_links.append(
                            NextStepActionLink.model_validate(link_obj),
                        )

            job_id_raw: object | None = payload_data.get("job_id")
            job_id: uuid.UUID | None = None
            if isinstance(job_id_raw, str):
                job_id = uuid.UUID(job_id_raw)
            elif task.job_id is not None:
                job_id = task.job_id

            items.append(
                NextStepItem(
                    dedup_key=task.dedup_key,
                    kind=task.kind,
                    status=task.status,  # type: ignore[arg-type]
                    title=task.title,
                    detail=task.detail,
                    sort_rank=task.sort_rank,
                    job_id=job_id,
                    org_id=task.org_id,
                    person_id=task.person_id,
                    payload=NextStepPayload(
                        unreviewed_job_count=None,
                        job_id=job_id,
                        job_title=self._payload_str(payload_data, "job_title"),
                        org_name=self._payload_str(payload_data, "org_name"),
                        job_url=self._payload_str(payload_data, "job_url"),
                        proposed_message=self._payload_str(payload_data, "proposed_message"),
                        contacts=contacts,
                        action_links=action_links,
                    ),
                ),
            )
        return items

    async def _load_outreach_contacts(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        viewer_person_id: uuid.UUID | None,
    ) -> list[NextStepContactCandidate]:
        people_result = await self._db.execute(
            select(Person)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .where(Person.current_org_id == org_id)
            .order_by(Person.canonical_name.asc())
            .limit(10),
        )
        people: list[Person] = list(people_result.scalars().all())
        candidates: list[NextStepContactCandidate] = []
        for person in people:
            phone: str | None = person.phone_numbers[0] if person.phone_numbers else None
            display_name: str = person.canonical_name
            if viewer_person_id is not None and person.id == viewer_person_id:
                display_name = "You"
            candidates.append(
                NextStepContactCandidate(
                    person_id=person.id,
                    display_name=display_name,
                    current_role=person.current_role,
                    phone=phone,
                ),
            )
        return candidates

    @staticmethod
    def _build_outreach_message(
        *,
        job_title: str,
        org_name: str,
        contact: NextStepContactCandidate | None,
    ) -> str:
        first_name: str = ""
        if contact is not None:
            first_name = contact.display_name.split()[0] if contact.display_name.strip() else ""
        greeting: str = f"Hi {first_name}," if first_name else "Hi,"
        return (
            f"{greeting} I saw {org_name} is hiring for a {job_title} role and thought of you. "
            "Would you be open to a quick chat about what it's like working there?"
        )

    @staticmethod
    def _is_source_complete(sources: list[Source], source_type: SourceType) -> bool:
        for source in sources:
            if source.source_type != source_type.value:
                continue
            return source.sync_state == SyncState.COMPLETE.value
        return False

    @staticmethod
    def _kind_for_dedup_key(dedup_key: str) -> UserTaskKind:
        mapping: dict[str, UserTaskKind] = {
            DEDUP_UPLOAD_PHONE: UserTaskKind.UPLOAD_PHONE,
            DEDUP_UPLOAD_LINKEDIN: UserTaskKind.UPLOAD_LINKEDIN,
            DEDUP_UPLOAD_PROFILE: UserTaskKind.UPLOAD_PROFILE,
            DEDUP_SET_JOB_CRITERIA: UserTaskKind.SET_JOB_CRITERIA,
            DEDUP_REVIEW_JOBS: UserTaskKind.REVIEW_JOBS,
        }
        if dedup_key in mapping:
            return mapping[dedup_key]
        if dedup_key.startswith("job_outreach:"):
            return UserTaskKind.JOB_OUTREACH
        raise ValueError(f"Unknown task dedup_key: {dedup_key}")

    @staticmethod
    def _derived_task_metadata(
        kind: UserTaskKind,
        *,
        unreviewed_count: int,
        sort_rank: int | None = None,
    ) -> tuple[str, str | None, int]:
        if kind == UserTaskKind.UPLOAD_PHONE:
            return (
                "Upload phone contacts",
                "Import your phone contacts so ContactGraph can map your network.",
                sort_rank if sort_rank is not None else 0,
            )
        if kind == UserTaskKind.UPLOAD_LINKEDIN:
            return (
                "Upload LinkedIn connections",
                "Import your LinkedIn connections export to enrich your graph.",
                sort_rank if sort_rank is not None else 10,
            )
        if kind == UserTaskKind.UPLOAD_PROFILE:
            return (
                "Upload your profile",
                "Upload your LinkedIn profile PDF so we can match you to roles.",
                sort_rank if sort_rank is not None else 20,
            )
        if kind == UserTaskKind.SET_JOB_CRITERIA:
            return (
                "Specify desired job criteria",
                "Pick target companies, describe your ideal role, and turn on job monitoring.",
                sort_rank if sort_rank is not None else 30,
            )
        if kind == UserTaskKind.REVIEW_JOBS:
            return (
                f"Review {unreviewed_count} new job{'s' if unreviewed_count != 1 else ''}",
                "Go to the Jobs tab and mark each role as interested or not interested.",
                sort_rank if sort_rank is not None else 40,
            )
        return ("Complete next step", None, sort_rank if sort_rank is not None else 999)

    @staticmethod
    def _derived_payload(kind: UserTaskKind, *, unreviewed_count: int) -> NextStepPayload:
        if kind == UserTaskKind.UPLOAD_PHONE:
            return NextStepPayload(
                action_links=[NextStepActionLink(label="Go to Graph", href="/graph")],
            )
        if kind == UserTaskKind.UPLOAD_LINKEDIN:
            return NextStepPayload(
                action_links=[NextStepActionLink(label="Go to Graph", href="/graph")],
            )
        if kind == UserTaskKind.UPLOAD_PROFILE:
            return NextStepPayload(
                action_links=[NextStepActionLink(label="Go to Profile", href="/profile")],
            )
        if kind == UserTaskKind.SET_JOB_CRITERIA:
            return NextStepPayload(
                action_links=[NextStepActionLink(label="Go to Jobs setup", href="/jobs")],
            )
        if kind == UserTaskKind.REVIEW_JOBS:
            return NextStepPayload(
                unreviewed_job_count=unreviewed_count,
                action_links=[NextStepActionLink(label="Go to Jobs", href="/jobs")],
            )
        return NextStepPayload()

    @staticmethod
    def _payload_str(payload: dict[str, object], key: str) -> str | None:
        value: object | None = payload.get(key)
        return value if isinstance(value, str) else None
