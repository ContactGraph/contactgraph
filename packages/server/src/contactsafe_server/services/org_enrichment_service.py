"""Background org enrichment using Exa search."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_core.contact_schemas import EnrichOrgsResult, OrgEnrichmentStatusResult
from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    Org,
    OrgEnrichmentRun,
    Person,
    PersonAlias,
    UserPersonObservation,
)
from contactsafe_server.services.contacts_service import PHONE_RELATIONSHIP
from contactsafe_server.services.exa_client import ExaClient
from contactsafe_server.services.strong_tie_matcher import LINKEDIN_CONNECTIONS_RELATIONSHIP
from contactsafe_server.services.web_search_types import WebSearchHit

logger: logging.Logger = logging.getLogger(__name__)

OrgEnrichmentState = Literal["pending", "running", "complete", "failed"]

_LINKEDIN_COMPANY_RE: re.Pattern[str] = re.compile(
    r"^https?://(?:[a-z]+\.)?linkedin\.com/company/[^/?#]+",
    flags=re.IGNORECASE,
)
_CAREERS_PATH_RE: re.Pattern[str] = re.compile(
    r"/(?:careers|jobs|join-us|openings|work-with-us)(?:/|$)",
    flags=re.IGNORECASE,
)
_SKIP_DOMAINS: frozenset[str] = frozenset(
    {
        "linkedin.com",
        "facebook.com",
        "twitter.com",
        "x.com",
        "instagram.com",
        "youtube.com",
        "wikipedia.org",
        "crunchbase.com",
        "glassdoor.com",
        "indeed.com",
        "google.com",
        "bing.com",
    }
)

_scheduling_lock: threading.Lock = threading.Lock()
_active_org_enrichment_user_ids: set[uuid.UUID] = set()


class OrgEnrichmentService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._exa: ExaClient = ExaClient(settings)

    async def start_enrichment(self, user_id: uuid.UUID) -> EnrichOrgsResult:
        if not self._settings.exa_api_key:
            return EnrichOrgsResult(
                scheduled=False,
                state="failed",
                message="Exa API key is not configured.",
            )

        if await self._has_running_run(user_id):
            return EnrichOrgsResult(
                scheduled=False,
                state="running",
                message="Company enrichment is already running.",
            )

        org_ids: list[uuid.UUID] = await self._list_user_org_ids(user_id)
        if not org_ids:
            return EnrichOrgsResult(
                scheduled=False,
                state="complete",
                message="No organizations to enrich yet.",
            )

        enriched_count: int = await self._count_enriched_orgs(user_id)
        total: int = len(org_ids)
        run = OrgEnrichmentRun(
            user_id=user_id,
            state="running",
            started_at=datetime.now(tz=UTC),
            orgs_total=total,
            orgs_enriched=enriched_count,
            progress_message=self._progress_message(enriched_count, total),
        )
        self._db.add(run)
        await self._db.flush()

        if not schedule_org_enrichment(user_id, run.id):
            run.state = "failed"
            run.error = "Could not schedule company enrichment task"
            run.completed_at = datetime.now(tz=UTC)
            await self._db.commit()
            return EnrichOrgsResult(
                scheduled=False,
                state="failed",
                message="Company enrichment is already running.",
            )

        await self._db.commit()
        return EnrichOrgsResult(
            scheduled=True,
            state="running",
            message="Company enrichment started in the background.",
        )

    async def get_status(self, user_id: uuid.UUID) -> OrgEnrichmentStatusResult:
        run: OrgEnrichmentRun | None = await self._latest_run(user_id)
        orgs_total: int = await self._count_user_orgs(user_id)
        orgs_enriched: int = await self._count_enriched_orgs(user_id)

        if run is not None:
            state: OrgEnrichmentState = run.state  # type: ignore[assignment]
            return OrgEnrichmentStatusResult(
                state=state,
                orgs_total=max(run.orgs_total, orgs_total),
                orgs_enriched=run.orgs_enriched if run.state == "running" else max(run.orgs_enriched, orgs_enriched),
                progress_message=run.progress_message,
                error=run.error,
                message=self._status_message(state, run.orgs_enriched, run.orgs_total),
            )

        if orgs_total == 0:
            return OrgEnrichmentStatusResult(
                state="pending",
                orgs_total=0,
                orgs_enriched=0,
                progress_message=None,
                error=None,
                message="No organizations to enrich yet.",
            )

        idle_state: OrgEnrichmentState = (
            "complete" if orgs_enriched >= orgs_total else "pending"
        )
        return OrgEnrichmentStatusResult(
            state=idle_state,
            orgs_total=orgs_total,
            orgs_enriched=orgs_enriched,
            progress_message=None,
            error=None,
            message=self._status_message(idle_state, orgs_enriched, orgs_total),
        )

    async def enrich_orgs(self, user_id: uuid.UUID, run_id: uuid.UUID) -> None:
        run: OrgEnrichmentRun | None = await self._db.get(OrgEnrichmentRun, run_id)
        if run is None:
            logger.warning("Org enrichment run %s not found", run_id)
            return

        orgs: list[Org] = await self._load_orgs_for_user(user_id)
        run.orgs_total = len(orgs)
        run.orgs_enriched = 0
        run.progress_message = self._progress_message(0, run.orgs_total)
        await self._db.commit()

        for index, org in enumerate(orgs, start=1):
            try:
                await self._enrich_one_org(org)
                run.orgs_enriched = index
                run.progress_message = self._progress_message(
                    run.orgs_enriched,
                    run.orgs_total,
                )
                await self._db.commit()
                logger.info(
                    "Org enrichment progress: %d/%d (%s)",
                    run.orgs_enriched,
                    run.orgs_total,
                    org.canonical_name,
                )
            except Exception:
                logger.exception("Failed to enrich org %s (%s)", org.id, org.canonical_name)
                await self._db.rollback()
                run = await self._db.get(OrgEnrichmentRun, run_id)
                if run is None:
                    return
            await asyncio.sleep(0.5)

        run.state = "complete"
        run.completed_at = datetime.now(tz=UTC)
        run.progress_message = None
        await self._db.commit()

    async def _enrich_one_org(self, org: Org) -> None:
        company_hits: list[WebSearchHit] = await self._exa.search_raw(
            query=f'"{org.canonical_name}" company',
            num_results=5,
        )
        careers_hits: list[WebSearchHit] = await self._exa.search_raw(
            query=f'"{org.canonical_name}" careers jobs',
            num_results=5,
        )
        description_hits: list[WebSearchHit] = await self._exa.search_with_summary(
            query=f'"{org.canonical_name}" company',
            summary_query=(
                f"What does {org.canonical_name} do? "
                "Describe their product or business in one or two sentences."
            ),
            num_results=3,
        )

        parsed = parse_org_enrichment_hits(
            company_name=org.canonical_name,
            company_hits=company_hits,
            careers_hits=careers_hits,
            description_hits=description_hits,
        )

        if parsed.primary_domain is not None:
            org.primary_domain = parsed.primary_domain
        if parsed.description is not None:
            org.description = parsed.description
        if parsed.careers_url is not None:
            org.careers_url = parsed.careers_url
        if parsed.linkedin_url is not None:
            org.linkedin_url = parsed.linkedin_url

        attributes: dict[str, object] = dict(org.attributes or {})
        attributes["exa_enriched_at"] = datetime.now(tz=UTC).isoformat()
        org.attributes = attributes

    async def _load_orgs_for_user(self, user_id: uuid.UUID) -> list[Org]:
        org_ids: list[uuid.UUID] = await self._list_user_org_ids(user_id)
        if not org_ids:
            return []
        result = await self._db.execute(
            select(Org).where(Org.id.in_(org_ids)).order_by(Org.canonical_name.asc())
        )
        return list(result.scalars().all())

    async def _list_user_org_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._db.execute(
            select(Org.id)
            .join(Person, Person.current_org_id == Org.id)
            .where(*self._strong_tie_person_filter(user_id))
            .group_by(Org.id)
            .order_by(Org.canonical_name.asc())
        )
        return [row[0] for row in result.all()]

    async def _count_user_orgs(self, user_id: uuid.UUID) -> int:
        result = await self._db.execute(
            select(Org.id)
            .join(Person, Person.current_org_id == Org.id)
            .where(*self._strong_tie_person_filter(user_id))
            .group_by(Org.id)
        )
        return len(result.all())

    async def _count_enriched_orgs(self, user_id: uuid.UUID) -> int:
        result = await self._db.execute(
            select(Org.id)
            .join(Person, Person.current_org_id == Org.id)
            .where(
                *self._strong_tie_person_filter(user_id),
                or_(
                    Org.description.is_not(None),
                    Org.careers_url.is_not(None),
                    Org.linkedin_url.is_not(None),
                    Org.attributes.has_key("exa_enriched_at"),
                ),
            )
            .group_by(Org.id)
        )
        return len(result.all())

    @staticmethod
    def _strong_tie_person_filter(user_id: uuid.UUID):  # noqa: ANN205
        return (
            exists(
                select(UserPersonObservation.person_id).where(
                    UserPersonObservation.user_id == user_id,
                    UserPersonObservation.person_id == Person.id,
                    UserPersonObservation.relationship_types.any(PHONE_RELATIONSHIP),
                ).correlate(Person)
            ),
            exists(
                select(UserPersonObservation.person_id).where(
                    UserPersonObservation.user_id == user_id,
                    UserPersonObservation.person_id == Person.id,
                    UserPersonObservation.relationship_types.any(
                        LINKEDIN_CONNECTIONS_RELATIONSHIP,
                    ),
                ).correlate(Person)
            ),
            exists(
                select(PersonAlias.person_id).where(
                    PersonAlias.person_id == Person.id,
                    PersonAlias.kind == "linkedin_url",
                ).correlate(Person)
            ),
        )

    async def _latest_run(self, user_id: uuid.UUID) -> OrgEnrichmentRun | None:
        result = await self._db.execute(
            select(OrgEnrichmentRun)
            .where(OrgEnrichmentRun.user_id == user_id)
            .order_by(OrgEnrichmentRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _has_running_run(self, user_id: uuid.UUID) -> bool:
        run: OrgEnrichmentRun | None = await self._latest_run(user_id)
        return run is not None and run.state == "running"

    @staticmethod
    def _progress_message(orgs_enriched: int, orgs_total: int) -> str:
        return f"Enriched {orgs_enriched} of {orgs_total} companies"

    @staticmethod
    def _status_message(
        state: OrgEnrichmentState,
        orgs_enriched: int,
        orgs_total: int,
    ) -> str:
        if state == "running":
            return f"Enriching companies ({orgs_enriched}/{orgs_total})…"
        if state == "complete":
            return f"Company enrichment complete ({orgs_enriched}/{orgs_total})."
        if state == "failed":
            return "Company enrichment failed."
        if orgs_total == 0:
            return "No organizations to enrich yet."
        if orgs_enriched >= orgs_total:
            return f"{orgs_enriched}/{orgs_total} companies enriched."
        return f"{orgs_enriched}/{orgs_total} companies enriched so far."


@dataclass(frozen=True, slots=True)
class ParsedOrgEnrichment:
    primary_domain: str | None
    description: str | None
    careers_url: str | None
    linkedin_url: str | None


def parse_org_enrichment_hits(
    *,
    company_name: str,
    company_hits: list[WebSearchHit],
    careers_hits: list[WebSearchHit],
    description_hits: list[WebSearchHit] | None = None,
) -> ParsedOrgEnrichment:
    linkedin_url: str | None = _pick_linkedin_company_url(company_hits + careers_hits)
    careers_url: str | None = _pick_careers_url(careers_hits + company_hits)
    primary_domain: str | None = _pick_primary_domain(company_hits, company_name)
    description: str | None = _pick_description(
        description_hits or company_hits,
        company_name,
    )
    return ParsedOrgEnrichment(
        primary_domain=primary_domain,
        description=description,
        careers_url=careers_url,
        linkedin_url=linkedin_url,
    )


def _org_is_enriched(org: Org) -> bool:
    if org.attributes.get("exa_enriched_at") is not None:
        return True
    return (
        org.description is not None
        and org.linkedin_url is not None
        and org.careers_url is not None
    )


def _pick_linkedin_company_url(hits: list[WebSearchHit]) -> str | None:
    for hit in hits:
        if hit.url and _LINKEDIN_COMPANY_RE.match(hit.url):
            return hit.url.split("?", maxsplit=1)[0]
    return None


def _pick_careers_url(hits: list[WebSearchHit]) -> str | None:
    for hit in hits:
        if not hit.url:
            continue
        parsed = urlparse(hit.url)
        if _CAREERS_PATH_RE.search(parsed.path):
            return hit.url.split("?", maxsplit=1)[0]
    return None


def _pick_primary_domain(hits: list[WebSearchHit], company_name: str) -> str | None:
    normalized_name: str = _normalize_company_name(company_name)
    for hit in hits:
        domain: str | None = _domain_from_url(hit.url)
        if domain is None or _is_skipped_domain(domain):
            continue
        if normalized_name and normalized_name in _normalize_company_name(domain):
            return domain
        if normalized_name and normalized_name in _normalize_company_name(hit.title):
            return domain
    for hit in hits:
        domain = _domain_from_url(hit.url)
        if domain is not None and not _is_skipped_domain(domain):
            return domain
    return None


_ELLIPSIS_MARKER_RE: re.Pattern[str] = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]")
_MARKDOWN_LINK_RE: re.Pattern[str] = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_HEADER_RE: re.Pattern[str] = re.compile(r"^#{1,6}\s*")
_DESCRIPTION_MAX_LEN: int = 220


def _clean_org_description(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line: str = raw_line.strip()
        if not line:
            continue
        line = _MARKDOWN_HEADER_RE.sub("", line)
        line = re.sub(r"\s+#+\s*", " ", line)
        line = _ELLIPSIS_MARKER_RE.sub(" ", line)
        line = _MARKDOWN_LINK_RE.sub(r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\s+", " ", line).strip(" ·|-")
        if line:
            lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _truncate_at_word(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    truncated: str = text[:max_len]
    last_space: int = truncated.rfind(" ")
    if last_space > max_len // 2:
        truncated = truncated[:last_space]
    return truncated.rstrip(".,;:- ") + "…"


def _summarize_description(text: str, *, max_len: int = _DESCRIPTION_MAX_LEN) -> str:
    cleaned: str = _clean_org_description(text)
    if not cleaned:
        return ""
    sentences: list[str] = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", cleaned)
        if part.strip()
    ]
    if sentences:
        summary: str = sentences[0]
        for sentence in sentences[1:3]:
            candidate: str = f"{summary} {sentence}".strip()
            if len(candidate) > max_len:
                break
            summary = candidate
        return _truncate_at_word(summary, max_len)
    return _truncate_at_word(cleaned, max_len)


def _description_quality_score(text: str) -> int:
    score: int = min(len(text), 400)
    score -= text.count("[...]") * 40
    score -= text.count("#") * 8
    score -= sum(1 for ch in text if ch in "[]{}") * 4
    if text.endswith("…"):
        score += 10
    return score


def _is_valid_description(text: str, normalized_company: str) -> bool:
    if len(text) < 40:
        return False
    if normalized_company not in text.lower() and len(text) < 80:
        return False
    return True


def _pick_description(hits: list[WebSearchHit], company_name: str) -> str | None:
    normalized_company: str = company_name.lower()

    for hit in hits:
        if not hit.summary.strip():
            continue
        summary: str = _summarize_description(hit.summary)
        if _is_valid_description(summary, normalized_company):
            return summary

    best: str | None = None
    best_score: int = -1
    for hit in hits:
        if not hit.text.strip():
            continue
        candidate: str = _summarize_description(hit.text)
        if not _is_valid_description(candidate, normalized_company):
            continue
        score: int = _description_quality_score(candidate)
        if score > best_score:
            best_score = score
            best = candidate

    return best


def _domain_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host: str = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or "." not in host:
        return None
    return host


def _is_skipped_domain(domain: str) -> bool:
    for skipped in _SKIP_DOMAINS:
        if domain == skipped or domain.endswith(f".{skipped}"):
            return True
    return False


def _normalize_company_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def schedule_org_enrichment(user_id: uuid.UUID, run_id: uuid.UUID) -> bool:
    with _scheduling_lock:
        if user_id in _active_org_enrichment_user_ids:
            return False
        _active_org_enrichment_user_ids.add(user_id)
    asyncio.create_task(
        _run_org_enrichment_task(user_id, run_id),
        name=f"org-enrichment-{user_id}",
    )
    return True


def is_org_enrichment_running(user_id: uuid.UUID) -> bool:
    with _scheduling_lock:
        return user_id in _active_org_enrichment_user_ids


def release_org_enrichment_lock(user_id: uuid.UUID) -> None:
    with _scheduling_lock:
        _active_org_enrichment_user_ids.discard(user_id)


async def _run_org_enrichment_task(user_id: uuid.UUID, run_id: uuid.UUID) -> None:
    from contactsafe_server.deps import build_app_context

    ctx = build_app_context()
    factory = ctx.session_factory
    try:
        async with factory() as db:
            service = OrgEnrichmentService(db, ctx.settings)
            await service.enrich_orgs(user_id, run_id)
    except Exception as exc:
        logger.exception("Background org enrichment failed for user %s", user_id)
        try:
            async with factory() as db:
                run: OrgEnrichmentRun | None = await db.get(OrgEnrichmentRun, run_id)
                if run is not None:
                    run.state = "failed"
                    run.error = str(exc)[:500]
                    run.completed_at = datetime.now(tz=UTC)
                    run.progress_message = None
                    await db.commit()
        except Exception:
            logger.exception("Failed to mark org enrichment run %s as failed", run_id)
    finally:
        release_org_enrichment_lock(user_id)
