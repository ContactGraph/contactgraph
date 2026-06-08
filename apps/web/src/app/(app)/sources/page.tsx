"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, Loader2, Plus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

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
import { Skeleton } from "@/components/ui/skeleton";
import { resolveLinkedInConnectionsUpload } from "@/lib/linkedin-connections-upload";
import type {
  ConnectSourceResult,
  ListSourcesResult,
  NetworkStatusResult,
  PollConnectResult,
  SourceSummary,
  SourceType,
  SyncSourceResult,
  SyncState,
  UploadSourceResult,
} from "@/lib/api-types";
import { formatSourceType, SyncStateBadge } from "@/lib/formatters";
import { proxyPost } from "@/lib/proxy-client";

const IMPORT_COMPLETE_STATES: ReadonlySet<SyncState> = new Set([
  "partial",
  "complete",
]);

type SetupStepId =
  | "phone"
  | "gmail"
  | "linkedin"
  | "linkedin_profile";

interface SetupStep {
  id: SetupStepId;
  title: string;
  description: string;
  optional?: boolean;
  phase: "network" | "enrich";
}

const setupSteps: ReadonlyArray<SetupStep> = [
  {
    id: "phone",
    phase: "network",
    title: "Import your network",
    description:
      "Upload phone contacts (.vcf) from iPhone or Android — this is your authoritative network.",
  },
  {
    id: "linkedin",
    phase: "enrich",
    title: "Upload LinkedIn connections",
    description:
      "Match LinkedIn profiles to phone contacts and identify strong professional ties.",
  },
  {
    id: "linkedin_profile",
    phase: "enrich",
    title: "Upload your LinkedIn profile",
    description:
      "Optional PDF export of your own profile for better self-identification during enrichment.",
    optional: true,
  },
];

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
  onPrimary: () => void;
  disabled: boolean;
}

function StepActionArea({
  complete,
  inProgress,
  pending,
  status,
  primaryLabel,
  onPrimary,
  disabled,
}: StepActionAreaProps) {
  if (inProgress || pending) {
    return (
      <Button variant="outline" size="sm" disabled>
        <Loader2 className="size-4 animate-spin" />
        {inProgress ? "Importing…" : "Working…"}
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

export default function SourcesPage() {
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

  const renderStepRow = (step: SetupStep) => {
    const complete: boolean = stepComplete(step.id, sources);
    const inProgress: boolean =
      step.id === "linkedin"
        ? stepInProgress(step.id, sources) || linkedinConnectionsProcessing
        : step.id === "linkedin_profile"
          ? stepInProgress(step.id, sources) || linkedinProfileProcessing
          : stepInProgress(step.id, sources);
    const importStatus: StepImportStatusDisplay | null = getStepImportStatus(
      step.id,
      sources,
      networkStatus,
    );

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
            {complete ? (
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
              {step.id === "phone" ? (
                <Badge variant="default">Required</Badge>
              ) : step.id === "linkedin" ? (
                <Badge variant="default">Recommended</Badge>
              ) : step.optional ? (
                <Badge variant="outline">Optional</Badge>
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
              </p>
            ) : null}
            {step.id === "linkedin" &&
            linkedinConnectionsSource?.sync_state === "failed" ? (
              <p className="text-xs text-destructive">
                {linkedinConnectionsSource.sync_error ??
                  "Import failed — try uploading again"}
              </p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 sm:justify-end sm:pt-0.5">
          {actionProps ? <StepActionArea {...actionProps} /> : null}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Your network</h1>
        <p className="text-muted-foreground">
          {networkStatus?.message ??
            "Phone contacts are your network. LinkedIn enriches them with professional context."}
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

      <Card>
        <CardHeader>
          <CardTitle>Phase 1 · Import your network</CardTitle>
          <CardDescription>
            Start with phone contacts. This defines who is in your network.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {setupSteps
            .filter((step) => step.phase === "network")
            .map((step) => renderStepRow(step))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Phase 2 · Enrich your network</CardTitle>
          <CardDescription>
            Add LinkedIn data to your phone contacts to identify strong
            professional ties with current employers and titles.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {setupSteps
            .filter((step) => step.phase === "enrich")
            .map((step) => renderStepRow(step))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div>
            <CardTitle>Raw imports</CardTitle>
            <CardDescription>
              {sourcesQuery.data?.message ?? "Loading sources…"}
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
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
        </CardHeader>
        <CardContent>
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
        </CardContent>
      </Card>

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
