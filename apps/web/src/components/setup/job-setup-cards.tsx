"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { LinkedInProfileUploadDialog } from "@/components/setup/linkedin-profile-upload-dialog";
import { SetupStepStatusIcon } from "@/components/setup/setup-step-status-icon";
import { JobTargetCompaniesCard } from "@/components/target-selection/job-target-companies-card";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  JobMonitorConfigResult,
  JobPreferencesResult,
  JobScanStatusResult,
  SetJobPreferencesRequest,
  ListOrgListsResult,
  ListSourcesResult,
  OrgEnrichmentStatusResult,
  OrgListSummary,
  SetJobMonitorConfigRequest,
  SourceSummary,
  SourceType,
  UploadSourceResult,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";
import { useGraphEvents } from "@/lib/use-graph-events";
import { useJobEvents } from "@/lib/use-job-events";
import {
  findJobProspectsList,
  hasJobPreferences,
  hasTargetCompanies,
  isLinkedInProfileComplete,
  isOrgEnrichmentBlocking,
  isSourceStepInProgress,
  sourceForType,
} from "@/lib/setup-utils";

export function JobSetupCards({
  compact = false,
  onDirtyChange,
}: {
  compact?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  useGraphEvents();
  useJobEvents();
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
  const [commuteMaxMinutes, setCommuteMaxMinutes] = useState<string>("");
  const [commuteNote, setCommuteNote] = useState<string>("");

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => proxyPost<ListSourcesResult>("list-sources"),
  });

  const orgListsQuery = useQuery({
    queryKey: ["org-lists"],
    queryFn: () => proxyPost<ListOrgListsResult>("list-org-lists"),
  });

  const orgEnrichmentQuery = useQuery({
    queryKey: ["org-enrichment-status"],
    queryFn: () =>
      proxyPost<OrgEnrichmentStatusResult>("get-org-enrichment-status"),
  });

  const jobPreferencesQuery = useQuery({
    queryKey: ["job-preferences"],
    queryFn: () => proxyPost<JobPreferencesResult>("get-job-preferences"),
  });

  const jobMonitorConfigQuery = useQuery({
    queryKey: ["job-monitor-config"],
    queryFn: () => proxyPost<JobMonitorConfigResult>("get-job-monitor-config"),
  });

  const jobScanStatusQuery = useQuery({
    queryKey: ["job-scan-status"],
    queryFn: () => proxyPost<JobScanStatusResult>("get-job-scan-status"),
    enabled: jobMonitorConfigQuery.data?.enabled === true,
  });

  const setJobPreferencesMutation = useMutation({
    mutationFn: (params: SetJobPreferencesRequest) =>
      proxyPost<JobPreferencesResult>("set-job-preferences", params),
    onSuccess: async (result: JobPreferencesResult) => {
      toast.success(result.message);
      await queryClient.invalidateQueries({ queryKey: ["job-preferences"] });
      await queryClient.invalidateQueries({ queryKey: ["org-jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["flat-jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["job-scan-status"] });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const dismissSuggestionMutation = useMutation({
    mutationFn: () =>
      proxyPost<JobPreferencesResult>("dismiss-job-preferences-suggestion"),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["job-preferences"] });
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
  const jobScanStatus: JobScanStatusResult | undefined = jobScanStatusQuery.data;
  const linkedinProfileSource: SourceSummary | undefined = sourceForType(
    sources,
    "linkedin_profile_upload",
  );
  const jobProspectsList: OrgListSummary | undefined =
    findJobProspectsList(orgLists);

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
        void queryClient.invalidateQueries({ queryKey: ["job-preferences"] });
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
    const serverCommute: number | null =
      jobPreferencesQuery.data?.commute_max_minutes ?? null;
    if (serverCommute !== null && commuteMaxMinutes === "") {
      setCommuteMaxMinutes(String(serverCommute));
    }
    const serverCommuteNote: string | null =
      jobPreferencesQuery.data?.commute_note ?? null;
    if (serverCommuteNote !== null && commuteNote === "") {
      setCommuteNote(serverCommuteNote);
    }
  }, [
    jobPreferencesQuery.data?.text,
    jobPreferencesQuery.data?.location_pref,
    jobPreferencesQuery.data?.location_city,
    jobPreferencesQuery.data?.commute_max_minutes,
    jobPreferencesQuery.data?.commute_note,
    preferencesText,
    locationPref,
    locationCity,
    commuteMaxMinutes,
    commuteNote,
  ]);

  const serverPreferencesText: string = jobPreferencesQuery.data?.text ?? "";
  const hasExistingPreferencesText: boolean =
    serverPreferencesText.trim().length > 0;
  const suggestion: string | null = jobPreferencesQuery.data?.suggestion ?? null;
  const suggestionPending: boolean =
    jobPreferencesQuery.data?.suggestion_pending ?? false;
  const prefilledSuggestionRef = useRef<string | null>(null);

  useEffect(() => {
    if (!suggestionPending || suggestion === null) return;
    if (hasExistingPreferencesText) return;
    if (prefilledSuggestionRef.current === suggestion) return;
    if (preferencesText.trim() !== "") return;
    prefilledSuggestionRef.current = suggestion;
    setPreferencesText(suggestion);
  }, [
    suggestionPending,
    suggestion,
    hasExistingPreferencesText,
    preferencesText,
  ]);

  const showSuggestionPrefillHint: boolean =
    suggestionPending &&
    suggestion !== null &&
    !hasExistingPreferencesText &&
    preferencesText === suggestion;
  const showSuggestionReplaceBanner: boolean =
    suggestionPending && suggestion !== null && hasExistingPreferencesText;

  const preferencesDirty: boolean = useMemo(() => {
    const serverText: string = jobPreferencesQuery.data?.text ?? "";
    const serverLocPref: string | null =
      jobPreferencesQuery.data?.location_pref ?? null;
    const serverCity: string = jobPreferencesQuery.data?.location_city ?? "";
    const serverCommute: string =
      jobPreferencesQuery.data?.commute_max_minutes != null
        ? String(jobPreferencesQuery.data.commute_max_minutes)
        : "";
    const serverCommuteNote: string =
      jobPreferencesQuery.data?.commute_note ?? "";
    if (!serverText && !preferencesText.trim()) return false;
    return (
      preferencesText !== serverText ||
      locationPref !== serverLocPref ||
      locationCity !== serverCity ||
      commuteMaxMinutes !== serverCommute ||
      commuteNote !== serverCommuteNote
    );
  }, [
    preferencesText,
    locationPref,
    locationCity,
    commuteMaxMinutes,
    commuteNote,
    jobPreferencesQuery.data?.text,
    jobPreferencesQuery.data?.location_pref,
    jobPreferencesQuery.data?.location_city,
    jobPreferencesQuery.data?.commute_max_minutes,
    jobPreferencesQuery.data?.commute_note,
  ]);

  useEffect(() => {
    onDirtyChange?.(preferencesDirty);
  }, [preferencesDirty, onDirtyChange]);

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
    void setJobMonitorConfigMutation.mutateAsync({
      list_id: jobProspectsList.list_id,
      enabled: true,
    });
  }, [
    targetComplete,
    profileComplete,
    preferencesComplete,
    jobMonitorConfig?.enabled,
    jobProspectsList,
    setJobMonitorConfigMutation,
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
    <div className={compact ? "space-y-4" : "space-y-6"}>
      {!compact ? (
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
          <p className="text-muted-foreground">
            Set up job search to monitor career pages at companies in your network.
          </p>
        </div>
      ) : null}

      <JobTargetCompaniesCard
        targetComplete={targetComplete}
        enrichmentInProgress={enrichmentInProgress}
        enrichmentProgressLabel={enrichmentProgressLabel}
      />

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
          {showSuggestionReplaceBanner && suggestion !== null ? (
            <div className="space-y-2 rounded-md border border-primary/30 bg-primary/5 p-3">
              <p className="text-xs font-medium text-foreground">
                Suggested from your LinkedIn profile
              </p>
              <p className="text-sm text-muted-foreground">{suggestion}</p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="default"
                  size="sm"
                  onClick={() => setPreferencesText(suggestion)}
                >
                  Use suggestion
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={dismissSuggestionMutation.isPending}
                  onClick={() => dismissSuggestionMutation.mutate()}
                >
                  Keep current
                </Button>
              </div>
            </div>
          ) : null}
          <textarea
            className="min-h-[80px] w-full rounded-md border bg-background px-3 py-2 text-sm"
            placeholder="e.g. Senior backend engineer, distributed systems, Python or Go, remote or SF Bay Area."
            value={preferencesText}
            onChange={(e) => setPreferencesText(e.target.value)}
          />
          {showSuggestionPrefillHint ? (
            <p className="text-xs text-muted-foreground">
              Suggested from your LinkedIn profile — edit it as you like, then
              save.
            </p>
          ) : null}
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
          {locationPref && locationPref !== "remote" ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="number"
                min={0}
                className="w-20 rounded-md border bg-background px-2 py-1.5 text-sm"
                placeholder="45"
                value={commuteMaxMinutes}
                onChange={(e) => setCommuteMaxMinutes(e.target.value)}
              />
              <span className="text-sm text-muted-foreground">
                max commute (min)
              </span>
            </div>
          ) : null}
          <input
            type="text"
            className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            placeholder="e.g. Willing to commute to Santa Clara if only 1 day/week"
            value={commuteNote}
            onChange={(e) => setCommuteNote(e.target.value)}
          />
          <Button
            variant={preferencesDirty ? "default" : "outline"}
            size="sm"
            disabled={
              setJobPreferencesMutation.isPending || !preferencesText.trim()
            }
            onClick={() =>
              setJobPreferencesMutation.mutate({
                text: preferencesText,
                location_pref: locationPref,
                location_city: locationCity || null,
                commute_max_minutes: commuteMaxMinutes
                  ? parseInt(commuteMaxMinutes, 10)
                  : null,
                commute_note: commuteNote.trim() || null,
              })
            }
          >
            {setJobPreferencesMutation.isPending ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Saving…
              </>
            ) : preferencesDirty ? (
              "Save"
            ) : preferencesComplete ? (
              "Saved"
            ) : (
              "Save preferences"
            )}
          </Button>
        </CardContent>
      </Card>

      {jobMonitorConfig?.enabled && jobScanStatus !== undefined && jobScanStatus.total > 0 ? (
        <p className="text-sm text-muted-foreground">
          {jobScanStatus.scanning_active || jobScanStatus.scanned < jobScanStatus.total
            ? `${jobScanStatus.scanned} of ${jobScanStatus.total} companies scanned today — scanning in progress.`
            : `${jobScanStatus.scanned} of ${jobScanStatus.total} companies scanned today.`}
        </p>
      ) : jobMonitorConfig?.enabled ? (
        <p className="text-sm text-muted-foreground">
          Your companies will be scanned automatically within a few minutes.
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
