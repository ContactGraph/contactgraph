from __future__ import annotations

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, Field


def split_display_name(display_name: str) -> tuple[str, str]:
    parts: list[str] = display_name.strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def join_display_name(first_name: str, last_name: str) -> str:
    """Combine first and last name for API display_name (inverse of split_display_name)."""
    return f"{first_name} {last_name}".strip()


class PersonListItem(BaseModel):
    person_id: UUID
    first_name: str
    last_name: str
    display_name: str
    primary_email: str | None = None
    phone: str | None = None
    org_name: str | None = None
    org_primary_domain: str | None = None
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
    is_claimed: bool = False
    avatar_url: str | None = None
    linkedin_url: str | None = None
    scrapingdog_enriched: bool = False
    shared_from: str | None = None
    shared_from_user_id: UUID | None = None
    job_count: int = 0


class ListPeopleRequest(BaseModel):
    network_only: bool = True
    include_shared: bool = True


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
    linkedin_url: str | None = None
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
    is_claimed: bool = False
    avatar_url: str | None = None
    message: str


class ListOrgsRequest(BaseModel):
    include_shared: bool = True


class OrgListItem(BaseModel):
    org_id: UUID
    name: str
    primary_domain: str | None = None
    description: str | None = None
    careers_url: str | None = None
    linkedin_url: str | None = None
    categories: list[str] = Field(default_factory=list)
    employee_count: int | None = None
    company_size_band: str | None = None
    contact_count: int = 0
    primary_contact_name: str | None = None
    shared_from: list[str] = Field(default_factory=list)
    shared_contact_count: int = 0
    shared_primary_contact_name: str | None = None
    shared_primary_bridge_name: str | None = None
    job_count: int = 0


class ListOrgsResult(BaseModel):
    orgs: list[OrgListItem] = Field(default_factory=list)
    total: int = 0
    message: str


class OrgPersonSummary(BaseModel):
    person_id: UUID
    display_name: str
    primary_email: str | None = None
    current_role: str | None = None
    shared_from: str | None = None


class OrgDetailResult(BaseModel):
    org_id: UUID
    name: str
    primary_domain: str | None = None
    description: str | None = None
    careers_url: str | None = None
    linkedin_url: str | None = None
    categories: list[str] = Field(default_factory=list)
    employee_count: int | None = None
    company_size_band: str | None = None
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
    social_profiles: dict[str, str] | None = None


class UpdateOrgRequest(BaseModel):
    org_id: str
    name: str | None = None
    primary_domain: str | None = None
    description: str | None = None
    linkedin_url: str | None = None
    careers_url: str | None = None
    categories: list[str] | None = None


class OrgListSummary(BaseModel):
    list_id: UUID
    name: str
    org_count: int = 0
    org_ids: list[UUID] = Field(default_factory=list)


class ListOrgListsResult(BaseModel):
    lists: list[OrgListSummary] = Field(default_factory=list)
    message: str


class CreateOrgListRequest(BaseModel):
    name: str


class CreateOrgListResult(BaseModel):
    list_id: UUID
    name: str
    message: str


class RenameOrgListRequest(BaseModel):
    list_id: str
    name: str


class RenameOrgListResult(BaseModel):
    list_id: UUID
    name: str
    message: str


class DeleteOrgListRequest(BaseModel):
    list_id: str


class DeleteOrgListResult(BaseModel):
    deleted: bool
    message: str


class ModifyOrgListMembershipRequest(BaseModel):
    list_id: str
    org_ids: list[str]


class ModifyOrgListMembershipResult(BaseModel):
    list_id: UUID
    affected_count: int
    message: str


class AddWatchedCompanyRequest(BaseModel):
    name: str
    website: str | None = None
    industry_tags: list[str] = Field(default_factory=list)
    company_size_band: str | None = None
    employee_count: int | None = None


class AddWatchedCompanyResult(BaseModel):
    org_id: UUID | None = None
    name: str
    added: bool
    message: str


class JobMonitorConfigResult(BaseModel):
    enabled: bool = False
    list_id: UUID | None = None
    list_name: str | None = None
    message: str


class SetJobMonitorConfigRequest(BaseModel):
    list_id: UUID | None = None
    enabled: bool | None = None


class StartJobDiscoveryResult(BaseModel):
    scheduled: bool
    state: Literal["pending", "running", "complete", "failed", "cancelled"]
    message: str


class JobDiscoveryStatusResult(BaseModel):
    state: Literal["pending", "running", "complete", "failed", "cancelled"]
    orgs_total: int = 0
    orgs_processed: int = 0
    jobs_found: int = 0
    new_jobs: int = 0
    progress_message: str | None = None
    error: str | None = None
    message: str


class JobScanStatusResult(BaseModel):
    scanned: int = 0
    total: int = 0
    scanning_active: bool = False
    message: str


class OrgJobItem(BaseModel):
    job_id: UUID
    external_job_id: str
    source: str
    title: str
    org_name: str | None = None
    org_id: UUID | None = None
    org_primary_domain: str | None = None
    location: str | None = None
    department: str | None = None
    url: str
    description_snippet: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    remote_status: str | None = None
    posted_at: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool = True
    is_relevant: bool | None = None
    match_score: int | None = None
    relevance_reason: str | None = None
    role_score: int | None = None
    role_reason: str | None = None
    seniority_score: int | None = None
    seniority_reason: str | None = None
    location_score: int | None = None
    location_reason: str | None = None
    contact_count: int = 0
    primary_contact_name: str | None = None
    shared_contact_count: int = 0
    shared_primary_contact_name: str | None = None
    shared_primary_bridge_name: str | None = None
    user_interest: Literal["interested", "dismissed"] | None = None


