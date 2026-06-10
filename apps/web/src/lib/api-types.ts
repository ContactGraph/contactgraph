/** API types aligned with packages/core/src/contactsafe_core/schemas.py */

export type SessionStatus = "pending" | "connected" | "failed";

export type SourceType =
  | "google_mail"
  | "google_calendar"
  | "google_contacts"
  | "linkedin_connections_upload"
  | "linkedin_profile_upload"
  | "phone_contacts_upload";

export type SourceConnectionStatus =
  | "pending_oauth"
  | "connected"
  | "disconnected"
  | "failed";

export type SyncState =
  | "pending"
  | "syncing"
  | "partial"
  | "complete"
  | "failed";

export type EnrichmentRunState =
  | "pending"
  | "running"
  | "complete"
  | "failed";

export type TrustListInviteStatus =
  | "pending"
  | "accepted"
  | "declined"
  | "expired";

export type TrustListMembershipStatus =
  | "active"
  | "muted_by_a"
  | "muted_by_b"
  | "revoked";

export interface ConnectSourceResult {
  connect_session_id: string;
  oauth_url: string;
  status: SessionStatus;
  message: string;
  already_connected: boolean;
  email: string | null;
  scopes: string[];
  source_id: string | null;
  access_token: string | null;
  refresh_token: string | null;
  system_messages: string[];
  upload_url: string | null;
  upload_instructions: string | null;
  poll_secret: string | null;
}

export interface PollConnectResult {
  status: string;
  access_token: string | null;
  refresh_token: string | null;
  email: string | null;
  message: string;
}

export interface SourceSummary {
  source_id: string;
  source_type: SourceType;
  label: string;
  external_account_id: string;
  connection_status: SourceConnectionStatus;
  sync_state: SyncState;
  contacts_found: number;
  contacts_resolved: number;
  contacts_pending: number;
  sync_error: string | null;
}

export interface ListSourcesResult {
  sources: SourceSummary[];
  message: string;
  system_messages: string[];
}

export interface SourceStatusResult {
  source_id: string;
  connect_session_id: string | null;
  status: SessionStatus;
  connection_status: SourceConnectionStatus;
  sync_state: SyncState;
  email: string | null;
  scopes: string[];
  contacts_found: number;
  contacts_resolved: number;
  contacts_pending: number;
  message: string;
  system_messages: string[];
}

export interface SyncSourceResult {
  source_id: string;
  scheduled: boolean;
  sync_state: SyncState;
  email: string | null;
  message: string;
  system_messages: string[];
}

export interface StartEnrichmentResult {
  run_id: string | null;
  scheduled: boolean;
  state: EnrichmentRunState;
  message: string;
  system_messages: string[];
}

export interface EnrichmentStatusResult {
  run_id: string | null;
  state: EnrichmentRunState;
  contacts_total: number;
  contacts_enriched: number;
  started_at: string | null;
  completed_at: string | null;
  progress_message: string | null;
  error: string | null;
  message: string;
  system_messages: string[];
}

export interface UploadSourceResult {
  source_id: string;
  scheduled: boolean;
  sync_state: SyncState;
  message: string;
  system_messages: string[];
}

export interface UserExperience {
  id: string | null;
  company: string;
  role: string | null;
  is_current: boolean;
  started_at: string | null;
  ended_at: string | null;
}

export interface UserProfileResult {
  email: string | null;
  display_name: string | null;
  headline: string | null;
  location: string | null;
  google_profile_name: string | null;
  phone: string | null;
  linkedin_url: string | null;
  bio_summary: string | null;
  social_profiles: Record<string, string>;
  experiences: UserExperience[];
  message: string;
}

export interface UpdateUserProfileRequest {
  display_name?: string | null;
  location?: string | null;
  phone?: string | null;
  linkedin_url?: string | null;
  bio_summary?: string | null;
  social_profiles?: Record<string, string> | null;
}

export interface SaveUserExperienceRequest {
  id?: string | null;
  company: string;
  role?: string | null;
  is_current?: boolean;
  started_at?: string | null;
  ended_at?: string | null;
}

export interface DeleteUserExperienceRequest {
  id: string;
}

