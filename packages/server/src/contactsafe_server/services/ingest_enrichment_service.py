import json
import logging
import re
import uuid
from typing import cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings
from contactsafe_server.db.models import Person, PersonAlias, UserPersonObservation
from contactsafe_server.services.claim_writer import record_employment, record_person_attribute
from contactsafe_server.services.email_parse import (
    BROADCAST_LOCAL_PARTS,
    ContactAccumulator,
    org_name_from_email,
)
from contactsafe_server.services.enrichment_attempt_tracker import EnrichmentAttemptTracker
from contactsafe_server.services.entity_resolution import EntityResolver, MergeConflict
from contactsafe_server.services.category_inference import infer_categories_from_contact
from contactsafe_server.services.openai_json import content_from_chat_completion, parse_json_object
from contactsafe_server.services.org_enrichment import should_apply_enrichment_org
from contactsafe_server.services.org_search import is_automation_or_generic_domain
from contactsafe_server.services.person_discovery_service import PersonDiscoveryService
from contactsafe_server.services.person_profile_recompute import PersonProfileRecompute
from contactsafe_server.services.signature_enrichment import parse_signature_from_snippets
from contactsafe_server.services.web_enrichment import (
    extract_hints_from_web_hits,
    extract_social_profiles_from_hits,
)

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