class OrgJobsByCompany(BaseModel):
    org_id: UUID
    org_name: str
    primary_domain: str | None = None
    description: str | None = None
    last_checked_at: datetime | None = None
    jobs: list[OrgJobItem] = Field(default_factory=list)


class StartSingleOrgDiscoveryRequest(BaseModel):
    org_id: UUID


class StartSingleOrgDiscoveryResult(BaseModel):
    scheduled: bool
    jobs_found: int = 0
    new_jobs: int = 0
    message: str


class ListOrgJobsResult(BaseModel):
    companies: list[OrgJobsByCompany] = Field(default_factory=list)
    total_jobs: int = 0
    total_relevant: int = 0
    message: str


class FlatJobListResult(BaseModel):
    jobs: list[OrgJobItem] = Field(default_factory=list)
    total_jobs: int = 0
    total_relevant: int = 0
    message: str


class JobDetailResult(BaseModel):
    job: OrgJobItem
    org_description: str | None = None
    org_primary_domain: str | None = None
    contacts: list[OrgPersonSummary] = Field(default_factory=list)
    contact_count: int = 0
    message: str


class SetJobPreferencesRequest(BaseModel):
    text: str
    location_pref: str | None = None
    location_city: str | None = None
    commute_max_minutes: int | None = None
    commute_note: str | None = None


class JobTargetScope(BaseModel):
    industry_tags: list[str] = Field(default_factory=list)
    sharer_names: list[str] = Field(default_factory=list)
    size_bands: list[str] = Field(default_factory=list)


class SetJobTargetScopeRequest(BaseModel):
    target_scope: JobTargetScope


class JobPreferencesResult(BaseModel):
    text: str | None = None
    location_pref: str | None = None
    location_city: str | None = None
    commute_max_minutes: int | None = None
    commute_note: str | None = None
    target_scope: JobTargetScope | None = None
    classified_job_count: int = 0
    message: str


class SetNotificationPreferencesRequest(BaseModel):
    job_digest_frequency: Literal["daily", "weekly", "off"]


class NotificationPreferencesResult(BaseModel):
    job_digest_frequency: Literal["daily", "weekly", "off"]
    message: str


class PipelineStatus(BaseModel):
    name: str
    queued: int = 0
    active: int = 0
    completed_24h: int = 0
    failed_24h: int = 0
    last_run_at: datetime | None = None
    last_run_duration_ms: int | None = None
    items_processed: int | None = None
    items_total: int | None = None


class WorkerStatusResult(BaseModel):
    pipelines: list[PipelineStatus] = Field(default_factory=list)
    worker_connected: bool = False
    redis_connected: bool = False
    message: str = "OK"


class AdminUserItem(BaseModel):
    user_id: str
    email: str
    display_name: str | None = None
    has_vcf: bool = False
    has_linkedin: bool = False
    person_count: int = 0
    org_count: int = 0
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class AdminUsersResult(BaseModel):
    users: list[AdminUserItem] = Field(default_factory=list)
    message: str = "OK"


class PublicCategoryJobItem(BaseModel):
    job_id: UUID
    title: str
    location: str | None = None
    url: str
    remote_status: str | None = None
    posted_at: datetime | None = None


class PublicCategoryCompanyItem(BaseModel):
    org_id: UUID
    slug: str
    name: str
    primary_domain: str | None = None
    description: str | None = None
    company_size_band: str | None = None
    active_job_count: int
    sample_jobs: list[PublicCategoryJobItem] = Field(default_factory=list)


class PublicCompaniesByCategoryResult(BaseModel):
    category: str
    companies: list[PublicCategoryCompanyItem] = Field(default_factory=list)
    total_companies: int = 0
    total_jobs: int = 0
    generated_at: datetime


class PublicCompanyDetailResult(BaseModel):
    org_id: UUID
    slug: str
    name: str
    primary_domain: str | None = None
    description: str | None = None
    company_size_band: str | None = None
    active_job_count: int
    jobs: list[PublicCategoryJobItem] = Field(default_factory=list)
    generated_at: datetime


class NextStepActionLink(BaseModel):
    label: str
    href: str


class NextStepContactCandidate(BaseModel):
    person_id: UUID
    display_name: str
    current_role: str | None = None
    phone: str | None = None


class NextStepPayload(BaseModel):
    unreviewed_job_count: int | None = None
    job_id: UUID | None = None
    job_title: str | None = None
    org_name: str | None = None
    job_url: str | None = None
    proposed_message: str | None = None
    outreach_type: Literal["direct", "bridge"] | None = None
    bridge_name: str | None = None
    bridge_phone: str | None = None
    target_contact_name: str | None = None
    contacts: list[NextStepContactCandidate] = Field(default_factory=list)
    action_links: list[NextStepActionLink] = Field(default_factory=list)


class NextStepItem(BaseModel):
    dedup_key: str
    kind: str
    status: Literal["open", "done", "skipped"]
    title: str
    detail: str | None = None
    sort_rank: int
    job_id: UUID | None = None
    person_id: UUID | None = None
    org_id: UUID | None = None
    payload: NextStepPayload = Field(default_factory=NextStepPayload)


class NextStepsResult(BaseModel):
    tasks: list[NextStepItem] = Field(default_factory=list)
    message: str = "OK"


class UpdateTaskStatusRequest(BaseModel):
    dedup_key: str
    status: Literal["done", "skipped"]


class UpdateTaskStatusResult(BaseModel):
    dedup_key: str
    status: Literal["open", "done", "skipped"]
    message: str = "OK"


class SetJobInterestRequest(BaseModel):
    job_id: UUID
    interest: Literal["interested", "dismissed"]


class SetJobInterestResult(BaseModel):
    job_id: UUID
    interest: Literal["interested", "dismissed"]
    message: str = "OK"