export interface PersonMatch {
  person_id: string;
  name: string;
  emails: string[];
  org_name: string | null;
  current_role: string | null;
  inferred_categories: string[];
  descriptive_tags: string[];
  social_profiles: Record<string, string>;
  bio_summary: string | null;
  also_known_as: string[];
  last_seen_in_email: string | null;
  tie_strength_score: number;
  match_reason: string;
  relevance: string;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export interface OrgCount {
  org_name: string;
  count: number;
}

export interface DescribeGraphResult {
  total_contacts: number;
  human_contacts: number;
  broadcast_contacts: number;
  automated_contacts: number;
  queryable_contacts: number;
  top_categories: CategoryCount[];
  top_orgs: OrgCount[];
  strongest_ties: PersonMatch[];
  message: string;
  system_messages: string[];
}

export interface SecondDegreeMatch {
  holder_name: string;
  holder_user_id: string;
  opaque_person_ref: string;
  person_name: string;
  person_org: string | null;
  person_role: string | null;
  person_categories: string[];
  person_location: string | null;
  match_reason: string;
}

export interface QueryNetworkResult {
  question: string;
  matches: PersonMatch[];
  second_degree_matches: SecondDegreeMatch[];
  message: string;
  applied_plan: Record<string, unknown> | null;
  system_messages: string[];
}

export interface TrustListMemberSummary {
  membership_id: string;
  user_id: string;
  email: string;
  name: string | null;
  status: TrustListMembershipStatus;
  established_at: string;
}

export interface TrustListInviteSummary {
  invite_id: string;
  invitee_email: string;
  status: TrustListInviteStatus;
  created_at: string;
}

export interface PendingInboundInvite {
  invite_id: string;
  inviter_email: string;
  inviter_name: string | null;
  created_at: string;
}

export interface ViewTrustedUsersResult {
  members: TrustListMemberSummary[];
  outbound_invites: TrustListInviteSummary[];
  inbound_invites: PendingInboundInvite[];
  max_members: number;
  message: string;
  system_messages: string[];
}

export interface EditTrustedUsersResult {
  added: string[];
  removed: string[];
  accepted: string[];
  declined: string[];
  privacy_updated: string[];
  invite_copy: string | null;
  message: string;
  system_messages: string[];
}

export interface OAuthTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  scope: string;
  refresh_token?: string;
}

export interface PersonListItem {
  person_id: string;
  first_name: string;
  last_name: string;
  display_name: string;
  primary_email: string | null;
  phone: string | null;
  org_name: string | null;
  current_role: string | null;
  emails: string[];
  sources: string[];
  first_contact_at: string | null;
  last_contact_at: string | null;
  tie_strength_score: number;
  is_human: boolean;
  is_broadcast: boolean;
  is_automated: boolean;
  is_strong_tie: boolean;
  linkedin_url: string | null;
  scrapingdog_enriched: boolean;
}

export interface EnrichPersonResult {
  message: string;
  queued: boolean;
}

export interface ListPeopleRequest {
  network_only?: boolean;
}

export interface ListPeopleResult {
  people: PersonListItem[];
  total: number;
  strong_tie_count: number;
  enriched_count: number;
  message: string;
}

export interface StrongTieItem {
  person_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  linkedin_url: string;
  tie_strength_score: number;
  current_company: string | null;
  current_role: string | null;
  scrapingdog_enriched: boolean;
}

export interface ListStrongTiesResult {
  strong_ties: StrongTieItem[];
  total: number;
  message: string;
}

export interface StrongTieCountResult {
  total: number;
  pending_enrichment: number;
  enriched: number;
  message: string;
}

export interface StrongTieCompanyInsider {
  person_id: string;
  person_name: string;
  person_role: string | null;
  tie_strength_score: number;
}

export interface StrongTieCompanySummary {
  org_id: string | null;
  company_name: string;
  insider_count: number;
  insiders: StrongTieCompanyInsider[];
  best_tie_strength: number;
}

export interface StrongTieCompaniesResult {
  companies: StrongTieCompanySummary[];
  total: number;
  message: string;
}

export interface EnrichStrongTiesResult {
  enqueued: number;
  message: string;
}

export interface ScrapingDogEnrichmentStatusResult {
  state: "idle" | "running" | "partial" | "complete";
  total: number;
  pending: number;
  in_progress: number;
  complete: number;
  failed: number;
  enriched_count: number;
  message: string;
}

export interface NetworkStatusResult {
  phone_contact_count: number;
  gmail_matched_count: number;
  linkedin_matched_count: number;
  strong_tie_count: number;
  enriched_strong_tie_count: number;
  target_company_count: number;
  phone_imported: boolean;
  gmail_connected: boolean;
  linkedin_imported: boolean;
  message: string;
}

export interface PersonDetailResult {
  person_id: string;
  first_name: string;
  last_name: string;
  display_name: string;
  primary_email: string | null;
  phone: string | null;
  phones: string[];
  emails: string[];
  org_name: string | null;
  org_id: string | null;
  current_role: string | null;
  location: string | null;
  bio_summary: string | null;
  inferred_categories: string[];
  descriptive_tags: string[];
  social_profiles: Record<string, string>;
  linkedin_url: string | null;
  web_links: string[];
  sources: string[];
  first_contact_at: string | null;
  last_contact_at: string | null;
  last_genuine_interaction_at: string | null;
  tie_strength_score: number;
  email_count: number;
  is_human: boolean;
  is_broadcast: boolean;
  is_automated: boolean;
  message: string;
}

export interface OrgListItem {
  org_id: string;
  name: string;
  primary_domain: string | null;
  description: string | null;
  careers_url: string | null;
  linkedin_url: string | null;
  categories: string[];
  employee_count: number | null;
  company_size_band: string | null;
  contact_count: number;
}

export interface ListOrgsResult {
  orgs: OrgListItem[];
  total: number;
  message: string;
}

