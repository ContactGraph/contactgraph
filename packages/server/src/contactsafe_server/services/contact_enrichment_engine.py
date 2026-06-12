"""Per-contact enrichment strategy execution."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings
from contactsafe_server.db.models import (
    EmploymentClaim,
    Org,
    Person,
    PersonAlias,
    PersonAttributeClaim,
    User,
    UserPersonObservation,
)
from contactsafe_server.services.claim_writer import record_employment, record_person_attribute
from contactsafe_server.services.email_parse import (
    BROADCAST_LOCAL_PARTS,
    ContactAccumulator,
    org_name_from_email,
)
from contactsafe_server.services.enrichment_attempt_tracker import EnrichmentAttemptTracker
from contactsafe_server.services.enrichment_strategies.base import email_domain_is_fresh
from contactsafe_server.services.enrichment_strategies.scrapingdog_linkedin import (
    run_scrapingdog_linkedin_strategy,
)
from contactsafe_server.services.entity_resolution import EntityResolver, MergeConflict
from contactsafe_server.services.category_inference import infer_categories_from_contact
from contactsafe_server.services.openai_json import content_from_chat_completion, parse_json_object
from contactsafe_server.services.org_enrichment import should_apply_enrichment_org
from contactsafe_server.services.org_search import is_automation_or_generic_domain
from contactsafe_server.services.person_discovery_service import PersonDiscoveryService
from contactsafe_server.services.person_search_query import (
    build_company_discovery_query,
    build_linkedin_discovery_query,
    is_generic_email,
)
from contactsafe_server.services.signature_enrichment import parse_signature_from_snippets
from contactsafe_server.services.web_enrichment import (
    extract_hints_from_web_hits,
    extract_social_profiles_from_hits,
)
from contactsafe_server.services.web_hit_verification import verify_web_hits
from contactsafe_server.services.web_search_types import WebSearchHit

logger: logging.Logger = logging.getLogger(__name__)

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "vc": [r"\bvc\b", r"venture capital", r"investor", r"partner at"],
    "founder": [r"\bfounder\b", r"\bco-founder\b", r"\bceo\b"],
    "engineer": [r"\bengineer\b", r"\bdeveloper\b", r"\bsoftware\b"],
    "sales": [r"\bsales\b", r"\baccount executive\b", r"\bae\b"],
}

_ROLE_PATTERNS: list[tuple[str, str]] = [
    (r"\brevops\b", "RevOps"),
    (r"\brevenue operations\b", "Revenue Operations"),
    (r"\bproduct manager\b", "Product Manager"),
    (r"\bchief executive\b", "CEO"),
]


@dataclass(slots=True)
class UserEnrichmentContext:
    user_name: str | None = None
    user_location: str | None = None
    user_company_names: list[str] = field(default_factory=list)
    user_context_hints: list[str] | None = None


class ContactEnrichmentEngine:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._discovery: PersonDiscoveryService = PersonDiscoveryService(settings)
        self._tracker: EnrichmentAttemptTracker = EnrichmentAttemptTracker(
            db, ttl_days=settings.web_enrichment_ttl_days
        )
        self._resolver: EntityResolver = EntityResolver(db)

    async def load_user_context(self, user_id: uuid.UUID) -> UserEnrichmentContext:
        user: User | None = await self._db.get(User, user_id)
        if user is None:
            return UserEnrichmentContext()

        user_name: str | None = user.display_name or user.google_profile_name
        company_names: list[str] = []
        hints: list[str] = []

        if user.person_id is not None:
            org_result = await self._db.execute(
                select(Org.canonical_name)
                .join(EmploymentClaim, EmploymentClaim.org_id == Org.id)
                .where(EmploymentClaim.person_id == user.person_id)
            )
            for (org_name,) in org_result.all():
                if org_name and org_name not in company_names:
                    company_names.append(org_name)
                    hints.append(org_name)

            edu_result = await self._db.execute(
                select(PersonAttributeClaim.value).where(
                    PersonAttributeClaim.person_id == user.person_id,
                    PersonAttributeClaim.kind == "education",
                )
            )
            for (school_name,) in edu_result.all():
                if school_name and school_name not in hints:
                    hints.append(school_name)

        return UserEnrichmentContext(
            user_name=user_name,
            user_location=user.location,
            user_company_names=company_names,
            user_context_hints=hints if hints else None,
        )

    async def build_accumulator(
        self,
        person: Person,
        obs: UserPersonObservation,
    ) -> ContactAccumulator | None:
        email: str | None = person.primary_email
        if not email:
            return None
        snippets: list[str] | None = (
            list(obs.import_snippets) if obs.import_snippets else None
        )
        return ContactAccumulator(
            email=email,
            display_name=person.canonical_name,
            first_seen_at=obs.first_observed_at,
            last_seen_at=obs.last_observed_at,
            message_count=obs.email_count,
            outbound_count=obs.outbound_count,
            inbound_count=obs.inbound_count,
            inbound_snippets=snippets,
        )

    async def run_strategy(
        self,
        strategy: str,
        *,
        person: Person,
        obs: UserPersonObservation,
        accumulator: ContactAccumulator | None,
        user_id: uuid.UUID,
        context: UserEnrichmentContext,
    ) -> bool:
        if strategy == "heuristic":
            await self._run_heuristic(person, obs, accumulator, user_id=user_id)
            return True
        if strategy == "signature":
            await self._run_signature(person, accumulator, user_id=user_id)
            return True
        if strategy == "scrapingdog_linkedin":
            return await run_scrapingdog_linkedin_strategy(
                self._db,
                self._settings,
                person=person,
                user_id=user_id,
                resolver=self._resolver,
                tracker=self._tracker,
            )
        if strategy == "web_employer":
            return await self._run_web_search(
                person,
                accumulator,
                user_id=user_id,
                context=context,
                org_hint=person.current_org_name,
                source_kind="web_employer",
            )
        if strategy == "web_relational":
            if not context.user_name:
                return False
            return await self._run_relational_web(
                person, accumulator, user_id=user_id, context=context
            )
        if strategy == "user_companies":
            return await self._run_user_companies(
                person, accumulator, user_id=user_id, context=context
            )
        if strategy == "email_derived":
            return await self._run_email_derived(
                person, accumulator, user_id=user_id, context=context
            )
        if strategy == "linkedin_search":
            return await self._run_linkedin_search(
                person, accumulator, user_id=user_id, context=context
            )
        if strategy == "mutual_connections":
            return await self._run_mutual_connections(
                person, accumulator, user_id=user_id, context=context
            )
        if strategy == "llm_synthesis":
            return await self._run_llm_synthesis(
                person, accumulator, user_id=user_id, context=context
            )
        logger.warning("Unknown enrichment strategy: %s", strategy)
        return False

    async def _run_heuristic(
        self,
        person: Person,
        obs: UserPersonObservation,
        accumulator: ContactAccumulator | None,
        *,
        user_id: uuid.UUID,
    ) -> None:
        email: str = person.primary_email or ""
        if email:
            local_part: str = email.rsplit("@", 1)[0].lower()
            if local_part in BROADCAST_LOCAL_PARTS:
                return

        blob: str = f"{person.canonical_name} {person.current_role or ''}".lower()
        if accumulator is not None:
            blob = f"{blob} {accumulator.display_name} {accumulator.email}"

        pitch_hits: int = accumulator.pitch_outbound_count if accumulator is not None else 0
        categories: list[str] = infer_categories_from_contact(
            email=email,
            display_name=person.canonical_name,
            org_name=person.current_org_name,
            pitch_outbound_count=pitch_hits,
        )
        for category, patterns in _CATEGORY_KEYWORDS.items():
            if category in categories:
                continue
            if any(re.search(p, blob) for p in patterns):
                categories.append(category)

        for cat in categories:
            await record_person_attribute(
                self._db,
                person_id=person.id,
                kind="category",
                value=cat.lower(),
                contributor_user_id=user_id,
                contributor_source_kind="heuristic",
                confidence=0.5,
            )

        role: str | None = None
        for pattern, role_label in _ROLE_PATTERNS:
            if re.search(pattern, blob, flags=re.IGNORECASE):
                role = role_label
                break

        if role:
            await record_person_attribute(
                self._db,
                person_id=person.id,
                kind="role",
                value=role,
                contributor_user_id=user_id,
                contributor_source_kind="heuristic",
                confidence=0.4,
            )

        if email and not person.current_org_name:
            inferred_org: str | None = org_name_from_email(email)
            if inferred_org:
                domain: str = email.rsplit("@", 1)[1].lower()
                if not is_automation_or_generic_domain(domain):
                    is_fresh: bool = email_domain_is_fresh(
                        obs,
                        freshness_days=self._settings.enrichment_email_domain_freshness_days,
                    )
                    org = await self._resolver.resolve_org(domain=domain, name=inferred_org)
                    if org is not None:
                        await record_employment(
                            self._db,
                            person_id=person.id,
                            org_id=org.id,
                            contributor_user_id=user_id,
                            contributor_source_kind="heuristic",
                            is_current=is_fresh,
                            confidence=0.4 if is_fresh else 0.2,
                        )

    async def _run_signature(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
        *,
        user_id: uuid.UUID,
    ) -> None:
        if accumulator is None or not accumulator.inbound_snippets:
            return
        hints = parse_signature_from_snippets(
            accumulator.inbound_snippets,
            display_name=person.canonical_name,
        )
        if hints.org_name:
            primary_email: str = person.primary_email or ""
            if should_apply_enrichment_org(
                primary_email=primary_email,
                proposed_org=hints.org_name,
            ):
                domain: str | None = None
                if primary_email and "@" in primary_email:
                    d: str = primary_email.rsplit("@", 1)[1].lower()
                    if not is_automation_or_generic_domain(d):
                        domain = d
                org = await self._resolver.resolve_org(domain=domain, name=hints.org_name)
                if org is not None:
                    await record_employment(
                        self._db,
                        person_id=person.id,
                        org_id=org.id,
                        role_title=hints.current_role,
                        contributor_user_id=user_id,
                        contributor_source_kind="gmail_signature",
                        confidence=0.85,
                    )

        if hints.phone_numbers:
            for phone in hints.phone_numbers:
                await record_person_attribute(
                    self._db,
                    person_id=person.id,
                    kind="phone",
                    value=phone,
                    contributor_user_id=user_id,
                    contributor_source_kind="gmail_signature",
                    confidence=0.8,
                )
        if hints.location:
            await record_person_attribute(
                self._db,
                person_id=person.id,
                kind="location",
                value=hints.location,
                contributor_user_id=user_id,
                contributor_source_kind="gmail_signature",
                confidence=0.7,
            )

    async def _run_web_search(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
        *,
        user_id: uuid.UUID,
        context: UserEnrichmentContext,
        org_hint: str | None,
        source_kind: str,
    ) -> bool:
        email: str = person.primary_email or ""
        if not email:
            return False
        if not self._has_web_provider():
            return False
        if not await self._tracker.should_attempt(person_id=person.id, source_kind=source_kind):
            return False

        hits: list[WebSearchHit]
        provider: str | None
        hits, provider = await self._discovery.search_employer(
            name=person.canonical_name,
            email=email,
            org_hint=org_hint,
            user_location=context.user_location,
            context_hints=context.user_context_hints,
        )
        return await self._apply_web_hits(
            person,
            accumulator,
            hits=hits,
            provider=provider or source_kind,
            user_id=user_id,
            source_kind=source_kind,
        )

    async def _run_relational_web(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
        *,
        user_id: uuid.UUID,
        context: UserEnrichmentContext,
    ) -> bool:
        email: str = person.primary_email or ""
        if not email or not context.user_name:
            return False
        if not self._has_web_provider():
            return False
        source_kind: str = "web_relational"
        if not await self._tracker.should_attempt(person_id=person.id, source_kind=source_kind):
            return False

        hits: list[WebSearchHit] = await self._discovery.search_relational(
            user_name=context.user_name,
            contact_name=person.canonical_name,
        )
        return await self._apply_web_hits(
            person,
            accumulator,
            hits=hits,
            provider="relational",
            user_id=user_id,
            source_kind=source_kind,
        )

    async def _run_user_companies(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
        *,
        user_id: uuid.UUID,
        context: UserEnrichmentContext,
    ) -> bool:
        if not context.user_company_names or not self._has_web_provider():
            return False

        source_kind: str = "user_companies"
        if not await self._tracker.should_attempt(person_id=person.id, source_kind=source_kind):
            return False

        found: bool = False
        for company_name in context.user_company_names[:5]:
            query: str = build_company_discovery_query(person.canonical_name, company_name)
            hits, provider = await self._discovery.search_raw_query(query)
            if not hits:
                continue
            applied: bool = await self._apply_web_hits(
                person,
                accumulator,
                hits=hits,
                provider=provider or source_kind,
                user_id=user_id,
                source_kind=source_kind,
            )
            found = found or applied
            if applied:
                break

        if not found:
            await self._tracker.record_attempt(
                person_id=person.id,
                source_kind=source_kind,
                user_id=user_id,
                succeeded=False,
                result_count=0,
            )
        return found

    async def _run_email_derived(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
        *,
        user_id: uuid.UUID,
        context: UserEnrichmentContext,
    ) -> bool:
        email: str = person.primary_email or ""
        if not email or "@" not in email or is_generic_email(email):
            return False
        if not self._has_web_provider():
            return False

        domain: str = email.rsplit("@", 1)[1].lower()
        if is_automation_or_generic_domain(domain):
            return False

        source_kind: str = "email_derived"
        if not await self._tracker.should_attempt(person_id=person.id, source_kind=source_kind):
            return False

        query: str = f'"{person.canonical_name.strip()}" {domain} team OR about OR people'
        hits, provider = await self._discovery.search_raw_query(query)
        return await self._apply_web_hits(
            person,
            accumulator,
            hits=hits,
            provider=provider or source_kind,
            user_id=user_id,
            source_kind=source_kind,
        )

    async def _run_linkedin_search(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
        *,
        user_id: uuid.UUID,
        context: UserEnrichmentContext,
    ) -> bool:
        if not self._has_web_provider():
            return False

        source_kind: str = "linkedin_search"
        if not await self._tracker.should_attempt(person_id=person.id, source_kind=source_kind):
            return False

        query: str = build_linkedin_discovery_query(
            person.canonical_name,
            user_location=context.user_location,
        )
        hits, provider = await self._discovery.search_raw_query(query)
        return await self._apply_web_hits(
            person,
            accumulator,
            hits=hits,
            provider=provider or source_kind,
            user_id=user_id,
            source_kind=source_kind,
        )

    async def _run_mutual_connections(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
        *,
        user_id: uuid.UUID,
        context: UserEnrichmentContext,
    ) -> bool:
        email: str = person.primary_email or ""
        if not email or "@" not in email or is_generic_email(email):
            return False
        if not self._has_web_provider():
            return False

        domain: str = email.rsplit("@", 1)[1].lower()
        if is_automation_or_generic_domain(domain):
            return False

        source_kind: str = "mutual_connections"
        if not await self._tracker.should_attempt(person_id=person.id, source_kind=source_kind):
            return False

        org_hint: str | None = org_name_from_email(email)
        if not org_hint:
            return False

        query: str = f'"{person.canonical_name.strip()}" "{org_hint}" colleagues OR team'
        hits, provider = await self._discovery.search_raw_query(query)
        return await self._apply_web_hits(
            person,
            accumulator,
            hits=hits,
            provider=provider or source_kind,
            user_id=user_id,
            source_kind=source_kind,
        )

    async def _run_llm_synthesis(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
        *,
        user_id: uuid.UUID,
        context: UserEnrichmentContext,
    ) -> bool:
        if not self._settings.openai_api_key:
            return False

        source_kind: str = "llm_synthesis"
        if not await self._tracker.should_attempt(person_id=person.id, source_kind=source_kind):
            return False

        email: str = person.primary_email or ""
        payload: dict[str, object] = {
            "name": person.canonical_name,
            "email": email,
            "current_org": person.current_org_name,
            "current_role": person.current_role,
            "user_name": context.user_name,
            "user_companies": context.user_company_names[:5],
        }
        system_prompt: str = (
            "You enrich contact records. Return JSON with keys: "
            "descriptive_tags (string[]), categories (string[]), "
            "current_role (string|null), org_name (string|null)."
        )
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._settings.openai_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self._settings.openai_api_key}"},
                    json={
                        "model": self._settings.openai_enrichment_model,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": json.dumps(payload)},
                        ],
                    },
                )
                response.raise_for_status()
                content: str = content_from_chat_completion(response.json())
                parsed: dict[str, object] = parse_json_object(content)
        except Exception:
            logger.exception("LLM synthesis failed for %s", email)
            await self._tracker.record_attempt(
                person_id=person.id,
                source_kind=source_kind,
                user_id=user_id,
                succeeded=False,
                error="llm_exception",
            )
            return False

        applied: bool = False
        org_name: str | None = cast(str | None, parsed.get("org_name"))
        if org_name and should_apply_enrichment_org(primary_email=email, proposed_org=org_name):
            domain: str | None = None
            if "@" in email:
                d: str = email.rsplit("@", 1)[1].lower()
                if not is_automation_or_generic_domain(d):
                    domain = d
            org = await self._resolver.resolve_org(domain=domain, name=org_name)
            if org is not None:
                await record_employment(
                    self._db,
                    person_id=person.id,
                    org_id=org.id,
                    role_title=cast(str | None, parsed.get("current_role")),
                    contributor_user_id=user_id,
                    contributor_source_kind="llm",
                    confidence=0.55,
                )
                applied = True

        for tag in cast(list[str], parsed.get("descriptive_tags") or []):
            if tag.strip():
                await record_person_attribute(
                    self._db,
                    person_id=person.id,
                    kind="descriptive_tag",
                    value=tag.strip(),
                    contributor_user_id=user_id,
                    contributor_source_kind="llm",
                    confidence=0.55,
                )
                applied = True

        for cat in cast(list[str], parsed.get("categories") or []):
            if cat.strip():
                await record_person_attribute(
                    self._db,
                    person_id=person.id,
                    kind="category",
                    value=cat.strip().lower(),
                    contributor_user_id=user_id,
                    contributor_source_kind="llm",
                    confidence=0.55,
                )
                applied = True

        await self._tracker.record_attempt(
            person_id=person.id,
            source_kind=source_kind,
            user_id=user_id,
            succeeded=applied,
            result_count=1 if applied else 0,
        )
        return applied

    async def _apply_web_hits(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
        *,
        hits: list[WebSearchHit],
        provider: str,
        user_id: uuid.UUID,
        source_kind: str,
    ) -> bool:
        email: str = person.primary_email or ""
        await self._tracker.record_attempt(
            person_id=person.id,
            source_kind=source_kind,
            user_id=user_id,
            succeeded=bool(hits),
            result_count=len(hits),
        )
        if not hits:
            return False

        known_linkedin_url: str | None = await self._load_person_linkedin_url(person.id)
        all_social_profiles: dict[str, str] = extract_social_profiles_from_hits(hits)
        verified = verify_web_hits(
            hits=hits,
            email=email,
            display_name=person.canonical_name,
            org_hint=person.current_org_name,
            known_linkedin_url=known_linkedin_url,
            social_profiles=all_social_profiles,
        )

        web_hints = extract_hints_from_web_hits(
            hits=verified.employer_hits,
            email=email,
            display_name=person.canonical_name,
            org_hint=person.current_org_name,
            pitch_outbound_count=accumulator.pitch_outbound_count if accumulator else 0,
            activity_posts="",
        )

        claim_confidence: float = verified.confidence
        claim_source: str = provider.split(":")[0]

        if (
            not verified.skip_employment
            and web_hints.org_name
            and should_apply_enrichment_org(
                primary_email=email, proposed_org=web_hints.org_name
            )
        ):
            domain: str | None = None
            if "@" in email:
                d: str = email.rsplit("@", 1)[1].lower()
                if not is_automation_or_generic_domain(d):
                    domain = d
            org = await self._resolver.resolve_org(domain=domain, name=web_hints.org_name)
            if org is not None:
                await record_employment(
                    self._db,
                    person_id=person.id,
                    org_id=org.id,
                    role_title=web_hints.current_role,
                    contributor_user_id=user_id,
                    contributor_source_kind=claim_source,
                    confidence=claim_confidence,
                )

        if not verified.skip_categories:
            for cat in web_hints.categories:
                await record_person_attribute(
                    self._db,
                    person_id=person.id,
                    kind="category",
                    value=cat.lower(),
                    contributor_user_id=user_id,
                    contributor_source_kind=claim_source,
                    confidence=claim_confidence,
                )

        for platform, url in verified.verified_social_profiles.items():
            await record_person_attribute(
                self._db,
                person_id=person.id,
                kind=f"social_profile.{platform}",
                value=url,
                contributor_user_id=user_id,
                contributor_source_kind=claim_source,
                confidence=0.8,
            )
            alias_kind: str | None = _social_platform_to_alias_kind(platform)
            if alias_kind:
                try:
                    await self._resolver.add_person_alias(
                        person_id=person.id,
                        kind=alias_kind,
                        value=url,
                    )
                except MergeConflict:
                    logger.warning(
                        "Alias conflict: %s=%s already belongs to another person",
                        alias_kind,
                        url,
                    )

        return bool(
            web_hints.org_name
            or verified.verified_social_profiles
            or web_hints.categories
        )

    async def _load_person_linkedin_url(self, person_id: uuid.UUID) -> str | None:
        result = await self._db.execute(
            select(PersonAlias.value).where(
                PersonAlias.person_id == person_id,
                PersonAlias.kind == "linkedin_url",
            ).limit(1)
        )
        return result.scalar_one_or_none()

    def _has_web_provider(self) -> bool:
        return bool(
            self._settings.exa_api_key
            or self._settings.tavily_api_key
            or self._settings.serper_api_key
        )


def _social_platform_to_alias_kind(platform: str) -> str | None:
    mapping: dict[str, str] = {
        "linkedin": "linkedin_url",
        "github": "github_url",
        "twitter": "twitter_url",
    }
    return mapping.get(platform.lower())
