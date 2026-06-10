"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Circle,
  ListPlus,
  Loader2,
  Plus,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { LinkedInConnectionsUploadDialog } from "@/components/setup/linkedin-connections-upload-dialog";
import { LinkedInProfileUploadDialog } from "@/components/setup/linkedin-profile-upload-dialog";
import { PhoneContactsUploadDialog } from "@/components/setup/phone-contacts-upload-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { resolveLinkedInConnectionsUpload } from "@/lib/linkedin-connections-upload";
import type {
  CancelOrgEnrichmentResult,
  ConnectSourceResult,
  CreateOrgListResult,
  EnrichOrgsResult,
  JobDiscoveryStatusResult,
  JobMonitorConfigResult,
  JobPreferencesResult,
  ListOrgListsResult,
  SetJobMonitorConfigRequest,
  StartJobDiscoveryResult,
  ListSourcesResult,
  NetworkStatusResult,
  OrgEnrichmentStatusResult,
  OrgListSummary,
  PollConnectResult,
  SourceSummary,
  SourceType,
  SyncSourceResult,
  SyncState,
  UploadSourceResult,
} from "@/lib/api-types";
import { formatSourceType, SyncStateBadge } from "@/lib/formatters";
import { proxyPost } from "@/lib/proxy-client";
import { cn } from "@/lib/utils";

const IMPORT_COMPLETE_STATES: ReadonlySet<SyncState> = new Set([
  "partial",
  "complete",
]);

type SetupStepId =
  | "phone"
  | "gmail"
  | "linkedin"
  | "linkedin_profile"
  | "org_enrichment"
  | "target_companies"
  | "job_preferences"
  | "job_scrapers";

type SetupSectionId = "network" | "job_search";

interface SetupStep {
  id: SetupStepId;
  section: SetupSectionId;
  title: string;
  description: string;
  optional?: boolean;
  comingSoon?: boolean;
}

interface FutureSection {
  id: string;
  title: string;
  description: string;
}

const setupSteps: ReadonlyArray<SetupStep> = [
  {
    id: "phone",
    section: "network",
    title: "Import phone contacts",
    description:
      "Upload phone contacts (.vcf) from iPhone or Android — this is your authoritative network.",
  },
  {
    id: "linkedin",
    section: "network",
    title: "Import LinkedIn connections",
    description:
      "Upload your LinkedIn Connections.csv — identifies your strong professional ties.",
  },
  {
    id: "org_enrichment",
    section: "network",
    title: "Enrich companies",
    description:
      "Look up company websites and profiles — maps companies where you have strong ties.",
  },
  {
    id: "linkedin_profile",
    section: "job_search",
    title: "Upload your LinkedIn profile",
    description:
      "Export your profile as PDF so we can match you to relevant roles and companies.",
  },
  {
    id: "target_companies",
    section: "job_search",
    title: "Select target companies",
    description:
      "Browse companies with strong ties and filter by industry, size, and more.",
  },
  {
    id: "job_preferences",
    section: "job_search",
    title: "Describe your ideal roles",
    description:
      "Tell us what kinds of jobs you're looking for so we only show relevant results.",
  },
  {
    id: "job_scrapers",
    section: "job_search",
    title: "Search for jobs",
    description:
      "Monitor career pages at your target companies and get daily alerts.",
  },
];

const futureSections: ReadonlyArray<FutureSection> = [
  {
    id: "hiring",
    title: "Hiring",
    description:
      "Edit your organization profile, upload a job description, and find warm matches in your network.",
  },
  {
    id: "fundraising",
    title: "Fundraising",
    description:
      "Identify investors and warm introductions through your professional network.",
  },
  {
    id: "outreach",
    title: "Ongoing warm outreach",
    description:
      "Stay in touch with key relationships — a personal CRM built on your network.",
  },
];

const sectionMeta: Record<
  SetupSectionId,
  { title: string; description: string }
> = {
  network: {
    title: "Build your network",
    description:
      "Start here. Import contacts and enrich companies before using any workflow below.",
  },
  job_search: {
    title: "Job search",
    description:
      "Upload your profile, pick target companies, and set up job monitoring.",
  },
};

