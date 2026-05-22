from enum import StrEnum

from pydantic import BaseModel, Field


class QueryIntent(StrEnum):
    LIST_PEOPLE = "list_people"
    LOOKUP_CONTACT = "lookup_contact"
    SEMANTIC_SEARCH = "semantic_search"


class QuerySortBy(StrEnum):
    TIE_STRENGTH = "tie_strength"
    LAST_SEEN = "last_seen"


class QueryPlan(BaseModel):
    """Structured plan produced from a natural-language question."""

    intent: QueryIntent = QueryIntent.LIST_PEOPLE
    name_tokens: list[str] = Field(default_factory=list)
    org_names: list[str] = Field(default_factory=list)
    categories_any: list[str] = Field(default_factory=list)
    role_keywords: list[str] = Field(default_factory=list)
    relationship_types_any: list[str] = Field(default_factory=list)
    require_genuine_contact: bool = False
    exclude_broadcast: bool = True
    semantic_query: str | None = None
    sort_by: QuerySortBy = QuerySortBy.TIE_STRENGTH
    limit: int = 25
