import json
import logging
import re
from typing import cast

import httpx
from contactsafe_core.query_plan import QueryPlan
from contactsafe_server.config import Settings
from contactsafe_server.services.heuristic_query_planner import plan_from_heuristics
from contactsafe_server.services.openai_json import content_from_chat_completion, parse_json_object

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM_PROMPT: str = """You translate questions about a user's email-derived contact graph into JSON QueryPlan objects.

Schema:
- intent: list_people | lookup_contact | semantic_search
- name_tokens: person-name tokens to match in person names (e.g. ["chris", "lee"] for "Chris Lee")
- org_names: company names (e.g. ["Cowboy VC", "AIX"])
- categories_any: legacy short tags — only use ["vc", "founder", "engineer", "sales"] if applicable
- type_keywords: 5–10 expanded synonyms for "type of person" queries. Use whenever the question asks about a category/type/profession of contact. Expand broadly with synonyms, related terms, and industry jargon.
  Examples:
    "investors" → ["investor", "angel", "vc", "venture", "partner", "fund", "capital", "lp", "limited partner"]
    "teachers" → ["teacher", "professor", "instructor", "educator", "lecturer", "tutor", "academic"]
    "artists" → ["artist", "painter", "sculptor", "illustrator", "creative director", "gallery", "musician"]
    "nonprofit" → ["nonprofit", "ngo", "charity", "foundation", "social enterprise", "philanthropy"]
- role_keywords: job title keywords for ADDITIONAL filtering (e.g. ["revops"]). Do NOT duplicate type_keywords here.
- relationship_types_any: ONLY use for structural graph queries like "who knows who" or co-occurrence. Leave EMPTY for vague social terms.
- require_genuine_contact: true when the question implies two-way communication ("people I actually talk to", "friends")
- exclude_broadcast: true to omit newsletters/marketing (default true)
- semantic_query: full text for topical search when intent is semantic_search
- sort_by: tie_strength | last_seen
- limit: max results (use 1 for lookup_contact with name+org)

IMPORTANT mapping rules:
- "what investors/teachers/artists/etc. do I know?" → use type_keywords with 5–10 broad synonyms. Also set categories_any if one of the 4 legacy tags applies.
- "friends", "close contacts", "people I know" → sort_by=tie_strength, require_genuine_contact=true, relationship_types_any=[] (NOT ["friend"])
- "who do I email most" → sort_by=tie_strength, limit=10
- Person name lookups → name_tokens with lowercase tokens
- Vague social terms are NOT relationship types. Only use relationship_types_any for explicit graph edge queries.

Return ONLY valid JSON matching QueryPlan. No markdown."""


class QueryPlanner:
    def __init__(self, settings: Settings) -> None:
        self._settings: Settings = settings

    async def plan(self, question: str) -> QueryPlan:
        heuristic_plan: QueryPlan = plan_from_heuristics(question)
        if not self._settings.openai_api_key:
            return heuristic_plan
        try:
            llm_plan: QueryPlan = await self._plan_with_llm(question)
            return self._merge_plans(heuristic_plan, llm_plan, question)
        except Exception:
            logger.exception("LLM query planning failed; using heuristics")
            return heuristic_plan

    async def _plan_with_llm(self, question: str) -> QueryPlan:
        payload: dict[str, object] = {
            "model": self._settings.openai_query_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({"question": question}),
                },
            ],
        }
        async with httpx.AsyncClient(timeout=30.0) as http:
            response = await http.post(
                f"{self._settings.openai_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data: dict[str, object] = parse_json_object(
                content_from_chat_completion(cast(dict[str, object], response.json()))
            )
        return QueryPlan.model_validate(data)

    @staticmethod
    def _merge_plans(heuristic: QueryPlan, llm: QueryPlan, question: str) -> QueryPlan:
        """Prefer LLM plan but keep heuristic filters the model often misses."""
        merged = llm.model_copy(deep=True)
        if not merged.name_tokens:
            merged.name_tokens = heuristic.name_tokens
        if not merged.org_names:
            merged.org_names = heuristic.org_names
        if not merged.categories_any:
            merged.categories_any = heuristic.categories_any
        if not merged.type_keywords:
            merged.type_keywords = heuristic.type_keywords
        if not merged.role_keywords:
            merged.role_keywords = heuristic.role_keywords
        if merged.semantic_query is None and heuristic.semantic_query is not None:
            merged.semantic_query = heuristic.semantic_query
            merged.intent = heuristic.intent
        if not _question_requires_genuine_contact(question):
            merged.require_genuine_contact = False
        return merged


def _question_requires_genuine_contact(question: str) -> bool:
    """Detect explicit requests for two-way relationships only."""
    q_lower: str = question.lower()
    return bool(
        re.search(
            r"\b(genuine|two-way|back-and-forth|real conversation|actually (talk|email|met))\b",
            q_lower,
        )
    )
