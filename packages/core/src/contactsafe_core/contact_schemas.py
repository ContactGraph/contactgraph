from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


def split_display_name(display_name: str) -> tuple[str, str]:
    parts: list[str] = display_name.strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


class PersonListItem(BaseModel):
    person_id: UUID
    first_name: str
    last_name: str
    display_name: str
    primary_email: str | None = None
    phone: str | None = None
    org_name: str | None = None
    current_role: str | None = None
    emails: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    first_contact_at: datetime | None = None
    last_contact_at: datetime | None = None
    tie_strength_score: float = 0.0
    is_human: bool = False
    is_broadcast: bool = False
    is_automated: bool = False


class ListPeopleResult(BaseModel):
    people: list[PersonListItem] = Field(default_factory=list)
    total: int = 0
    message: str


class DedupPersonsResult(BaseModel):
    groups_merged: int = 0
    persons_removed: int = 0
    message: str


class PersonDetailResult(BaseModel):
    person_id: UUID
    first_name: str
    last_name: str
    display_name: str
    primary_email: str | None = None
    phone: str | None = None
    phones: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    org_name: str | None = None
    org_id: UUID | None = None
    current_role: str | None = None
    location: str | None = None
    bio_summary: str | None = None
    inferred_categories: list[str] = Field(default_factory=list)
    descriptive_tags: list[str] = Field(default_factory=list)
    social_profiles: dict[str, str] = Field(default_factory=dict)
    web_links: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    first_contact_at: datetime | None = None
    last_contact_at: datetime | None = None
    last_genuine_interaction_at: datetime | None = None
    tie_strength_score: float = 0.0
    email_count: int = 0
    is_human: bool = False
    is_broadcast: bool = False
    is_automated: bool = False
    message: str


class OrgListItem(BaseModel):
    org_id: UUID
    name: str
    primary_domain: str | None = None
    categories: list[str] = Field(default_factory=list)
    contact_count: int = 0


class ListOrgsResult(BaseModel):
    orgs: list[OrgListItem] = Field(default_factory=list)
    total: int = 0
    message: str


class OrgPersonSummary(BaseModel):
    person_id: UUID
    display_name: str
    primary_email: str | None = None
    current_role: str | None = None


class OrgDetailResult(BaseModel):
    org_id: UUID
    name: str
    primary_domain: str | None = None
    categories: list[str] = Field(default_factory=list)
    attributes: dict[str, object] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    people: list[OrgPersonSummary] = Field(default_factory=list)
    contact_count: int = 0
    message: str


class GetPersonRequest(BaseModel):
    person_id: str


class GetOrgRequest(BaseModel):
    org_id: str
