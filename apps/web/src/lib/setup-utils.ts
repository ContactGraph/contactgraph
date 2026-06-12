import type {
  JobMonitorConfigResult,
  JobPreferencesResult,
  ListSourcesResult,
  OrgEnrichmentStatusResult,
  OrgListSummary,
  SourceSummary,
  SourceType,
  SyncState,
} from "@/lib/api-types";

export const IMPORT_COMPLETE_STATES: ReadonlySet<SyncState> = new Set([
  "partial",
  "complete",
]);

export function sourceForType(
  sources: ReadonlyArray<SourceSummary>,
  type: SourceType,
): SourceSummary | undefined {
  let best: SourceSummary | undefined;
  for (const source of sources) {
    if (source.source_type !== type) continue;
    if (source.sync_state === "syncing" || source.sync_state === "pending") {
      return source;
    }
    if (
      best === undefined ||
      source.contacts_resolved > best.contacts_resolved
    ) {
      best = source;
    }
  }
  return best;
}

export function isPhoneImportComplete(
  sources: ReadonlyArray<SourceSummary>,
): boolean {
  const source: SourceSummary | undefined = sourceForType(
    sources,
    "phone_contacts_upload",
  );
  return source !== undefined && source.sync_state === "complete";
}

export function isLinkedInImportComplete(
  sources: ReadonlyArray<SourceSummary>,
): boolean {
  const source: SourceSummary | undefined = sourceForType(
    sources,
    "linkedin_connections_upload",
  );
  return source !== undefined && source.sync_state === "complete";
}

export function isLinkedInProfileComplete(
  sources: ReadonlyArray<SourceSummary>,
): boolean {
  const source: SourceSummary | undefined = sourceForType(
    sources,
    "linkedin_profile_upload",
  );
  return source !== undefined && source.sync_state === "complete";
}

export function isGraphReady(sources: ReadonlyArray<SourceSummary>): boolean {
  return isPhoneImportComplete(sources) && isLinkedInImportComplete(sources);
}

export const JOB_PROSPECTS_LIST_NAME: "Job Prospects" = "Job Prospects";

export function findJobProspectsList(
  orgLists: ReadonlyArray<OrgListSummary>,
): OrgListSummary | undefined {
  return orgLists.find((list) => list.name === JOB_PROSPECTS_LIST_NAME);
}

export function hasTargetCompanies(
  orgLists: ReadonlyArray<OrgListSummary>,
): boolean {
  const jobProspectsList: OrgListSummary | undefined =
    findJobProspectsList(orgLists);
  return jobProspectsList !== undefined && jobProspectsList.org_count > 0;
}

export function jobProspectsStarredCount(
  orgLists: ReadonlyArray<OrgListSummary>,
): number {
  return findJobProspectsList(orgLists)?.org_count ?? 0;
}

export function hasJobPreferences(
  jobPreferences: JobPreferencesResult | undefined,
): boolean {
  return (jobPreferences?.text ?? "").trim().length > 0;
}

export function isJobMonitorEnabled(
  jobMonitorConfig: JobMonitorConfigResult | undefined,
): boolean {
  return jobMonitorConfig?.enabled === true;
}

export function isJobSetupComplete(
  sources: ReadonlyArray<SourceSummary>,
  orgLists: ReadonlyArray<OrgListSummary>,
  jobPreferences: JobPreferencesResult | undefined,
  jobMonitorConfig: JobMonitorConfigResult | undefined,
): boolean {
  return (
    hasTargetCompanies(orgLists) &&
    isLinkedInProfileComplete(sources) &&
    hasJobPreferences(jobPreferences) &&
    isJobMonitorEnabled(jobMonitorConfig)
  );
}

export function isOrgEnrichmentComplete(
  orgEnrichmentStatus: OrgEnrichmentStatusResult | undefined,
): boolean {
  return (
    orgEnrichmentStatus !== undefined &&
    orgEnrichmentStatus.orgs_total > 0 &&
    orgEnrichmentStatus.orgs_enriched >= orgEnrichmentStatus.orgs_total
  );
}

export function isOrgEnrichmentBlocking(
  orgEnrichmentStatus: OrgEnrichmentStatusResult | undefined,
): boolean {
  if (orgEnrichmentStatus === undefined) {
    return true;
  }
  if (orgEnrichmentStatus.orgs_total === 0) {
    return false;
  }
  if (
    orgEnrichmentStatus.state === "failed" ||
    orgEnrichmentStatus.state === "pending"
  ) {
    return false;
  }
  return !isOrgEnrichmentComplete(orgEnrichmentStatus);
}

export function isSourceStepInProgress(
  sourceType: SourceType,
  sources: ReadonlyArray<SourceSummary>,
): boolean {
  const source: SourceSummary | undefined = sourceForType(sources, sourceType);
  return (
    source?.sync_state === "syncing" || source?.sync_state === "pending"
  );
}

export function importTotalContacts(source: SourceSummary): number {
  return Math.max(source.contacts_found, source.contacts_pending);
}

export function importProgressLabel(source: SourceSummary): string {
  const total: number = importTotalContacts(source);
  if (total <= 0) {
    return "Importing…";
  }
  if (source.contacts_resolved <= 0) {
    return `Processing ${total.toLocaleString()} contacts…`;
  }
  return `Imported ${source.contacts_resolved.toLocaleString()} of ${total.toLocaleString()}`;
}

export type SourcesQueryData = ListSourcesResult | undefined;
