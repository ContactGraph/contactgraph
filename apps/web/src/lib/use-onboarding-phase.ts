"use client";

import { useQuery } from "@tanstack/react-query";

import type {
  JobMonitorConfigResult,
  JobPreferencesResult,
  ListOrgListsResult,
  ListSourcesResult,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";

import {
  isGraphReady,
  isJobSetupComplete,
  sourceForType,
} from "./setup-utils";

export type OnboardingPhase = "graph-setup" | "job-setup" | "jobs-active";

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
}

export function useOnboardingPhase(): OnboardingPhaseState {
  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => proxyPost<ListSourcesResult>("list-sources"),
  });

  const orgListsQuery = useQuery({
    queryKey: ["org-lists"],
    queryFn: () => proxyPost<ListOrgListsResult>("list-org-lists"),
  });

  const jobPreferencesQuery = useQuery({
    queryKey: ["job-preferences"],
    queryFn: () => proxyPost<JobPreferencesResult>("get-job-preferences"),
  });

  const jobMonitorConfigQuery = useQuery({
    queryKey: ["job-monitor-config"],
    queryFn: () => proxyPost<JobMonitorConfigResult>("get-job-monitor-config"),
  });

  const sources = sourcesQuery.data?.sources ?? [];
  const orgLists = orgListsQuery.data?.lists ?? [];
  const jobPreferences = jobPreferencesQuery.data;
  const jobMonitorConfig = jobMonitorConfigQuery.data;

  const phoneComplete: boolean =
    sourceForType(sources, "phone_contacts_upload")?.sync_state === "complete";
  const linkedinComplete: boolean =
    sourceForType(sources, "linkedin_connections_upload")?.sync_state ===
    "complete";
  const linkedinProfileComplete: boolean =
    sourceForType(sources, "linkedin_profile_upload")?.sync_state ===
    "complete";
  const graphReady: boolean = isGraphReady(sources);
  const hasTargetCompanies: boolean = orgLists.some((list) => list.org_count > 0);
  const hasJobPreferences: boolean =
    (jobPreferences?.text ?? "").trim().length > 0;
  const jobMonitorEnabled: boolean = jobMonitorConfig?.enabled === true;

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
    hasTargetCompanies,
    hasJobPreferences,
    jobMonitorEnabled,
    showJobsTab: graphReady,
  };
}
