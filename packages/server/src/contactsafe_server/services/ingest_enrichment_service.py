import json
import logging
import re
import uuid
from typing import cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contactsafe_server.config import Settings
from contactsafe_server.db.models import Person, PersonEdge
from contactsafe_server.services.employment_service import EmploymentService
from contactsafe_server.services.openai_json import content_from_chat_completion, parse_json_object
from contactsafe_server.services.org_enrichment import should_apply_enrichment_org
from contactsafe_server.services.category_inference import infer_categories_from_contact
from contactsafe_server.services.email_parse import (
    BROADCAST_LOCAL_PARTS,
    ContactAccumulator,
    org_name_from_email,
)
from contactsafe_server.services.person_discovery_service import PersonDiscoveryService
from contactsafe_server.services.signature_enrichment import (
    apply_signature_hints_to_person,
    parse_signature_from_snippets,
)
from contactsafe_server.services.web_enrichment import (
    apply_web_hints_to_person,
    extract_hints_from_web_hits,
)

logger = logging.getLogger(__name__)

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
        self._employment: EmploymentService = EmploymentService(db)
        self._discovery: PersonDiscoveryService = PersonDiscoveryService(settings)

    async def enrich_after_import(
        self,
        *,
        user_id: uuid.UUID,
        contact_by_email: dict[str, ContactAccumulator],
    ) -> None:
        result = await self._db.execute(select(Person).where(Person.user_id == user_id))
        people: list[Person] = list(result.scalars().all())
        if not people:
            return

        for person in people:
            acc: ContactAccumulator | None = contact_by_email.get(
                person.email_addresses[0] if person.email_addresses else ""
            )
            if await self._should_skip_enrichment(person):
                continue
            self._heuristic_enrich_person(person, acc)
            await self._signature_enrich_person(person, acc)

        if self._has_web_enrichment_provider():
            limit: int = self._web_enrichment_limit()
            top_for_web = await self._load_top_people_by_tie_strength(user_id, limit=limit)
            await self._web_enrich_batch(top_for_web, contact_by_email)

        if self._settings.openai_api_key:
            top_for_llm = await self._load_top_people_by_tie_strength(
                user_id, limit=self._settings.enrichment_contact_limit
            )
            await self._llm_enrich_batch(top_for_llm, contact_by_email)

        await self._cleanup_non_human_enrichment(user_id)

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

    async def _should_skip_enrichment(self, person: Person) -> bool:
        result = await self._db.execute(
            select(PersonEdge.is_automated, PersonEdge.is_broadcast).where(
                PersonEdge.person_id == person.id,
                PersonEdge.user_id == person.user_id,
            )
        )
        row: tuple[bool, bool] | None = result.one_or_none()
        if row is None:
            return False
        is_automated, is_broadcast = row
        return is_automated or is_broadcast

    async def _load_top_people_by_tie_strength(
        self, user_id: uuid.UUID, *, limit: int
    ) -> list[Person]:
        result = await self._db.execute(
            select(Person)
            .join(
                PersonEdge,
                (PersonEdge.person_id == Person.id) & (PersonEdge.user_id == user_id),
            )
            .where(
                Person.user_id == user_id,
                PersonEdge.is_automated.is_(False),
                PersonEdge.is_broadcast.is_(False),
            )
            .order_by(
                PersonEdge.is_human.desc(),
                PersonEdge.tie_strength_score.desc(),
            )
            .limit(limit)
        )
        return list(result.scalars().unique().all())

    async def _cleanup_non_human_enrichment(self, user_id: uuid.UUID) -> None:
        result = await self._db.execute(
            select(Person, PersonEdge.is_automated, PersonEdge.is_broadcast)
            .join(
                PersonEdge,
                (PersonEdge.person_id == Person.id) & (PersonEdge.user_id == user_id),
            )
            .where(Person.user_id == user_id)
        )
        for person, is_automated, is_broadcast in result.all():
            if not is_automated and not is_broadcast:
                continue
            person.current_role = None
            if person.email_addresses:
                inferred_org: str | None = org_name_from_email(person.email_addresses[0])
                person.current_org_name = inferred_org

    def _heuristic_enrich_person(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
    ) -> None:
        email: str = person.email_addresses[0] if person.email_addresses else ""
        if email:
            local_part: str = email.rsplit("@", 1)[0].lower()
            if local_part in BROADCAST_LOCAL_PARTS:
                person.current_role = None
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
        if categories:
            person.inferred_categories = [c.lower() for c in categories]

        if not person.current_role:
            for pattern, role_label in _ROLE_PATTERNS:
                if re.search(pattern, blob, flags=re.IGNORECASE):
                    person.current_role = role_label
                    break

        if not person.current_org_name and person.email_addresses:
            inferred_org: str | None = org_name_from_email(person.email_addresses[0])
            if inferred_org:
                person.current_org_name = inferred_org

    async def _signature_enrich_person(
        self,
        person: Person,
        accumulator: ContactAccumulator | None,
    ) -> None:
        if accumulator is None or not accumulator.inbound_snippets:
            return
        hints = parse_signature_from_snippets(
            accumulator.inbound_snippets,
            display_name=person.canonical_name,
        )
        apply_signature_hints_to_person(person, hints)
        if hints.org_name or hints.current_role:
            await self._employment.apply_enrichment_to_employment(
                person=person,
                org_name=hints.org_name,
                role_title=hints.current_role,
                source="signature",
            )

    async def _web_enrich_batch(
        self,
        people: list[Person],
        contact_by_email: dict[str, ContactAccumulator],
    ) -> None:
        for person in people:
            email: str = person.email_addresses[0] if person.email_addresses else ""
            if not email or await self._should_skip_enrichment(person):
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
                continue

            hits = [*discovery.employer_hits, *discovery.activity_hits]
            if not hits and not discovery.posts:
                continue

            activity_blob: str = self._discovery.activity_blob(discovery)
            hints = extract_hints_from_web_hits(
                hits=discovery.employer_hits or hits,
                email=email,
                display_name=person.canonical_name,
                org_hint=person.current_org_name,
                pitch_outbound_count=acc.pitch_outbound_count if acc else 0,
                activity_posts=activity_blob,
            )
            apply_web_hints_to_person(person, hints)
            source: str = discovery.providers_used[0] if discovery.providers_used else "web"
            await self._employment.apply_enrichment_to_employment(
                person=person,
                org_name=hints.org_name,
                role_title=hints.current_role,
                source=source.split(":")[0],
            )

    async def _llm_enrich_batch(
        self,
        people: list[Person],
        contact_by_email: dict[str, ContactAccumulator],
    ) -> None:
        enrichable: list[Person] = []
        for person in people:
            if not await self._should_skip_enrichment(person):
                enrichable.append(person)

        payload_people: list[dict[str, str]] = []
        for person in enrichable[:50]:
            email: str = person.email_addresses[0] if person.email_addresses else ""
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
            "For each contact, infer categories (vc, founder, engineer, sales, etc.), "
            "current_role (job title if known), and improved org_name. "
            "Return JSON: {\"contacts\": [{\"person_id\": \"...\", \"categories\": [], "
            "\"current_role\": \"\", \"org_name\": \"\"}]}"
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
            logger.exception("LLM ingest enrichment failed; using heuristics")
            for person in enrichable:
                acc = contact_by_email.get(
                    person.email_addresses[0] if person.email_addresses else ""
                )
                self._heuristic_enrich_person(person, acc)
            return

        contacts_raw: object = data.get("contacts")
        if not isinstance(contacts_raw, list):
            return

        by_id: dict[str, Person] = {str(p.id): p for p in enrichable}
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
            cats_raw: object = item.get("categories")
            if isinstance(cats_raw, list):
                cat_items: list[object] = cast(list[object], cats_raw)
                person.inferred_categories = [
                    str(c).lower() for c in cat_items if isinstance(c, (str, int))
                ]
            role_raw: object = item.get("current_role")
            role_title: str | None = None
            primary_email: str = person.email_addresses[0] if person.email_addresses else ""
            local_part: str = primary_email.rsplit("@", 1)[0].lower() if primary_email else ""
            if isinstance(role_raw, str) and role_raw.strip():
                if local_part not in BROADCAST_LOCAL_PARTS:
                    role_title = role_raw.strip()
                    person.current_role = role_title
            org_raw: object = item.get("org_name")
            org_name: str | None = None
            primary_email = person.email_addresses[0] if person.email_addresses else ""
            if isinstance(org_raw, str) and org_raw.strip():
                candidate_org: str = org_raw.strip()
                if should_apply_enrichment_org(
                    primary_email=primary_email,
                    proposed_org=candidate_org,
                ):
                    org_name = candidate_org
                    person.current_org_name = org_name
            await self._employment.apply_enrichment_to_employment(
                person=person,
                org_name=org_name,
                role_title=role_title,
                source="llm",
            )
