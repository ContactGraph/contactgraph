"use client";

import { useQuery } from "@tanstack/react-query";

import type {
  JobMonitorConfigResult,
  JobPreferencesResult,
  ListOrgListsResult,
  ListSourcesResult,
  OrgEnrichmentStatusResult,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";
import { useGraphEvents } from "@/lib/use-graph-events";

import {
  hasTargetCompanies,
  isGraphReady,
  isJobSetupComplete,
  isOrgEnrichmentBlocking,
  isOrgEnrichmentComplete,
  sourceForType,
} from "./setup-utils";

export type OnboardingPhase = "graph-setup" | "job-setup" | "jobs-active";

export interface OrgEnrichmentProgress {
  orgs_enriched: number;
  orgs_total: number;
}

export interface OnboardingPhaseState {
  phase: OnboardingPhase;
  isLoading: boolean;
  graphReady: boolean;
  jobSetupComplete: boolean;
  phoneComplete: boolean;
  linkedinComplete: boolean;
  linkedinProfileComplete: boolean;
  hasTargetCompanies: boolean;
  hasJobPreferences: boolean;
  jobMonitorEnabled: boolean;
  showJobsTab: boolean;
  orgEnrichmentComplete: boolean;
  orgEnrichmentInProgress: boolean;
  orgEnrichmentProgress: OrgEnrichmentProgress | null;
}

export interface UseOnboardingPhaseOptions {
  /**
   * When false, no authenticated queries or event streams run. Use this for
   * shared components (e.g. the site header) that also render for logged-out
   * visitors — otherwise the proxy calls 401 and force a redirect to /login.
   */
  readonly enabled?: boolean;
}

export function useOnboardingPhase(
  options?: UseOnboardingPhaseOptions,
): OnboardingPhaseState {
  const enabled: boolean = options?.enabled ?? true;

  useGraphEvents(enabled);

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => proxyPost<ListSourcesResult>("list-sources"),
    enabled,
  });

  const orgListsQuery = useQuery({
    queryKey: ["org-lists"],
    queryFn: () => proxyPost<ListOrgListsResult>("list-org-lists"),
    enabled,
  });

  const jobPreferencesQuery = useQuery({
    queryKey: ["job-preferences"],
    queryFn: () => proxyPost<JobPreferencesResult>("get-job-preferences"),
    enabled,
  });

  const jobMonitorConfigQuery = useQuery({
    queryKey: ["job-monitor-config"],
    queryFn: () => proxyPost<JobMonitorConfigResult>("get-job-monitor-config"),
    enabled,
  });

  const orgEnrichmentQuery = useQuery({
    queryKey: ["org-enrichment-status"],
    queryFn: () =>
      proxyPost<OrgEnrichmentStatusResult>("get-org-enrichment-status"),
    enabled,
  });

  const sources = sourcesQuery.data?.sources ?? [];
  const orgLists = orgListsQuery.data?.lists ?? [];
  const jobPreferences = jobPreferencesQuery.data;
  const jobMonitorConfig = jobMonitorConfigQuery.data;
  const orgEnrichmentStatus: OrgEnrichmentStatusResult | undefined =
    orgEnrichmentQuery.data;

  const phoneComplete: boolean =
    sourceForType(sources, "phone_contacts_upload")?.sync_state === "complete";
  const linkedinComplete: boolean =
    sourceForType(sources, "linkedin_connections_upload")?.sync_state ===
    "complete";
  const linkedinProfileComplete: boolean =
    sourceForType(sources, "linkedin_profile_upload")?.sync_state ===
    "complete";
  const graphReady: boolean = isGraphReady(sources);
  const hasTargetCompaniesFlag: boolean = hasTargetCompanies(orgLists);
  const hasJobPreferences: boolean =
    (jobPreferences?.text ?? "").trim().length > 0;
  const jobMonitorEnabled: boolean = jobMonitorConfig?.enabled === true;
  const orgEnrichmentComplete: boolean =
    isOrgEnrichmentComplete(orgEnrichmentStatus);
  const orgEnrichmentInProgress: boolean =
    isOrgEnrichmentBlocking(orgEnrichmentStatus);

  const orgEnrichmentProgress: OrgEnrichmentProgress | null =
    orgEnrichmentStatus !== undefined && orgEnrichmentStatus.orgs_total > 0
      ? {
          orgs_enriched: orgEnrichmentStatus.orgs_enriched,
          orgs_total: orgEnrichmentStatus.orgs_total,
        }
      : null;

  const jobSetupComplete: boolean = isJobSetupComplete(
    sources,
    orgLists,
    jobPreferences,
    jobMonitorConfig,
  );

  const isLoading: boolean =
    sourcesQuery.isLoading ||
    orgListsQuery.isLoading ||
    jobPreferencesQuery.isLoading ||
    jobMonitorConfigQuery.isLoading;

  let phase: OnboardingPhase;
  if (!graphReady) {
    phase = "graph-setup";
  } else if (jobSetupComplete) {
    phase = "jobs-active";
  } else {
    phase = "job-setup";
  }

  return {
    phase,
    isLoading,
    graphReady,
    jobSetupComplete,
    phoneComplete,
    linkedinComplete,
    linkedinProfileComplete,
    hasTargetCompanies: hasTargetCompaniesFlag,
    hasJobPreferences,
    jobMonitorEnabled,
    showJobsTab: graphReady,
    orgEnrichmentComplete,
    orgEnrichmentInProgress,
    orgEnrichmentProgress,
  };
}