function sourceForType(
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

function stepComplete(
  stepId: SetupStepId,
  sources: ReadonlyArray<SourceSummary>,
  orgEnrichmentStatus: OrgEnrichmentStatusResult | undefined,
  orgLists: ReadonlyArray<OrgListSummary>,
  jobMonitorConfig: JobMonitorConfigResult | undefined,
  jobPreferences: JobPreferencesResult | undefined,
): boolean {
  switch (stepId) {
    case "gmail": {
      const source = sourceForType(sources, "google_mail");
      return source !== undefined && IMPORT_COMPLETE_STATES.has(source.sync_state);
    }
    case "phone": {
      const source = sourceForType(sources, "phone_contacts_upload");
      return source !== undefined && source.sync_state === "complete";
    }
    case "linkedin_profile": {
      const source = sourceForType(sources, "linkedin_profile_upload");
      return source !== undefined && source.sync_state === "complete";
    }
    case "linkedin": {
      const source = sourceForType(sources, "linkedin_connections_upload");
      return source !== undefined && source.sync_state === "complete";
    }
    case "org_enrichment":
      return (
        orgEnrichmentStatus !== undefined &&
        orgEnrichmentStatus.orgs_total > 0 &&
        orgEnrichmentStatus.orgs_enriched >= orgEnrichmentStatus.orgs_total
      );
    case "target_companies":
      return orgLists.some((list) => list.org_count > 0);
    case "job_preferences":
      return (jobPreferences?.text ?? "").trim().length > 0;
    case "job_scrapers":
      return jobMonitorConfig?.enabled === true;
    default:
      return false;
  }
}

function stepInProgress(
  stepId: SetupStepId,
  sources: ReadonlyArray<SourceSummary>,
): boolean {
  const typeMap: Partial<Record<SetupStepId, SourceType>> = {
    gmail: "google_mail",
    phone: "phone_contacts_upload",
    linkedin_profile: "linkedin_profile_upload",
    linkedin: "linkedin_connections_upload",
  };
  const sourceType: SourceType | undefined = typeMap[stepId];
  if (sourceType === undefined) {
    return false;
  }
  const source = sourceForType(sources, sourceType);
  return (
    source?.sync_state === "syncing" || source?.sync_state === "pending"
  );
}

interface StepImportStatusDisplay {
  count: number | null;
  suffix: string;
  retryLabel: string;
}

function getStepImportStatus(
  stepId: SetupStepId,
  sources: ReadonlyArray<SourceSummary>,
  networkStatus: NetworkStatusResult | undefined,
): StepImportStatusDisplay | null {
  switch (stepId) {
    case "phone": {
      const source = sourceForType(sources, "phone_contacts_upload");
      if (source?.sync_state !== "complete") {
        return null;
      }
      return {
        count: source.contacts_resolved,
        suffix: "Uploaded",
        retryLabel: "re-upload",
      };
    }
    case "gmail": {
      if (!networkStatus?.gmail_connected) {
        return null;
      }
      const source = sourceForType(sources, "google_mail");
      return {
        count: networkStatus.gmail_matched_count || source?.contacts_resolved || null,
        suffix: "Imported",
        retryLabel: "reconnect",
      };
    }
    case "linkedin": {
      const source = sourceForType(sources, "linkedin_connections_upload");
      if (source?.sync_state !== "complete") {
        return null;
      }
      return {
        count: source.contacts_resolved,
        suffix: "Imported",
        retryLabel: "re-upload",
      };
    }
    case "linkedin_profile": {
      const source = sourceForType(sources, "linkedin_profile_upload");
      if (source?.sync_state !== "complete") {
        return null;
      }
      return {
        count: null,
        suffix: "Uploaded",
        retryLabel: "re-upload",
      };
    }
    case "org_enrichment":
    case "target_companies":
    case "job_scrapers":
      return null;
    default:
      return null;
  }
}

interface StepActionAreaProps {
  complete: boolean;
  inProgress: boolean;
  pending: boolean;
  status: StepImportStatusDisplay | null;
  primaryLabel: string;
  inProgressLabel?: string;
  pendingLabel?: string;
  onPrimary: () => void;
  disabled: boolean;
}

function StepActionArea({
  complete,
  inProgress,
  pending,
  status,
  primaryLabel,
  inProgressLabel = "Importing…",
  pendingLabel = "Working…",
  onPrimary,
  disabled,
}: StepActionAreaProps) {
  if (inProgress || pending) {
    return (
      <Button variant="outline" size="sm" disabled>
        <Loader2 className="size-4 animate-spin" />
        {inProgress ? inProgressLabel : pendingLabel}
      </Button>
    );
  }

  if (complete && status !== null) {
    const statusText: string =
      status.count !== null
        ? `${status.count.toLocaleString()} ${status.suffix}`
        : `Profile ${status.suffix.toLowerCase()}`;
    return (
      <div className="flex min-w-[6.5rem] flex-col items-end gap-0.5 text-right">
        <p className="text-sm font-medium tabular-nums">{statusText}</p>
        <button
          type="button"
          className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline disabled:opacity-50"
          onClick={onPrimary}
          disabled={disabled}
        >
          {status.retryLabel}
        </button>
      </div>
    );
  }

  return (
    <Button variant="outline" size="sm" onClick={onPrimary} disabled={disabled}>
      <Plus className="size-4" />
      {primaryLabel}
    </Button>
  );
}

function FutureSectionCard({ title, description }: FutureSection) {
  return (
    <Card className="opacity-75">
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="space-y-1">
          <CardTitle className="text-base">{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
        <Badge variant="secondary" className="shrink-0">
          Coming soon
        </Badge>
      </CardHeader>
    </Card>
  );
}

export default function SetupPage() {
  const queryClient = useQueryClient();
  const popupRef = useRef<Window | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [connectMessage, setConnectMessage] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [phoneUploadError, setPhoneUploadError] = useState<string | null>(null);
  const [linkedinProfileUploadError, setLinkedinProfileUploadError] =
    useState<string | null>(null);
  const [connectionsUploadError, setConnectionsUploadError] =
    useState<string | null>(null);
  const [phoneDialogOpen, setPhoneDialogOpen] = useState<boolean>(false);
  const [linkedinConnectionsDialogOpen, setLinkedinConnectionsDialogOpen] =
    useState<boolean>(false);
  const [linkedinProfileDialogOpen, setLinkedinProfileDialogOpen] =
    useState<boolean>(false);
  const [linkedinProfileProcessing, setLinkedinProfileProcessing] =
    useState<boolean>(false);
  const [linkedinConnectionsProcessing, setLinkedinConnectionsProcessing] =
    useState<boolean>(false);
  const [orgEnrichmentMessage, setOrgEnrichmentMessage] = useState<string | null>(
    null,
  );
  const [orgEnrichmentError, setOrgEnrichmentError] = useState<string | null>(null);
  const [selectedTargetListId, setSelectedTargetListId] = useState<string | null>(
    null,
  );
  const [preferencesText, setPreferencesText] = useState<string>("");
  const [locationPref, setLocationPref] = useState<string | null>(null);
  const [locationCity, setLocationCity] = useState<string>("");

  const clearPollTimer = useCallback((): void => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearPollTimer();
      popupRef.current?.close();
    };
  }, [clearPollTimer]);

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => proxyPost<ListSourcesResult>("list-sources"),
    refetchInterval: (query) => {
      const data: ListSourcesResult | undefined = query.state.data;
      const syncing: boolean =
        data?.sources.some((source) => source.sync_state === "syncing") ?? false;
      const pending: boolean =
        data?.sources.some((source) => source.sync_state === "pending") ?? false;
      return syncing || pending || linkedinProfileProcessing || linkedinConnectionsProcessing
        ? 4000
        : false;
    },
  });

  const networkStatusQuery = useQuery({
    queryKey: ["network-status"],
    queryFn: () => proxyPost<NetworkStatusResult>("get-network-status"),
    refetchInterval: 8000,
  });

  const orgEnrichmentStatusQuery = useQuery({
    queryKey: ["org-enrichment-status"],
    queryFn: () =>
      proxyPost<OrgEnrichmentStatusResult>("get-org-enrichment-status"),
    refetchInterval: (query) =>
      query.state.data?.state === "running" ? 2000 : false,
  });

  const orgListsQuery = useQuery({
    queryKey: ["org-lists"],
    queryFn: () => proxyPost<ListOrgListsResult>("list-org-lists"),
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

  const jobPreferencesQuery = useQuery({
    queryKey: ["job-preferences"],
    queryFn: () => proxyPost<JobPreferencesResult>("get-job-preferences"),
  });

  const setJobPreferencesMutation = useMutation({
    mutationFn: (params: { text: string; location_pref: string | null; location_city: string | null }) =>
      proxyPost<JobPreferencesResult>("set-job-preferences", params),
    onSuccess: async (result: JobPreferencesResult) => {
      toast.success(result.message);
      await queryClient.invalidateQueries({ queryKey: ["job-preferences"] });
      await queryClient.invalidateQueries({ queryKey: ["org-jobs"] });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const createOrgListMutation = useMutation({
    mutationFn: (name: string) =>
      proxyPost<CreateOrgListResult>("create-org-list", { name }),
    onSuccess: async (result: CreateOrgListResult) => {
      toast.success(result.message);
      setSelectedTargetListId(result.list_id);
      await queryClient.invalidateQueries({ queryKey: ["org-lists"] });
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

  const enrichOrgsMutation = useMutation({
    mutationFn: () => proxyPost<EnrichOrgsResult>("enrich-orgs"),
    onSuccess: async (result: EnrichOrgsResult) => {
      setOrgEnrichmentError(null);
      setOrgEnrichmentMessage(result.message);
      await queryClient.invalidateQueries({ queryKey: ["org-enrichment-status"] });
      await queryClient.invalidateQueries({ queryKey: ["organizations"] });
    },
    onError: (error: Error) => {
      setOrgEnrichmentMessage(null);
      setOrgEnrichmentError(error.message);
    },
  });

  const syncMutation = useMutation({
    mutationFn: (sourceId?: string) =>
      proxyPost<SyncSourceResult>("sync-source", { source_id: sourceId ?? null }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (payload: {
      source_type: SourceType;
      filename: string;
      content: string;
    }) => proxyPost<UploadSourceResult>("upload-source", payload),
    onSuccess: async (_result, variables) => {
      if (variables.source_type === "phone_contacts_upload") {
        setPhoneUploadError(null);
        setPhoneDialogOpen(false);
      } else if (variables.source_type === "linkedin_profile_upload") {
        setLinkedinProfileUploadError(null);
        setLinkedinProfileProcessing(true);
      } else if (variables.source_type === "linkedin_connections_upload") {
        setConnectionsUploadError(null);
        setLinkedinConnectionsProcessing(true);
        setLinkedinConnectionsDialogOpen(false);
      }
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      await queryClient.invalidateQueries({ queryKey: ["network-status"] });
      await queryClient.invalidateQueries({ queryKey: ["strong-ties"] });
    },
    onError: (error: Error, variables) => {
      if (variables.source_type === "phone_contacts_upload") {
        setPhoneUploadError(error.message);
      } else if (variables.source_type === "linkedin_profile_upload") {
        setLinkedinProfileUploadError(error.message);
      } else if (variables.source_type === "linkedin_connections_upload") {
        setConnectionsUploadError(error.message);
      }
    },
  });

  const sources: SourceSummary[] = sourcesQuery.data?.sources ?? [];
  const linkedinProfileSource: SourceSummary | undefined = sourceForType(
    sources,
    "linkedin_profile_upload",
  );
  const phoneSource: SourceSummary | undefined = sourceForType(
    sources,
    "phone_contacts_upload",
  );
  const linkedinConnectionsSource: SourceSummary | undefined = sourceForType(
    sources,
    "linkedin_connections_upload",
  );

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
      if (linkedinProfileSource.sync_state === "failed") {
        setLinkedinProfileUploadError(
          "Could not read that PDF. Try re-exporting from LinkedIn.",
        );
      } else {
        void queryClient.invalidateQueries({ queryKey: ["user-profile"] });
      }
    }
  }, [linkedinProfileProcessing, linkedinProfileSource, queryClient]);

  useEffect(() => {
    if (!linkedinConnectionsProcessing) {
      return;
    }
    if (linkedinConnectionsSource === undefined) {
      return;
    }
    if (
      linkedinConnectionsSource.sync_state === "complete" ||
      linkedinConnectionsSource.sync_state === "failed"
    ) {
      setLinkedinConnectionsProcessing(false);
      if (linkedinConnectionsSource.sync_state === "failed") {
        setConnectionsUploadError(
          linkedinConnectionsSource.sync_error ??
            "Import failed. Try uploading again.",
        );
      }
    }
  }, [linkedinConnectionsProcessing, linkedinConnectionsSource, queryClient]);

  const pollConnect = useCallback(
    async (sessionId: string, pollSecret: string): Promise<void> => {
      const response: Response = await fetch(
        `/api/auth/poll?sid=${encodeURIComponent(sessionId)}&poll_secret=${encodeURIComponent(pollSecret)}`,
      );
      if (!response.ok) {
        throw new Error("Failed to poll OAuth status");
      }
      const result: PollConnectResult =
        (await response.json()) as PollConnectResult;
      setConnectMessage(result.message);

      if (result.status === "connected") {
        clearPollTimer();
        popupRef.current?.close();
        await queryClient.invalidateQueries({ queryKey: ["sources"] });
        await queryClient.invalidateQueries({ queryKey: ["network-status"] });
        setConnectMessage("Source connected successfully.");
        return;
      }

      if (result.status === "failed") {
        clearPollTimer();
        popupRef.current?.close();
        setConnectError(result.message);
      }
    },
    [clearPollTimer, queryClient],
  );

  const connectMutation = useMutation({
    mutationFn: (sourceType: SourceType) =>
      proxyPost<ConnectSourceResult>("connect-source", {
        source_type: sourceType,
      }),
    onSuccess: async (result: ConnectSourceResult) => {
      setConnectError(null);
      if (result.already_connected) {
        setConnectMessage(result.message);
        await queryClient.invalidateQueries({ queryKey: ["sources"] });
        if (result.source_id) {
          syncMutation.mutate(result.source_id);
        }
        return;
      }

      const popup: Window | null = window.open(
        result.oauth_url,
        "contactgraph-connect",
        "width=520,height=720",
      );
      if (!popup) {
        setConnectError("Popup blocked. Allow popups and try again.");
        return;
      }
      popupRef.current = popup;
      setConnectMessage("Complete authorization in the popup…");
      const pollSecret: string | null = result.poll_secret;
      if (!pollSecret) {
        setConnectError("Server did not return a poll secret. Try connecting again.");
        return;
      }
      await pollConnect(result.connect_session_id, pollSecret);
      pollTimerRef.current = setInterval(() => {
        void pollConnect(result.connect_session_id, pollSecret).catch(() => {
          clearPollTimer();
          setConnectError("OAuth polling failed");
        });
      }, 4000);
    },
    onError: (error: Error) => {
      setConnectError(error.message);
    },
  });

  const handleTextFileUpload = useCallback(
    async (
      sourceType: SourceType,
      file: File,
    ): Promise<void> => {
      const content: string = await file.text();
      uploadMutation.mutate({
        source_type: sourceType,
        filename: file.name,
        content,
      });
    },
    [uploadMutation],
  );

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

  const handleCancelSync = useCallback(
    (sourceId: string): void => {
      void proxyPost("cancel-sync", { source_id: sourceId }).then(() => {
        void sourcesQuery.refetch();
      });
    },
    [sourcesQuery],
  );

  const handleCancelOrgEnrichment = useCallback((): void => {
    void proxyPost<CancelOrgEnrichmentResult>("cancel-org-enrichment").then(() => {
      void orgEnrichmentStatusQuery.refetch();
      void queryClient.invalidateQueries({ queryKey: ["organizations"] });
    });
  }, [orgEnrichmentStatusQuery, queryClient]);

  const handlePhoneFileUpload = useCallback(
    (file: File): void => {
      void handleTextFileUpload("phone_contacts_upload", file);
    },
    [handleTextFileUpload],
  );

  const handleLinkedInConnectionsFileUpload = useCallback(
    async (file: File): Promise<void> => {
      try {
        const resolved: File = await resolveLinkedInConnectionsUpload(file);
        await handleTextFileUpload("linkedin_connections_upload", resolved);
      } catch (error: unknown) {
        const message: string =
          error instanceof Error ? error.message : "Failed to read upload file";
        setConnectionsUploadError(message);
      }
    },
    [handleTextFileUpload],
  );

  const networkStatus: NetworkStatusResult | undefined = networkStatusQuery.data;
  const orgEnrichmentStatus: OrgEnrichmentStatusResult | undefined =
    orgEnrichmentStatusQuery.data;
  const orgLists: OrgListSummary[] = orgListsQuery.data?.lists ?? [];
  const jobMonitorConfig: JobMonitorConfigResult | undefined =
    jobMonitorConfigQuery.data;
  const jobDiscoveryStatus: JobDiscoveryStatusResult | undefined =
    jobDiscoveryStatusQuery.data;

  const selectedTargetList: OrgListSummary | undefined = orgLists.find(
    (list) => list.list_id === selectedTargetListId,
  );

  const handleCreateTargetList = useCallback((): void => {
    const name: string | null = window.prompt("New list name");
    if (name === null) {
      return;
    }
    const trimmed: string = name.trim();
    if (trimmed.length === 0) {
      return;
    }
    createOrgListMutation.mutate(trimmed);
  }, [createOrgListMutation]);

  useEffect(() => {
    if (orgEnrichmentStatus?.state !== "complete") {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: ["organizations"] });
  }, [orgEnrichmentStatus?.state, queryClient]);

  useEffect(() => {
    if (jobMonitorConfig?.list_id && selectedTargetListId === null) {
      setSelectedTargetListId(jobMonitorConfig.list_id);
    }
  }, [jobMonitorConfig?.list_id, selectedTargetListId]);

  useEffect(() => {
    const serverText: string | null = jobPreferencesQuery.data?.text ?? null;
    if (serverText !== null && preferencesText === "") {
      setPreferencesText(serverText);
    }
    const serverLocPref: string | null = jobPreferencesQuery.data?.location_pref ?? null;
    if (serverLocPref !== null && locationPref === null) {
      setLocationPref(serverLocPref);
    }
    const serverCity: string | null = jobPreferencesQuery.data?.location_city ?? null;
    if (serverCity !== null && locationCity === "") {
      setLocationCity(serverCity);
    }
  }, [jobPreferencesQuery.data?.text, jobPreferencesQuery.data?.location_pref, jobPreferencesQuery.data?.location_city, preferencesText, locationPref, locationCity]);

  useEffect(() => {
    if (jobDiscoveryStatus?.state !== "complete") {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: ["org-jobs"] });
  }, [jobDiscoveryStatus?.state, queryClient]);

  const renderStepRow = (step: SetupStep) => {
    const complete: boolean = stepComplete(
      step.id,
      sources,
      orgEnrichmentStatus,
      orgLists,
      jobMonitorConfig,
      jobPreferencesQuery.data,
    );
    const inProgress: boolean =
      step.id === "org_enrichment"
        ? orgEnrichmentStatus?.state === "running" || enrichOrgsMutation.isPending
        : step.id === "job_scrapers"
          ? jobDiscoveryStatus?.state === "running" ||
            startJobDiscoveryMutation.isPending
        : step.id === "linkedin"
          ? stepInProgress(step.id, sources) || linkedinConnectionsProcessing
          : step.id === "linkedin_profile"
            ? stepInProgress(step.id, sources) || linkedinProfileProcessing
            : stepInProgress(step.id, sources);
    const importStatus: StepImportStatusDisplay | null =
      step.id === "org_enrichment" &&
      orgEnrichmentStatus !== undefined &&
      orgEnrichmentStatus.orgs_total > 0
        ? {
            count: orgEnrichmentStatus.orgs_enriched,
            suffix: `of ${orgEnrichmentStatus.orgs_total.toLocaleString()} enriched`,
            retryLabel: "re-enrich",
          }
        : getStepImportStatus(step.id, sources, networkStatus);

    const actionProps: StepActionAreaProps | null = (() => {
      switch (step.id) {
        case "linkedin_profile":
          return {
            complete,
            inProgress,
            pending: uploadMutation.isPending,
            status: importStatus,
            primaryLabel: "Upload",
            onPrimary: () => setLinkedinProfileDialogOpen(true),
            disabled: uploadMutation.isPending || linkedinProfileProcessing,
          };
        case "gmail":
          return {
            complete,
            inProgress,
            pending: connectMutation.isPending,
            status: importStatus,
            primaryLabel: "Connect",
            onPrimary: () => connectMutation.mutate("google_mail"),
            disabled: connectMutation.isPending,
          };
        case "phone":
          return {
            complete,
            inProgress,
            pending: uploadMutation.isPending,
            status: importStatus,
            primaryLabel: "Upload",
            onPrimary: () => setPhoneDialogOpen(true),
            disabled: uploadMutation.isPending,
          };
        case "linkedin":
          return {
            complete,
            inProgress,
            pending: uploadMutation.isPending,
            status: importStatus,
            primaryLabel: "Upload",
            onPrimary: () => setLinkedinConnectionsDialogOpen(true),
            disabled: uploadMutation.isPending,
          };
        case "org_enrichment":
          return {
            complete,
            inProgress,
            pending: enrichOrgsMutation.isPending,
            status: importStatus,
            primaryLabel: "Enrich",
            inProgressLabel: "Enriching…",
            pendingLabel: "Starting…",
            onPrimary: () => enrichOrgsMutation.mutate(),
            disabled:
              enrichOrgsMutation.isPending ||
              orgEnrichmentStatus?.state === "running",
          };
        default:
          return null;
      }
    })();

    return (
      <div
        key={step.id}
        className="flex flex-col gap-3 border-b pb-4 last:border-b-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between"
      >
        <div className="flex gap-3">
          <div className="mt-0.5 shrink-0">
            {step.comingSoon ? (
              <Circle className="size-5 text-muted-foreground/50" />
            ) : complete ? (
              <CheckCircle2 className="size-5 text-green-600" />
            ) : inProgress ? (
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            ) : (
              <Circle className="size-5 text-muted-foreground" />
            )}
          </div>
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium">{step.title}</p>
              {step.comingSoon ? (
                <Badge variant="secondary" className="text-xs">
                  Coming soon
                </Badge>
              ) : step.id === "phone" ? (
                <span className="text-xs text-muted-foreground">Required</span>
              ) : step.id === "linkedin" || step.id === "org_enrichment" ? (
                <span className="text-xs text-muted-foreground">Recommended</span>
              ) : step.optional ? (
                <span className="text-xs text-muted-foreground">Optional</span>
              ) : null}
            </div>
            <p className="text-sm text-muted-foreground">{step.description}</p>
            {step.id === "phone" &&
            phoneSource &&
            (phoneSource.sync_state === "syncing" ||
              phoneSource.sync_state === "pending") ? (
              <p className="text-xs text-muted-foreground">
                {phoneSource.contacts_pending > 0
                  ? `Imported ${phoneSource.contacts_resolved.toLocaleString()} of ${phoneSource.contacts_pending.toLocaleString()}`
                  : "Importing…"}
                {" · "}
                <button
                  type="button"
                  className="text-destructive hover:underline"
                  onClick={() => handleCancelSync(phoneSource.source_id)}
                >
                  Cancel
                </button>
              </p>
            ) : null}
            {step.id === "linkedin" &&
            linkedinConnectionsSource &&
            (linkedinConnectionsSource.sync_state === "syncing" ||
              linkedinConnectionsSource.sync_state === "pending") ? (
              <p className="text-xs text-muted-foreground">
                {linkedinConnectionsSource.contacts_pending > 0
                  ? `Imported ${linkedinConnectionsSource.contacts_resolved.toLocaleString()} of ${linkedinConnectionsSource.contacts_pending.toLocaleString()}`
                  : "Importing…"}
                {" · "}
                <button
                  type="button"
                  className="text-destructive hover:underline"
                  onClick={() => handleCancelSync(linkedinConnectionsSource.source_id)}
                >
                  Cancel
                </button>
              </p>
            ) : null}
            {step.id === "linkedin" &&
            linkedinConnectionsSource?.sync_state === "failed" ? (
              <p className="text-xs text-destructive">
                {linkedinConnectionsSource.sync_error ??
                  "Import failed — try uploading again"}
              </p>
            ) : null}
            {step.id === "org_enrichment" &&
            orgEnrichmentStatus?.state === "running" ? (
              <p className="text-xs text-muted-foreground">
                {orgEnrichmentStatus.orgs_total > 0
                  ? orgEnrichmentStatus.progress_message ??
                    `Enriched ${orgEnrichmentStatus.orgs_enriched.toLocaleString()} of ${orgEnrichmentStatus.orgs_total.toLocaleString()}`
                  : "Starting enrichment…"}
                {" · "}
                <button
                  type="button"
                  className="text-destructive hover:underline"
                  onClick={handleCancelOrgEnrichment}
                >
                  Cancel
                </button>
              </p>
            ) : null}
            {step.id === "org_enrichment" &&
            orgEnrichmentStatus?.state === "failed" &&
            orgEnrichmentStatus.error ? (
              <p className="text-xs text-destructive">{orgEnrichmentStatus.error}</p>
            ) : null}
            {step.id === "job_scrapers" &&
            jobDiscoveryStatus?.state === "running" ? (
              <p className="text-xs text-muted-foreground">
                {jobDiscoveryStatus.progress_message ?? jobDiscoveryStatus.message}
                {" · "}
                <button
                  type="button"
                  className="text-destructive hover:underline"
                  onClick={() => {
                    void proxyPost("cancel-job-discovery").then(() => {
                      void jobDiscoveryStatusQuery.refetch();
                    });
                  }}
                >
                  Cancel
                </button>
              </p>
            ) : null}
            {step.id === "job_scrapers" &&
            jobDiscoveryStatus?.state === "failed" &&
            jobDiscoveryStatus.error ? (
              <p className="text-xs text-destructive">{jobDiscoveryStatus.error}</p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 sm:justify-end sm:pt-0.5">
          {step.id === "target_companies" ? (
            <>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={orgListsQuery.isLoading}
                  >
                    {selectedTargetList !== undefined
                      ? `${selectedTargetList.name} (${selectedTargetList.org_count})`
                      : "Choose list…"}
                    <ChevronDown className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {orgLists.length === 0 ? (
                    <DropdownMenuItem disabled>No lists yet</DropdownMenuItem>
                  ) : (
                    orgLists.map((list) => (
                      <DropdownMenuCheckboxItem
                        key={list.list_id}
                        checked={selectedTargetListId === list.list_id}
                        onCheckedChange={() =>
                          setSelectedTargetListId(
                            selectedTargetListId === list.list_id
                              ? null
                              : list.list_id,
                          )
                        }
                      >
                        {list.name} ({list.org_count})
                      </DropdownMenuCheckboxItem>
                    ))
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={handleCreateTargetList}
                    disabled={createOrgListMutation.isPending}
                  >
                    <ListPlus className="mr-2 size-4" />
                    Create new list…
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              {selectedTargetList !== undefined ? (
                <Button variant="outline" size="sm" asChild>
                  <Link
                    href={`/organizations?list=${encodeURIComponent(selectedTargetList.list_id)}`}
                  >
                    View in Organizations
                    <ArrowRight className="size-4" />
                  </Link>
                </Button>
              ) : null}
            </>
          ) : step.id === "job_preferences" ? (
            <>
              <div className="flex w-full flex-col gap-3">
                <textarea
                  className="min-h-[80px] w-full rounded-md border bg-background px-3 py-2 text-sm sm:w-80"
                  placeholder="e.g. I'm a senior backend engineer interested in distributed systems, platform, and SRE roles. Python or Go preferred. Not interested in frontend or sales."
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
                <div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={
                      setJobPreferencesMutation.isPending ||
                      !preferencesText.trim()
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
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      "Save"
                    )}
                  </Button>
                </div>
              </div>
              {jobPreferencesQuery.data?.classified_job_count ? (
                <p className="text-xs text-muted-foreground">
                  {jobPreferencesQuery.data.classified_job_count} job(s) classified
                </p>
              ) : null}
            </>
          ) : step.id === "job_scrapers" ? (
            <>
              <Button
                variant={jobMonitorConfig?.enabled ? "default" : "outline"}
                size="sm"
                disabled={
                  selectedTargetList === undefined ||
                  setJobMonitorConfigMutation.isPending
                }
                onClick={() =>
                  setJobMonitorConfigMutation.mutate({
                    list_id: selectedTargetListId,
                    enabled: !jobMonitorConfig?.enabled,
                  })
                }
              >
                {jobMonitorConfig?.enabled ? "Monitoring on" : "Enable monitoring"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={
                  selectedTargetList === undefined ||
                  startJobDiscoveryMutation.isPending ||
                  setJobMonitorConfigMutation.isPending ||
                  jobDiscoveryStatus?.state === "running"
                }
                onClick={async () => {
                  if (selectedTargetListId !== null) {
                    await setJobMonitorConfigMutation.mutateAsync({
                      list_id: selectedTargetListId,
                    });
                  }
                  startJobDiscoveryMutation.mutate();
                }}
              >
                {jobDiscoveryStatus?.state === "running" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <RefreshCw className="size-4" />
                )}
                Scan now
              </Button>
              <Button variant="outline" size="sm" asChild>
                <Link href="/jobs">
                  View jobs
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
            </>
          ) : step.comingSoon ? (
            <Button variant="outline" size="sm" disabled>
              Coming soon
            </Button>
          ) : actionProps ? (
            <StepActionArea {...actionProps} />
          ) : null}
        </div>
      </div>
    );
  };

  const sectionOrder: readonly SetupSectionId[] = ["network", "job_search"];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Setup</h1>
        <p className="text-muted-foreground">
          Follow the steps below to get the most out of ContactGraph. Start by
          importing your network, then configure job search tools to surface
          relevant opportunities.
        </p>
      </div>

      {connectError ? (
        <Alert variant="destructive">
          <AlertDescription>{connectError}</AlertDescription>
        </Alert>
      ) : null}
      {connectMessage ? (
        <Alert>
          <AlertDescription>{connectMessage}</AlertDescription>
        </Alert>
      ) : null}
      {orgEnrichmentError ? (
        <Alert variant="destructive">
          <AlertDescription>{orgEnrichmentError}</AlertDescription>
        </Alert>
      ) : null}
      {orgEnrichmentMessage ? (
        <Alert>
          <AlertDescription>{orgEnrichmentMessage}</AlertDescription>
        </Alert>
      ) : null}

      {sectionOrder.map((sectionId) => {
        const meta = sectionMeta[sectionId];
        const steps = setupSteps.filter((step) => step.section === sectionId);
        return (
          <Card key={sectionId}>
            <CardHeader>
              <CardTitle className="text-base">{meta.title}</CardTitle>
              <CardDescription>{meta.description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {steps.map((step) => renderStepRow(step))}
            </CardContent>
          </Card>
        );
      })}

      {futureSections.map((section) => (
        <FutureSectionCard key={section.id} {...section} />
      ))}

      <details className="group rounded-lg border">
        <summary
          className={cn(
            "flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-4",
            "[&::-webkit-details-marker]:hidden",
          )}
        >
          <div>
            <p className="font-medium">Raw imports</p>
            <p className="text-sm text-muted-foreground">
              {sourcesQuery.data?.message ?? "View and sync connected data sources"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={(event) => {
                event.preventDefault();
                void sourcesQuery.refetch();
                void networkStatusQuery.refetch();
              }}
              disabled={
                sourcesQuery.isFetching ||
                networkStatusQuery.isFetching
              }
            >
              <RefreshCw
                className={`size-4 ${sourcesQuery.isFetching ? "animate-spin" : ""}`}
              />
              Refresh
            </Button>
            <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
          </div>
        </summary>
        <div className="border-t px-6 pb-6 pt-4">
          {sourcesQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No sources connected yet. Start by importing phone contacts above.
            </p>
          ) : (
            <ul className="divide-y">
              {sources.map((source) => (
                <li
                  key={source.source_id}
                  className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{source.label}</p>
                      <Badge variant="outline">
                        {formatSourceType(source.source_type)}
                      </Badge>
                      <SyncStateBadge state={source.sync_state} />
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {source.contacts_resolved.toLocaleString()} resolved ·{" "}
                      {source.contacts_pending.toLocaleString()} pending ·{" "}
                      {source.contacts_found.toLocaleString()} found
                    </p>
                    {source.sync_state === "failed" && source.sync_error ? (
                      <p className="text-sm text-destructive">{source.sync_error}</p>
                    ) : null}
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => syncMutation.mutate(source.source_id)}
                    disabled={
                      syncMutation.isPending ||
                      source.sync_state === "syncing" ||
                      source.source_type === "phone_contacts_upload" ||
                      source.source_type === "linkedin_connections_upload" ||
                      source.source_type === "linkedin_profile_upload"
                    }
                  >
                    {source.sync_state === "syncing" ? "Syncing…" : "Sync now"}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>

      <PhoneContactsUploadDialog
        open={phoneDialogOpen}
        onOpenChange={setPhoneDialogOpen}
        onFileSelect={handlePhoneFileUpload}
        isPending={uploadMutation.isPending}
        error={phoneUploadError}
        syncState={phoneSource?.sync_state}
        contactsResolved={phoneSource?.contacts_resolved}
      />

      <LinkedInConnectionsUploadDialog
        open={linkedinConnectionsDialogOpen}
        onOpenChange={setLinkedinConnectionsDialogOpen}
        onFileSelect={handleLinkedInConnectionsFileUpload}
        isPending={uploadMutation.isPending}
        isProcessing={linkedinConnectionsProcessing}
        error={connectionsUploadError}
        syncState={linkedinConnectionsSource?.sync_state}
        syncError={linkedinConnectionsSource?.sync_error}
        contactsResolved={linkedinConnectionsSource?.contacts_resolved}
      />

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
