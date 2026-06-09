from __future__ import annotations

from datetime import datetime
from typing import Literal
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
    is_strong_tie: bool = False
    linkedin_url: str | None = None
    scrapingdog_enriched: bool = False


class ListPeopleRequest(BaseModel):
    network_only: bool = True


class ListPeopleResult(BaseModel):
    people: list[PersonListItem] = Field(default_factory=list)
    total: int = 0
    strong_tie_count: int = 0
    enriched_count: int = 0
    message: str


class StrongTieItem(BaseModel):
    person_id: UUID
    name: str
    email: str | None = None
    phone: str | None = None
    linkedin_url: str
    tie_strength_score: float
    current_company: str | None = None
    current_role: str | None = None
    scrapingdog_enriched: bool = False


class ListStrongTiesResult(BaseModel):
    strong_ties: list[StrongTieItem] = Field(default_factory=list)
    total: int = 0
    message: str


class StrongTieCountResult(BaseModel):
    total: int = 0
    pending_enrichment: int = 0
    enriched: int = 0
    message: str


class StrongTieCompanyInsider(BaseModel):
    person_id: UUID
    person_name: str
    person_role: str | None = None
    tie_strength_score: float = 0.0


class StrongTieCompanySummary(BaseModel):
    org_id: UUID | None = None
    company_name: str
    insider_count: int = 0
    insiders: list[StrongTieCompanyInsider] = Field(default_factory=list)
    best_tie_strength: float = 0.0


class StrongTieCompaniesResult(BaseModel):
    companies: list[StrongTieCompanySummary] = Field(default_factory=list)
    total: int = 0
    message: str


class EnrichStrongTiesResult(BaseModel):
    enqueued: int = 0
    message: str


class ScrapingDogEnrichmentStatusResult(BaseModel):
    state: str
    total: int = 0
    pending: int = 0
    in_progress: int = 0
    complete: int = 0
    failed: int = 0
    enriched_count: int = 0
    message: str


class NetworkStatusResult(BaseModel):
    phone_contact_count: int = 0
    gmail_matched_count: int = 0
    linkedin_matched_count: int = 0
    strong_tie_count: int = 0
    enriched_strong_tie_count: int = 0
    target_company_count: int = 0
    phone_imported: bool = False
    gmail_connected: bool = False
    linkedin_imported: bool = False
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
    description: str | None = None
    careers_url: str | None = None
    linkedin_url: str | None = None
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
    description: str | None = None
    careers_url: str | None = None
    linkedin_url: str | None = None
    categories: list[str] = Field(default_factory=list)
    attributes: dict[str, object] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    people: list[OrgPersonSummary] = Field(default_factory=list)
    contact_count: int = 0
    message: str


class EnrichOrgsResult(BaseModel):
    scheduled: bool
    state: Literal["pending", "running", "complete", "failed"]
    message: str


class OrgEnrichmentStatusResult(BaseModel):
    state: Literal["pending", "running", "complete", "failed"]
    orgs_total: int = 0
    orgs_enriched: int = 0
    progress_message: str | None = None
    error: str | None = None
    message: str


class CancelOrgEnrichmentResult(BaseModel):
    cancelled: bool = False
    message: str = ""


class GetPersonRequest(BaseModel):
    person_id: str


class EnrichPersonRequest(BaseModel):
    person_id: str


class EnrichPersonResult(BaseModel):
    message: str
    queued: bool


class GetOrgRequest(BaseModel):
    org_id: str


class UpdatePersonRequest(BaseModel):
    person_id: str
    first_name: str | None = None
    last_name: str | None = None
    primary_email: str | None = None
    phone: str | None = None
    org_name: str | None = None
    current_role: str | None = None
    location: str | None = None
    bio_summary: str | None = None
    linkedin_url: str | None = None


class UpdateOrgRequest(BaseModel):
    org_id: str
    name: str | None = None
    primary_domain: str | None = None
    description: str | None = None
    linkedin_url: str | None = None
    careers_url: str | None = None
    categories: list[str] | None = None
