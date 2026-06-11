"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Loader2, Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { LinkedInProfileUploadDialog } from "@/components/setup/linkedin-profile-upload-dialog";
import { SetupStepStatusIcon } from "@/components/setup/setup-step-status-icon";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  JobDiscoveryStatusResult,
  JobMonitorConfigResult,
  JobPreferencesResult,
  ListOrgListsResult,
  ListSourcesResult,
  OrgEnrichmentStatusResult,
  OrgListSummary,
  SetJobMonitorConfigRequest,
  SourceSummary,
  SourceType,
  StartJobDiscoveryResult,
  UploadSourceResult,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";
import {
  findJobProspectsList,
  hasJobPreferences,
  hasTargetCompanies,
  isLinkedInProfileComplete,
  isOrgEnrichmentBlocking,
  isOrgEnrichmentComplete,
  isSourceStepInProgress,
  jobProspectsStarredCount,
  sourceForType,
} from "@/lib/setup-utils";

export function JobSetupCards() {
  const queryClient = useQueryClient();
  const autoStartedRef = useRef<boolean>(false);
  const [linkedinProfileDialogOpen, setLinkedinProfileDialogOpen] =
    useState<boolean>(false);
  const [linkedinProfileUploadError, setLinkedinProfileUploadError] =
    useState<string | null>(null);
  const [linkedinProfileProcessing, setLinkedinProfileProcessing] =
    useState<boolean>(false);
  const [preferencesText, setPreferencesText] = useState<string>("");
  const [locationPref, setLocationPref] = useState<string | null>(null);
  const [locationCity, setLocationCity] = useState<string>("");

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => proxyPost<ListSourcesResult>("list-sources"),
    refetchInterval: (query) => {
      const data: ListSourcesResult | undefined = query.state.data;
      const syncing: boolean =
        data?.sources.some((source) => source.sync_state === "syncing") ?? false;
      const pending: boolean =
        data?.sources.some((source) => source.sync_state === "pending") ?? false;
      return syncing || pending || linkedinProfileProcessing ? 4000 : false;
    },
  });

  const orgListsQuery = useQuery({
    queryKey: ["org-lists"],
    queryFn: () => proxyPost<ListOrgListsResult>("list-org-lists"),
  });

  const orgEnrichmentQuery = useQuery({
    queryKey: ["org-enrichment-status"],
    queryFn: () =>
      proxyPost<OrgEnrichmentStatusResult>("get-org-enrichment-status"),
    refetchInterval: (query) => {
      const data: OrgEnrichmentStatusResult | undefined = query.state.data;
      if (data === undefined) {
        return 4000;
      }
      if (data.orgs_total === 0 || data.state === "failed") {
        return false;
      }
      return isOrgEnrichmentComplete(data) ? false : 4000;
    },
  });

  const jobPreferencesQuery = useQuery({
    queryKey: ["job-preferences"],
    queryFn: () => proxyPost<JobPreferencesResult>("get-job-preferences"),
  });

  const jobMonitorConfigQuery = useQuery({
    queryKey: ["job-monitor-config"],
    queryFn: () => proxyPost<JobMonitorConfigResult>("get-job-monitor-config"),
  });

  const jobDiscoveryStatusQuery = useQuery({
    queryKey: ["job-discovery-status"],
    queryFn: () =>
      proxyPost<JobDiscoveryStatusResult>("get-job-discovery-status"),
    refetchInterval: (query) =>
      query.state.data?.state === "running" ? 2000 : false,
  });

  const setJobPreferencesMutation = useMutation({
    mutationFn: (params: {
      text: string;
      location_pref: string | null;
      location_city: string | null;
    }) => proxyPost<JobPreferencesResult>("set-job-preferences", params),
    onSuccess: async (result: JobPreferencesResult) => {
      toast.success(result.message);
      await queryClient.invalidateQueries({ queryKey: ["job-preferences"] });
      await queryClient.invalidateQueries({ queryKey: ["org-jobs"] });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const setJobMonitorConfigMutation = useMutation({
    mutationFn: (body: SetJobMonitorConfigRequest) =>
      proxyPost<JobMonitorConfigResult>("set-job-monitor-config", body),
    onSuccess: async (result: JobMonitorConfigResult) => {
      toast.success(result.message);
      await queryClient.invalidateQueries({ queryKey: ["job-monitor-config"] });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const startJobDiscoveryMutation = useMutation({
    mutationFn: () => proxyPost<StartJobDiscoveryResult>("start-job-discovery"),
    onSuccess: async (result: StartJobDiscoveryResult) => {
      toast.success(result.message);
      await queryClient.invalidateQueries({ queryKey: ["job-discovery-status"] });
      await queryClient.invalidateQueries({ queryKey: ["org-jobs"] });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (payload: {
      source_type: SourceType;
      filename: string;
      content: string;
    }) => proxyPost<UploadSourceResult>("upload-source", payload),
    onSuccess: async (_result, variables) => {
      if (variables.source_type === "linkedin_profile_upload") {
        setLinkedinProfileUploadError(null);
        setLinkedinProfileProcessing(true);
      }
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      await queryClient.invalidateQueries({ queryKey: ["user-profile"] });
    },
    onError: (error: Error) => {
      setLinkedinProfileUploadError(error.message);
    },
  });

  const sources: SourceSummary[] = sourcesQuery.data?.sources ?? [];
  const orgLists: OrgListSummary[] = orgListsQuery.data?.lists ?? [];
  const orgEnrichmentStatus: OrgEnrichmentStatusResult | undefined =
    orgEnrichmentQuery.data;
  const jobMonitorConfig: JobMonitorConfigResult | undefined =
    jobMonitorConfigQuery.data;
  const jobDiscoveryStatus: JobDiscoveryStatusResult | undefined =
    jobDiscoveryStatusQuery.data;
  const linkedinProfileSource: SourceSummary | undefined = sourceForType(
    sources,
    "linkedin_profile_upload",
  );
  const jobProspectsList: OrgListSummary | undefined =
    findJobProspectsList(orgLists);

  const starredCount: number = jobProspectsStarredCount(orgLists);
  const targetComplete: boolean = hasTargetCompanies(orgLists);
  const profileComplete: boolean = isLinkedInProfileComplete(sources);
  const preferencesComplete: boolean = hasJobPreferences(jobPreferencesQuery.data);
  const enrichmentBlocking: boolean =
    isOrgEnrichmentBlocking(orgEnrichmentStatus);
  const enrichmentInProgress: boolean =
    orgEnrichmentQuery.isLoading || enrichmentBlocking;

  useEffect(() => {
    if (!linkedinProfileProcessing) {
      return;
    }
    if (linkedinProfileSource === undefined) {
      return;
    }
    if (
      linkedinProfileSource.sync_state === "complete" ||
      linkedinProfileSource.sync_state === "failed"
    ) {
      setLinkedinProfileProcessing(false);
      if (linkedinProfileSource.sync_state === "complete") {
        setLinkedinProfileDialogOpen(false);
      } else {
        setLinkedinProfileUploadError(
          "Could not read that PDF. Try re-exporting from LinkedIn.",
        );
      }
    }
  }, [linkedinProfileProcessing, linkedinProfileSource]);

  useEffect(() => {
    const serverText: string | null = jobPreferencesQuery.data?.text ?? null;
    if (serverText !== null && preferencesText === "") {
      setPreferencesText(serverText);
    }
    const serverLocPref: string | null =
      jobPreferencesQuery.data?.location_pref ?? null;
    if (serverLocPref !== null && locationPref === null) {
      setLocationPref(serverLocPref);
    }
    const serverCity: string | null =
      jobPreferencesQuery.data?.location_city ?? null;
    if (serverCity !== null && locationCity === "") {
      setLocationCity(serverCity);
    }
  }, [
    jobPreferencesQuery.data?.text,
    jobPreferencesQuery.data?.location_pref,
    jobPreferencesQuery.data?.location_city,
    preferencesText,
    locationPref,
    locationCity,
  ]);

  const handleLinkedInProfileUpload = useCallback(
    async (file: File): Promise<void> => {
      const buffer: ArrayBuffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = "";
      for (const byte of bytes) {
        binary += String.fromCharCode(byte);
      }
      const base64: string = btoa(binary);
      uploadMutation.mutate({
        source_type: "linkedin_profile_upload",
        filename: file.name,
        content: base64,
      });
    },
    [uploadMutation],
  );

  useEffect(() => {
    if (autoStartedRef.current) {
      return;
    }
    if (!targetComplete || !profileComplete || !preferencesComplete) {
      return;
    }
    if (jobMonitorConfig?.enabled) {
      return;
    }
    if (jobProspectsList === undefined) {
      return;
    }

    autoStartedRef.current = true;
    void (async (): Promise<void> => {
      await setJobMonitorConfigMutation.mutateAsync({
        list_id: jobProspectsList.list_id,
        enabled: true,
      });
      startJobDiscoveryMutation.mutate();
    })();
  }, [
    targetComplete,
    profileComplete,
    preferencesComplete,
    jobMonitorConfig?.enabled,
    jobProspectsList,
    setJobMonitorConfigMutation,
    startJobDiscoveryMutation,
  ]);

  const profileInProgress: boolean =
    isSourceStepInProgress("linkedin_profile_upload", sources) ||
    linkedinProfileProcessing;

  const enrichmentProgressLabel: string = (() => {
    if (orgEnrichmentStatus === undefined) {
      return "Enrichment process still running…";
    }
    if (orgEnrichmentStatus.progress_message !== null) {
      return orgEnrichmentStatus.progress_message;
    }
    return `Enriching company data (${orgEnrichmentStatus.orgs_enriched.toLocaleString()} of ${orgEnrichmentStatus.orgs_total.toLocaleString()})…`;
  })();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
        <p className="text-muted-foreground">
          Set up job search to monitor career pages at companies in your network.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="mt-0.5 shrink-0">
              <SetupStepStatusIcon
                complete={targetComplete}
                inProgress={enrichmentInProgress && !targetComplete}
              />
            </div>
            <div className="space-y-1">
              <CardTitle className="text-base">
                Select organizations for jobs
              </CardTitle>
              <CardDescription>
                Star companies in your network that you would like to work at.
              </CardDescription>
              {enrichmentInProgress ? (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" />
                  {enrichmentProgressLabel}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {starredCount === 0
                    ? "0 organizations selected for job search"
                    : `${starredCount.toLocaleString()} organization${starredCount === 1 ? "" : "s"} selected for job search`}
                </p>
              )}
            </div>
          </div>
          {!enrichmentInProgress ? (
            <Button variant="outline" size="sm" asChild>
              <Link href="/graph?tab=organizations">
                {starredCount === 0 ? (
                  <>
                    Go to Organizations tab
                    <ArrowRight className="size-4" />
                  </>
                ) : (
                  "Edit"
                )}
              </Link>
            </Button>
          ) : null}
        </CardHeader>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="mt-0.5 shrink-0">
              <SetupStepStatusIcon
                complete={profileComplete}
                inProgress={profileInProgress}
              />
            </div>
            <div className="space-y-1">
              <CardTitle className="text-base">Upload your LinkedIn profile</CardTitle>
              <CardDescription>
                Export your profile as PDF so we can match you to relevant roles.
              </CardDescription>
              {linkedinProfileUploadError ? (
                <p className="text-xs text-destructive">{linkedinProfileUploadError}</p>
              ) : null}
            </div>
          </div>
          {profileComplete ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Uploaded</span>
              <button
                type="button"
                className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                onClick={() => setLinkedinProfileDialogOpen(true)}
                disabled={uploadMutation.isPending || profileInProgress}
              >
                re-upload
              </button>
            </div>
          ) : profileInProgress ? (
            <Button variant="outline" size="sm" disabled>
              <Loader2 className="size-4 animate-spin" />
              Processing…
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setLinkedinProfileDialogOpen(true)}
              disabled={uploadMutation.isPending}
            >
              <Plus className="size-4" />
              Upload
            </Button>
          )}
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex gap-3">
            <div className="mt-0.5 shrink-0">
              <SetupStepStatusIcon
                complete={preferencesComplete}
                inProgress={false}
              />
            </div>
            <div className="space-y-1">
              <CardTitle className="text-base">Describe your ideal roles</CardTitle>
              <CardDescription>
                Tell us what kinds of jobs, companies, and locations you are looking for.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            className="min-h-[80px] w-full rounded-md border bg-background px-3 py-2 text-sm"
            placeholder="e.g. Senior backend engineer, distributed systems, Python or Go, remote or SF Bay Area."
            value={preferencesText}
            onChange={(e) => setPreferencesText(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="rounded-md border bg-background px-2 py-1.5 text-sm"
              value={locationPref ?? ""}
              onChange={(e) => setLocationPref(e.target.value || null)}
            >
              <option value="">Location…</option>
              <option value="remote">Remote only</option>
              <option value="in_person">In-person</option>
              <option value="either">Remote or in-person</option>
            </select>
            {locationPref && locationPref !== "remote" ? (
              <input
                type="text"
                className="rounded-md border bg-background px-2 py-1.5 text-sm sm:w-48"
                placeholder="City (e.g. San Francisco)"
                value={locationCity}
                onChange={(e) => setLocationCity(e.target.value)}
              />
            ) : null}
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={
              setJobPreferencesMutation.isPending || !preferencesText.trim()
            }
            onClick={() =>
              setJobPreferencesMutation.mutate({
                text: preferencesText,
                location_pref: locationPref,
                location_city: locationCity || null,
              })
            }
          >
            {setJobPreferencesMutation.isPending ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Saving…
              </>
            ) : preferencesComplete ? (
              "Saved"
            ) : (
              "Save preferences"
            )}
          </Button>
        </CardContent>
      </Card>

      {jobDiscoveryStatus?.state === "running" ? (
        <p className="text-sm text-muted-foreground">
          {jobDiscoveryStatus.progress_message ?? jobDiscoveryStatus.message}
        </p>
      ) : null}

      <LinkedInProfileUploadDialog
        open={linkedinProfileDialogOpen}
        onOpenChange={setLinkedinProfileDialogOpen}
        onFileSelect={(file) => {
          void handleLinkedInProfileUpload(file);
        }}
        isPending={uploadMutation.isPending}
        isProcessing={linkedinProfileProcessing}
        error={linkedinProfileUploadError}
        isComplete={linkedinProfileSource?.sync_state === "complete"}
      />
    </div>
  );
}
