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
- name_tokens: first name tokens to match in person names (e.g. ["chris"])
- org_names: company names (e.g. ["Cowboy VC", "AIX"])
- categories_any: person categories (e.g. ["vc", "founder", "engineer"])
- role_keywords: job title keywords (e.g. ["revops", "revenue operations"])
- relationship_types_any: edge types (e.g. ["investor", "colleague"])
- require_genuine_contact: default false; true only when the question asks for real back-and-forth (not for "what VCs do I know" style lists)
- exclude_broadcast: true to omit newsletters/marketing (default true)
- semantic_query: full text for topical search when intent is semantic_search
- sort_by: tie_strength | last_seen
- limit: max results (use 1 for lookup_contact with name+org)

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