class IngestEnrichmentService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db: AsyncSession = db
        self._settings: Settings = settings
        self._discovery: PersonDiscoveryService = PersonDiscoveryService(settings)
        self._tracker: EnrichmentAttemptTracker = EnrichmentAttemptTracker(
            db, ttl_days=getattr(settings, "web_enrichment_ttl_days", 30)
        )
        self._recompute: PersonProfileRecompute = PersonProfileRecompute(db)
        self._resolver: EntityResolver = EntityResolver(db)

    async def enrich_after_import(
        self,
        *,
        user_id: uuid.UUID,
        contact_by_email: dict[str, ContactAccumulator],
    ) -> None:
        people: list[tuple[Person, UserPersonObservation]] = await self._load_people_with_obs(user_id)
        if not people:
            return

        enriched_person_ids: list[uuid.UUID] = []

        for person, obs in people:
            primary_email: str | None = person.primary_email
            if not primary_email:
                continue
            acc: ContactAccumulator | None = contact_by_email.get(primary_email)
            if obs.is_automated or obs.is_broadcast:
                continue

            await self._heuristic_enrich(person, acc, user_id=user_id)
            await self._signature_enrich(person, acc, user_id=user_id)
            enriched_person_ids.append(person.id)

        if self._has_web_enrichment_provider():
            limit: int = self._web_enrichment_limit()
            top_for_web = await self._load_top_people_by_tie_strength(user_id, limit=limit)
            await self._web_enrich_batch(top_for_web, contact_by_email, user_id=user_id)

        if self._settings.openai_api_key:
            top_for_llm = await self._load_top_people_by_tie_strength(
                user_id, limit=self._settings.enrichment_contact_limit
            )
            await self._llm_enrich_batch(top_for_llm, contact_by_email, user_id=user_id)

        await self._recompute.recompute_for_user(user_id)
        await self._db.flush()

    def _has_web_enrichment_provider(self) -> bool:
        return bool(
            self._settings.exa_api_key
            or self._settings.tavily_api_key
            or self._settings.serper_api_key
        )

    def _web_enrichment_limit(self) -> int:
        return max(
            self._settings.web_enrichment_contact_limit,
            self._settings.exa_enrichment_contact_limit,
        )

    async def _load_people_with_obs(
        self, user_id: uuid.UUID
    ) -> list[tuple[Person, UserPersonObservation]]:
        result = await self._db.execute(
            select(Person, UserPersonObservation)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
        )
        return [(p, obs) for p, obs in result.all()]

    async def _load_top_people_by_tie_strength(
        self, user_id: uuid.UUID, *, limit: int
    ) -> list[Person]:
        result = await self._db.execute(
            select(Person)
            .join(
                UserPersonObservation,
                (UserPersonObservation.person_id == Person.id)
                & (UserPersonObservation.user_id == user_id),
            )
            .where(
                UserPersonObservation.is_automated.is_(False),
                UserPersonObservation.is_broadcast.is_(False),
            )
            .order_by(
                UserPersonObservation.is_human.desc(),
                UserPersonObservation.tie_strength_score.desc(),
            )
            .limit(limit)
        )
        return list(result.scalars().unique().all())

    async def _heuristic_enrich(
        self,
        person: Person,
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
                    org = await self._resolver.resolve_org(domain=domain, name=inferred_org)
                    await record_employment(
                        self._db,
                        person_id=person.id,
                        org_id=org.id,
                        contributor_user_id=user_id,
                        contributor_source_kind="heuristic",
                        confidence=0.4,
                    )

    async def _signature_enrich(
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

    async def _web_enrich_batch(
        self,
        people: list[Person],
        contact_by_email: dict[str, ContactAccumulator],
        *,
        user_id: uuid.UUID,
    ) -> None:
        for person in people:
            email: str = person.primary_email or ""
            if not email:
                continue

            if not await self._tracker.should_attempt(person_id=person.id, source_kind="web"):
                continue

            acc: ContactAccumulator | None = contact_by_email.get(email)
            try:
                discovery = await self._discovery.discover_person(
                    name=person.canonical_name,
                    email=email,
                    org_hint=person.current_org_name,
                )
            except Exception:
                logger.exception("Web discovery failed for %s", email)
                await self._tracker.record_attempt(
                    person_id=person.id,
                    source_kind="web",
                    user_id=user_id,
                    succeeded=False,
                    error="discovery_exception",
                )
                continue

            hits = [*discovery.employer_hits, *discovery.activity_hits]
            provider: str = discovery.providers_used[0] if discovery.providers_used else "web"

            await self._tracker.record_attempt(
                person_id=person.id,
                source_kind="web",
                user_id=user_id,
                succeeded=bool(hits or discovery.posts),
                result_count=len(hits) + len(discovery.posts),
            )

            if not hits and not discovery.posts:
                continue

            activity_blob: str = self._discovery.activity_blob(discovery)
            web_hints = extract_hints_from_web_hits(
                hits=discovery.employer_hits or hits,
                email=email,
                display_name=person.canonical_name,
                org_hint=person.current_org_name,
                pitch_outbound_count=acc.pitch_outbound_count if acc else 0,
                activity_posts=activity_blob,
            )

            source_kind: str = provider.split(":")[0]

            if web_hints.org_name and should_apply_enrichment_org(
                primary_email=email, proposed_org=web_hints.org_name
            ):
                domain: str | None = None
                if "@" in email:
                    d: str = email.rsplit("@", 1)[1].lower()
                    if not is_automation_or_generic_domain(d):
                        domain = d
                org = await self._resolver.resolve_org(domain=domain, name=web_hints.org_name)
                await record_employment(
                    self._db,
                    person_id=person.id,
                    org_id=org.id,
                    role_title=web_hints.current_role,
                    contributor_user_id=user_id,
                    contributor_source_kind=source_kind,
                    confidence=0.7,
                )

            for cat in web_hints.categories:
                await record_person_attribute(
                    self._db,
                    person_id=person.id,
                    kind="category",
                    value=cat.lower(),
                    contributor_user_id=user_id,
                    contributor_source_kind=source_kind,
                    confidence=0.65,
                )

            for platform, url in web_hints.social_profiles.items():
                await record_person_attribute(
                    self._db,
                    person_id=person.id,
                    kind=f"social_profile.{platform}",
                    value=url,
                    contributor_user_id=user_id,
                    contributor_source_kind=source_kind,
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
                            alias_kind, url,
                        )

            if activity_blob.strip():
                await record_person_attribute(
                    self._db,
                    person_id=person.id,
                    kind="bio_summary",
                    value=activity_blob.strip()[:2000],
                    contributor_user_id=user_id,
                    contributor_source_kind=source_kind,
                    confidence=0.6,
                )

    async def _llm_enrich_batch(
        self,
        people: list[Person],
        contact_by_email: dict[str, ContactAccumulator],
        *,
        user_id: uuid.UUID,
    ) -> None:
        enrichable: list[Person] = []
        for person in people:
            if await self._tracker.should_attempt(person_id=person.id, source_kind="llm"):
                enrichable.append(person)

        payload_people: list[dict[str, str]] = []
        for person in enrichable[:50]:
            email: str = person.primary_email or ""
            acc: ContactAccumulator | None = contact_by_email.get(email)
            payload_people.append(
                {
                    "person_id": str(person.id),
                    "name": person.canonical_name,
                    "email": email,
                    "org_hint": person.current_org_name or "",
                    "notes": acc.display_name if acc else "",
                    "bio_summary": person.bio_summary or "",
                }
            )

        if not payload_people:
            return

        prompt: str = (
            "For each contact, produce:\n"
            "- descriptive_tags: 3–8 lowercase tags describing what this person does, "
            "their industry, and professional identity. Be broad and generous — "
            "over-tagging is better than under-tagging. "
            "Examples: investor, angel, vc, venture-capital, founder, teacher, professor, "
            "artist, journalist, nonprofit, healthcare, real-estate, government, engineer, "
            "designer, product-manager, recruiter, lawyer, consultant, scientist, musician, "
            "author, podcaster, executive, sales, marketing, data-science, devops, "
            "finance, banking, crypto, climate-tech, biotech, edtech.\n"
            "- categories: legacy short tags (vc, founder, engineer, sales) if applicable.\n"
            "- current_role: job title if inferrable.\n"
            "- org_name: company/org if inferrable.\n\n"
            'Return JSON: {"contacts": [{"person_id": "...", "descriptive_tags": [], '
            '"categories": [], "current_role": "", "org_name": ""}]}'
        )
        try:
            async with httpx.AsyncClient(timeout=60.0) as http:
                response = await http.post(
                    f"{self._settings.openai_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._settings.openai_enrichment_model,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": prompt},
                            {
                                "role": "user",
                                "content": json.dumps({"contacts": payload_people}),
                            },
                        ],
                    },
                )
                response.raise_for_status()
                data = parse_json_object(
                    content_from_chat_completion(cast(dict[str, object], response.json()))
                )
        except Exception:
            logger.exception("LLM ingest enrichment failed")
            for person in enrichable:
                await self._tracker.record_attempt(
                    person_id=person.id,
                    source_kind="llm",
                    user_id=user_id,
                    succeeded=False,
                    error="llm_exception",
                )
            return

        by_id: dict[str, Person] = {str(p.id): p for p in enrichable}
        contacts_raw: object = data.get("contacts")
        if not isinstance(contacts_raw, list):
            return

        items: list[object] = cast(list[object], contacts_raw)
        for item_raw in items:
            if not isinstance(item_raw, dict):
                continue
            item: dict[str, object] = cast(dict[str, object], item_raw)
            pid_raw: object = item.get("person_id")
            if not isinstance(pid_raw, str):
                continue
            person: Person | None = by_id.get(pid_raw)
            if person is None:
                continue

            primary_email: str = person.primary_email or ""
            local_part: str = primary_email.rsplit("@", 1)[0].lower() if primary_email else ""

            tags_raw: object = item.get("descriptive_tags")
            if isinstance(tags_raw, list):
                tag_items: list[object] = cast(list[object], tags_raw)
                for t in tag_items:
                    if isinstance(t, (str, int)):
                        await record_person_attribute(
                            self._db,
                            person_id=person.id,
                            kind="descriptive_tag",
                            value=str(t).lower().strip(),
                            contributor_user_id=user_id,
                            contributor_source_kind="llm",
                            confidence=0.6,
                        )

            cats_raw: object = item.get("categories")
            if isinstance(cats_raw, list):
                cat_items: list[object] = cast(list[object], cats_raw)
                for c in cat_items:
                    if isinstance(c, (str, int)):
                        await record_person_attribute(
                            self._db,
                            person_id=person.id,
                            kind="category",
                            value=str(c).lower(),
                            contributor_user_id=user_id,
                            contributor_source_kind="llm",
                            confidence=0.6,
                        )

            role_raw: object = item.get("current_role")
            if isinstance(role_raw, str) and role_raw.strip():
                if local_part not in BROADCAST_LOCAL_PARTS:
                    await record_person_attribute(
                        self._db,
                        person_id=person.id,
                        kind="role",
                        value=role_raw.strip(),
                        contributor_user_id=user_id,
                        contributor_source_kind="llm",
                        confidence=0.6,
                    )

            org_raw: object = item.get("org_name")
            if isinstance(org_raw, str) and org_raw.strip():
                candidate_org: str = org_raw.strip()
                if should_apply_enrichment_org(
                    primary_email=primary_email,
                    proposed_org=candidate_org,
                ):
                    domain: str | None = None
                    if primary_email and "@" in primary_email:
                        d: str = primary_email.rsplit("@", 1)[1].lower()
                        if not is_automation_or_generic_domain(d):
                            domain = d
                    org = await self._resolver.resolve_org(domain=domain, name=candidate_org)
                    await record_employment(
                        self._db,
                        person_id=person.id,
                        org_id=org.id,
                        contributor_user_id=user_id,
                        contributor_source_kind="llm",
                        confidence=0.6,
                    )

            await self._tracker.record_attempt(
                person_id=person.id,
                source_kind="llm",
                user_id=user_id,
                succeeded=True,
                result_count=1,
            )


def _social_platform_to_alias_kind(platform: str) -> str | None:
    mapping: dict[str, str] = {
        "linkedin": "linkedin_url",
        "github": "github_url",
        "bluesky": "bluesky_handle",
        "twitter": "twitter_handle",
    }
    return mapping.get(platform)
