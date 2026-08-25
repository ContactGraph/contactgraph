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
  JobScoringWeights,
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
import { FUNDING_STAGE_OPTIONS } from "@/lib/company-funding-stage";
import { cn } from "@/lib/utils";
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

const DEFAULT_SCORING_WEIGHTS: JobScoringWeights = {
  role: 1.0,
  qualification: 0.9,
  seniority: 0.85,
  location: 0.9,
  funding_stage: 0.7,
};

// Ordinals must stay in sync with job_seniority.py.
const SENIORITY_LEVELS: ReadonlyArray<{ value: number; label: string }> = [
  { value: 0, label: "Intern" },
  { value: 1, label: "Entry" },
  { value: 2, label: "Associate" },
  { value: 3, label: "Mid" },
  { value: 4, label: "Senior" },
  { value: 5, label: "Staff / Principal" },
  { value: 6, label: "Manager" },
  { value: 7, label: "Director" },
  { value: 8, label: "VP" },
  { value: 9, label: "C-level" },
];

const SCORING_WEIGHT_SLIDERS: ReadonlyArray<{
  key: keyof JobScoringWeights;
  label: string;
}> = [
  { key: "role", label: "Role / function" },
  { key: "qualification", label: "Qualification" },
  { key: "seniority", label: "Seniority" },
  { key: "location", label: "Location" },
  { key: "funding_stage", label: "Funding stage" },
];

