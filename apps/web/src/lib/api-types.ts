/** API types aligned with packages/core/src/contactsafe_core/schemas.py */

export type SessionStatus = "pending" | "connected" | "failed";

export type SourceType =
  | "google_mail"
  | "google_calendar"
  | "google_contacts"
  | "linkedin_connections_upload"
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

export interface UserProfileResult {
  display_name: string | null;
  location: string | null;
  google_profile_name: string | null;
  message: string;
}

export interface UpdateUserProfileRequest {
  display_name?: string | null;
  location?: string | null;
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
  person_id: string;
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
}

export interface ListPeopleResult {
  people: PersonListItem[];
  total: number;
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
  categories: string[];
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
  categories: string[];
  attributes: Record<string, unknown>;
  aliases: string[];
  people: OrgPersonSummary[];
  contact_count: number;
  message: string;
}