export interface OrgPersonSummary {
  person_id: string;
  display_name: string;
  primary_email: string | null;
  current_role: string | null;
}

export interface OrgDetailResult {
  org_id: string;
  name: string;
  primary_domain: string | null;
  description: string | null;
  careers_url: string | null;
  linkedin_url: string | null;
  categories: string[];
  employee_count: number | null;
  company_size_band: string | null;
  attributes: Record<string, unknown>;
  aliases: string[];
  people: OrgPersonSummary[];
  contact_count: number;
  message: string;
}

export interface UpdatePersonRequest {
  person_id: string;
  first_name?: string;
  last_name?: string;
  primary_email?: string;
  phone?: string;
  org_name?: string;
  current_role?: string;
  location?: string;
  bio_summary?: string;
  linkedin_url?: string;
  social_profiles?: Record<string, string>;
}

export interface UpdateOrgRequest {
  org_id: string;
  name?: string;
  primary_domain?: string;
  description?: string;
  linkedin_url?: string;
  careers_url?: string;
  categories?: string[];
}

export interface OrgListSummary {
  list_id: string;
  name: string;
  org_count: number;
  org_ids: string[];
}

export interface ListOrgListsResult {
  lists: OrgListSummary[];
  message: string;
}

export interface CreateOrgListRequest {
  name: string;
}

export interface CreateOrgListResult {
  list_id: string;
  name: string;
  message: string;
}

export interface RenameOrgListRequest {
  list_id: string;
  name: string;
}

export interface RenameOrgListResult {
  list_id: string;
  name: string;
  message: string;
}

export interface DeleteOrgListRequest {
  list_id: string;
}

export interface DeleteOrgListResult {
  deleted: boolean;
  message: string;
}

export interface ModifyOrgListMembershipRequest {
  list_id: string;
  org_ids: string[];
}

export interface ModifyOrgListMembershipResult {
  list_id: string;
  affected_count: number;
  message: string;
}

export type OrgEnrichmentState = "pending" | "running" | "complete" | "failed";

export interface EnrichOrgsResult {
  scheduled: boolean;
  state: OrgEnrichmentState;
  message: string;
}

export interface OrgEnrichmentStatusResult {
  state: OrgEnrichmentState;
  orgs_total: number;
  orgs_enriched: number;
  progress_message: string | null;
  error: string | null;
  message: string;
}

export interface CancelOrgEnrichmentResult {
  cancelled: boolean;
  message: string;
}

export interface TargetCompanyInsiderSummary {
  person_id: string;
  person_name: string;
  person_role: string | null;
  trust_score: number;
  relationship_kind: string | null;
}

export interface TargetCompanySummary {
  org_id: string;
  org_name: string;
  insiders: TargetCompanyInsiderSummary[];
  best_trust_score: number;
}

export interface TargetCompaniesResult {
  companies: TargetCompanySummary[];
  message: string;
  system_messages: string[];
}

export interface SecondDegreeTargetInsiderSummary {
  person_id: string;
  person_name: string;
  person_role: string | null;
  bridge_user_id: string;
  bridge_name: string;
  trust_score: number;
}

export interface SecondDegreeTargetCompanySummary {
  org_id: string;
  org_name: string;
  insiders: SecondDegreeTargetInsiderSummary[];
  best_trust_score: number;
}

export interface SecondDegreeTargetCompaniesResult {
  companies: SecondDegreeTargetCompanySummary[];
  message: string;
  system_messages: string[];
}

export interface JobMonitorConfigResult {
  enabled: boolean;
  list_id: string | null;
  list_name: string | null;
  message: string;
}

export interface SetJobMonitorConfigRequest {
  list_id?: string | null;
  enabled?: boolean;
}

export type JobDiscoveryState = "pending" | "running" | "complete" | "failed" | "cancelled";

export interface StartJobDiscoveryResult {
  scheduled: boolean;
  state: JobDiscoveryState;
  message: string;
}

export interface JobDiscoveryStatusResult {
  state: JobDiscoveryState;
  orgs_total: number;
  orgs_processed: number;
  jobs_found: number;
  new_jobs: number;
  progress_message: string | null;
  error: string | null;
  message: string;
}

export interface OrgJobItem {
  job_id: string;
  external_job_id: string;
  source: string;
  title: string;
  location: string | null;
  department: string | null;
  url: string;
  description_snippet: string | null;
  salary_min: number | null;
  salary_max: number | null;
  remote_status: string | null;
  posted_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  is_active: boolean;
  is_relevant: boolean | null;
  relevance_reason: string | null;
}

export interface OrgJobsByCompany {
  org_id: string;
  org_name: string;
  primary_domain: string | null;
  jobs: OrgJobItem[];
}

export interface ListOrgJobsResult {
  companies: OrgJobsByCompany[];
  total_jobs: number;
  total_relevant: number;
  message: string;
}

export interface SetJobPreferencesRequest {
  text: string;
}

export interface JobPreferencesResult {
  text: string | null;
  classified_job_count: number;
  message: string;
}