function scoringWeightsEqual(
  left: JobScoringWeights,
  right: JobScoringWeights,
): boolean {
  return SCORING_WEIGHT_SLIDERS.every(
    (item) => Math.abs(left[item.key] - right[item.key]) < 0.005,
  );
}

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
  const [preferredFundingStages, setPreferredFundingStages] = useState<
    string[] | null
  >(null);
  const [scoringWeights, setScoringWeights] = useState<JobScoringWeights | null>(
    null,
  );
  const [scoringWeightsHydrated, setScoringWeightsHydrated] =
    useState<boolean>(false);
  const [targetSeniorityMin, setTargetSeniorityMin] = useState<number | null>(
    null,
  );
  const [targetSeniorityMax, setTargetSeniorityMax] = useState<number | null>(
    null,
  );
  const [seniorityHydrated, setSeniorityHydrated] = useState<boolean>(false);

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => proxyPost<ListSourcesResult>("list-sources"),
    refetchInterval: linkedinProfileProcessing ? 2000 : false,
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
      regenerate_role_suggestions?: boolean;
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
        void queryClient.invalidateQueries({ queryKey: ["flat-jobs"] });
        void queryClient.invalidateQueries({ queryKey: ["org-jobs"] });
      } else {
        setLinkedinProfileUploadError(
          "Could not read that PDF. Try a LinkedIn PDF export or a resume PDF.",
        );
      }
    }
  }, [linkedinProfileProcessing, linkedinProfileSource, queryClient]);

  useEffect(() => {
    const serverText: string | null = jobPreferencesQuery.data?.text ?? null;
    const suggestedText: string | null =
      jobPreferencesQuery.data?.suggested_text ?? null;
    if (preferencesText === "") {
      if (serverText !== null && serverText !== "") {
        setPreferencesText(serverText);
      } else if (suggestedText !== null && suggestedText !== "") {
        setPreferencesText(suggestedText);
      }
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
    const serverStages: string[] | null =
      jobPreferencesQuery.data?.preferred_funding_stages ?? null;
    if (serverStages !== null && preferredFundingStages === null) {
      setPreferredFundingStages(serverStages);
    }
    if (!scoringWeightsHydrated && jobPreferencesQuery.data !== undefined) {
      const serverWeights: JobScoringWeights =
        jobPreferencesQuery.data.scoring_weights ?? DEFAULT_SCORING_WEIGHTS;
      setScoringWeights(serverWeights);
      setScoringWeightsHydrated(true);
    }
    if (!seniorityHydrated && jobPreferencesQuery.data !== undefined) {
      setTargetSeniorityMin(jobPreferencesQuery.data.target_seniority_min);
      setTargetSeniorityMax(jobPreferencesQuery.data.target_seniority_max);
      setSeniorityHydrated(true);
    }
  }, [
    jobPreferencesQuery.data,
    jobPreferencesQuery.data?.text,
    jobPreferencesQuery.data?.suggested_text,
    jobPreferencesQuery.data?.location_pref,
    jobPreferencesQuery.data?.location_city,
    jobPreferencesQuery.data?.commute_max_minutes,
    jobPreferencesQuery.data?.commute_note,
    jobPreferencesQuery.data?.preferred_funding_stages,
    jobPreferencesQuery.data?.scoring_weights,
    preferencesText,
    locationPref,
    locationCity,
    commuteMaxMinutes,
    commuteNote,
    preferredFundingStages,
    scoringWeightsHydrated,
    seniorityHydrated,
  ]);

  const effectiveScoringWeights: JobScoringWeights =
    scoringWeights ?? DEFAULT_SCORING_WEIGHTS;

  const preferencesDirty: boolean = useMemo(() => {
    const serverText: string = jobPreferencesQuery.data?.text ?? "";
    const suggestedText: string = jobPreferencesQuery.data?.suggested_text ?? "";
    const baselineText: string = serverText !== "" ? serverText : suggestedText;
    const serverLocPref: string | null =
      jobPreferencesQuery.data?.location_pref ?? null;
    const serverCity: string = jobPreferencesQuery.data?.location_city ?? "";
    const serverCommute: string =
      jobPreferencesQuery.data?.commute_max_minutes != null
        ? String(jobPreferencesQuery.data.commute_max_minutes)
        : "";
    const serverCommuteNote: string =
      jobPreferencesQuery.data?.commute_note ?? "";
    const serverStages: string[] =
      jobPreferencesQuery.data?.preferred_funding_stages ?? [];
    const localStages: string[] = preferredFundingStages ?? [];
    const stagesEqual: boolean =
      serverStages.length === localStages.length &&
      serverStages.every((stage: string) => localStages.includes(stage));
    const serverWeights: JobScoringWeights =
      jobPreferencesQuery.data?.scoring_weights ?? DEFAULT_SCORING_WEIGHTS;
    const weightsEqual: boolean = scoringWeightsEqual(
      effectiveScoringWeights,
      serverWeights,
    );
    const seniorityEqual: boolean =
      targetSeniorityMin ===
        (jobPreferencesQuery.data?.target_seniority_min ?? null) &&
      targetSeniorityMax ===
        (jobPreferencesQuery.data?.target_seniority_max ?? null);
    if (
      !baselineText.trim() &&
      !preferencesText.trim() &&
      stagesEqual &&
      weightsEqual &&
      seniorityEqual
    ) {
      return false;
    }
    return (
      preferencesText.trim() !== baselineText.trim() ||
      locationPref !== serverLocPref ||
      locationCity !== serverCity ||
      commuteMaxMinutes !== serverCommute ||
      commuteNote !== serverCommuteNote ||
      !stagesEqual ||
      !weightsEqual ||
      !seniorityEqual
    );
  }, [
    preferencesText,
    locationPref,
    locationCity,
    commuteMaxMinutes,
    commuteNote,
    preferredFundingStages,
    effectiveScoringWeights,
    jobPreferencesQuery.data?.text,
    jobPreferencesQuery.data?.suggested_text,
    jobPreferencesQuery.data?.location_pref,
    jobPreferencesQuery.data?.location_city,
    jobPreferencesQuery.data?.commute_max_minutes,
    jobPreferencesQuery.data?.commute_note,
    jobPreferencesQuery.data?.preferred_funding_stages,
    jobPreferencesQuery.data?.scoring_weights,
    jobPreferencesQuery.data?.target_seniority_min,
    jobPreferencesQuery.data?.target_seniority_max,
    targetSeniorityMin,
    targetSeniorityMax,
  ]);

  useEffect(() => {
    onDirtyChange?.(preferencesDirty);
  }, [preferencesDirty, onDirtyChange]);

  const togglePreferredFundingStage = useCallback((stage: string): void => {
    setPreferredFundingStages((current: string[] | null) => {
      const existing: string[] = current ?? [];
      if (existing.includes(stage)) {
        return existing.filter((value: string) => value !== stage);
      }
      return [...existing, stage];
    });
  }, []);

  const updateScoringWeight = useCallback(
    (key: keyof JobScoringWeights, percent: number): void => {
      const clamped: number = Math.max(0, Math.min(100, percent)) / 100;
      setScoringWeights((current: JobScoringWeights | null) => ({
        ...(current ?? DEFAULT_SCORING_WEIGHTS),
        [key]: clamped,
      }));
    },
    [],
  );

  const handleLinkedInProfileUpload = useCallback(
    async (file: File, regenerateRoleSuggestions: boolean): Promise<void> => {
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
        regenerate_role_suggestions: regenerateRoleSuggestions,
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
              <CardTitle className="text-base">
                Upload your LinkedIn PDF or resume
              </CardTitle>
              <CardDescription>
                We use your background to suggest roles and score how well you
                match each job&apos;s requirements.
              </CardDescription>
              {profileInProgress ? (
                <p className="text-xs text-muted-foreground">
                  Reading your PDF and analyzing your background — usually about
                  15–30 seconds. You can leave this page; it finishes in the
                  background.
                </p>
              ) : null}
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
                Or leave blank and we&apos;ll match from your profile.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            className="min-h-[140px] w-full rounded-md border bg-background px-3 py-2 text-sm"
            placeholder="e.g. Senior backend engineer, distributed systems, Python or Go, remote or SF Bay Area."
            value={preferencesText}
            onChange={(e) => setPreferencesText(e.target.value)}
          />
          {jobPreferencesQuery.data?.suggested_text &&
          (!jobPreferencesQuery.data.text ||
            preferencesText === jobPreferencesQuery.data.suggested_text) ? (
            <p className="text-xs text-muted-foreground">
              Suggested directions from your profile — we match jobs against any of
              them. Edit or trim as needed, then save.
            </p>
          ) : null}          <div className="flex flex-wrap items-center gap-2">
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
                max commute (minutes)
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
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">
              Target level
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <select
                className="rounded-md border bg-background px-2 py-1.5 text-sm"
                value={targetSeniorityMin ?? ""}
                onChange={(e) => {
                  const next: number | null =
                    e.target.value === "" ? null : parseInt(e.target.value, 10);
                  setTargetSeniorityMin(next);
                  if (next === null) {
                    setTargetSeniorityMax(null);
                  } else if (
                    targetSeniorityMax === null ||
                    targetSeniorityMax < next
                  ) {
                    setTargetSeniorityMax(next);
                  }
                }}
              >
                <option value="">Auto (from your description)</option>
                {SENIORITY_LEVELS.map((level) => (
                  <option key={level.value} value={level.value}>
                    {level.label}
                  </option>
                ))}
              </select>
              {targetSeniorityMin !== null ? (
                <>
                  <span className="text-sm text-muted-foreground">to</span>
                  <select
                    className="rounded-md border bg-background px-2 py-1.5 text-sm"
                    value={targetSeniorityMax ?? targetSeniorityMin}
                    onChange={(e) =>
                      setTargetSeniorityMax(parseInt(e.target.value, 10))
                    }
                  >
                    {SENIORITY_LEVELS.filter(
                      (level) => level.value >= targetSeniorityMin,
                    ).map((level) => (
                      <option key={level.value} value={level.value}>
                        {level.label}
                      </option>
                    ))}
                  </select>
                </>
              ) : null}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {targetSeniorityMin === null
                ? `Inferred from your description and profile${
                    jobPreferencesQuery.data?.resolved_seniority_label &&
                    jobPreferencesQuery.data.resolved_seniority_label !==
                      "Unknown"
                      ? `: ${jobPreferencesQuery.data.resolved_seniority_label}`
                      : ""
                  }. Set it explicitly to filter harder.`
                : "Roles below this range are heavily penalized; roles above it are treated as a stretch."}
            </p>
          </div>
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">
              Preferred funding stages
            </p>
            <div className="flex flex-wrap gap-1.5">
              {FUNDING_STAGE_OPTIONS.map((option) => {
                const selected: boolean = (
                  preferredFundingStages ?? []
                ).includes(option.value);
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={cn(
                      "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                      selected
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-background hover:bg-muted",
                    )}
                    onClick={() => togglePreferredFundingStage(option.value)}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="space-y-2">
            <div>
              <p className="text-xs font-medium text-muted-foreground">
                How much should a poor fit hurt the match?
              </p>
              <p className="text-[11px] text-muted-foreground">
                100% = a 0 on that dimension zeroes the match. 0% = ignore that
                dimension.
              </p>
            </div>
            <div className="space-y-2">
              {SCORING_WEIGHT_SLIDERS.map((item) => {
                const percent: number = Math.round(
                  effectiveScoringWeights[item.key] * 100,
                );
                return (
                  <label
                    key={item.key}
                    className="grid grid-cols-[7.5rem_1fr_2.5rem] items-center gap-2 text-xs"
                  >
                    <span className="text-muted-foreground">{item.label}</span>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      step={5}
                      value={percent}
                      onChange={(e) =>
                        updateScoringWeight(
                          item.key,
                          parseInt(e.target.value, 10),
                        )
                      }
                      className="w-full accent-primary"
                    />
                    <span className="tabular-nums text-muted-foreground">
                      {percent}%
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={preferencesDirty ? "default" : "outline"}
              size="sm"
              disabled={
                setJobPreferencesMutation.isPending ||
                !preferencesText.trim() ||
                !preferencesDirty
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
                  preferred_funding_stages:
                    (preferredFundingStages ?? []).length > 0
                      ? preferredFundingStages
                      : null,
                  scoring_weights: effectiveScoringWeights,
                  target_seniority_min: targetSeniorityMin,
                  target_seniority_max: targetSeniorityMax,
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
            {preferencesComplete ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={setJobPreferencesMutation.isPending}
                onClick={() => {
                  setPreferencesText("");
                  setJobPreferencesMutation.mutate({
                    text: "",
                    location_pref: locationPref,
                    location_city: locationCity || null,
                    commute_max_minutes: commuteMaxMinutes
                      ? parseInt(commuteMaxMinutes, 10)
                      : null,
                    commute_note: commuteNote.trim() || null,
                    preferred_funding_stages:
                      (preferredFundingStages ?? []).length > 0
                        ? preferredFundingStages
                        : null,
                    scoring_weights: effectiveScoringWeights,
                    target_seniority_min: targetSeniorityMin,
                    target_seniority_max: targetSeniorityMax,
                  });
                }}
              >
                Clear
              </Button>
            ) : null}
          </div>
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
        onFileSelect={(file, regenerateRoleSuggestions) => {
          void handleLinkedInProfileUpload(file, regenerateRoleSuggestions);
        }}
        isPending={uploadMutation.isPending}
        isProcessing={linkedinProfileProcessing}
        error={linkedinProfileUploadError}
        isComplete={linkedinProfileSource?.sync_state === "complete"}
      />
    </div>
  );
}
