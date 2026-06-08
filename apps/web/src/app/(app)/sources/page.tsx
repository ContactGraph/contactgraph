"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, Loader2, Plus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { LinkedInConnectionsUploadDialog } from "@/components/setup/linkedin-connections-upload-dialog";
import { LinkedInEnrichmentStep } from "@/components/setup/linkedin-enrichment-step";
import { LinkedInProfileUploadDialog } from "@/components/setup/linkedin-profile-upload-dialog";
import { PhoneContactsUploadDialog } from "@/components/setup/phone-contacts-upload-dialog";
import { StrongTiesStep } from "@/components/setup/strong-ties-step";
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
  EnrichStrongTiesResult,
  ListSourcesResult,
  ListStrongTiesResult,
  NetworkStatusResult,
  PollConnectResult,
  ScrapingDogEnrichmentStatusResult,
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
      "Upload phone contacts (.vcf) — this is your authoritative network. Everything else enriches these people.",
  },
  {
    id: "gmail",
    phase: "enrich",
    title: "Connect Gmail",
    description: "Add email addresses and communication history to your phone contacts.",
    optional: true,
  },
  {
    id: "linkedin",
    phase: "enrich",
    title: "Upload LinkedIn connections",
    description:
      "Match LinkedIn profiles to phone contacts and identify strong professional ties.",
    optional: true,
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
  let latest: SourceSummary | undefined;
  for (const source of sources) {
    if (source.source_type === type) {
      latest = source;
    }
  }
  return latest;
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

  const strongTiesQuery = useQuery({
    queryKey: ["strong-ties"],
    queryFn: () => proxyPost<ListStrongTiesResult>("list-strong-ties"),
    enabled: (networkStatusQuery.data?.strong_tie_count ?? 0) > 0,
  });

  const scrapingDogStatusQuery = useQuery({
    queryKey: ["scrapingdog-enrichment-status"],
    queryFn: () =>
      proxyPost<ScrapingDogEnrichmentStatusResult>(
        "get-scrapingdog-enrichment-status",
      ),
    refetchInterval: (query) =>
      query.state.data?.state === "running" ? 3000 : false,
  });

  const syncMutation = useMutation({
    mutationFn: (sourceId?: string) =>
      proxyPost<SyncSourceResult>("sync-source", { source_id: sourceId ?? null }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });

  const enrichStrongTiesMutation = useMutation({
    mutationFn: () => proxyPost<EnrichStrongTiesResult>("enrich-strong-ties"),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["scrapingdog-enrichment-status"],
      });
      await queryClient.invalidateQueries({ queryKey: ["network-status"] });
      await queryClient.invalidateQueries({ queryKey: ["people"] });
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
      } else if (variables.source_type === "linkedin_profile_upload") {
        setLinkedinProfileUploadError(null);
        setLinkedinProfileProcessing(true);
      } else if (variables.source_type === "linkedin_connections_upload") {
        setConnectionsUploadError(null);
        setLinkedinConnectionsProcessing(true);
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
        : stepInProgress(step.id, sources);

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
              ) : step.optional ? (
                <Badge variant="outline">Recommended</Badge>
              ) : null}
            </div>
            <p className="text-sm text-muted-foreground">{step.description}</p>
            {step.id === "phone" && phoneSource?.sync_state === "complete" ? (
              <p className="text-xs text-muted-foreground">
                Imported {phoneSource.contacts_resolved.toLocaleString()} people into your network
              </p>
            ) : null}
            {step.id === "gmail" && networkStatus?.gmail_connected ? (
              <p className="text-xs text-muted-foreground">
                Matched {networkStatus.gmail_matched_count.toLocaleString()} of your contacts
              </p>
            ) : null}
            {step.id === "linkedin" && linkedinConnectionsSource ? (
              <p className="text-xs text-muted-foreground">
                {linkedinConnectionsSource.sync_state === "syncing" ||
                linkedinConnectionsSource.sync_state === "pending"
                  ? linkedinConnectionsSource.contacts_resolved > 0
                    ? `Importing ${linkedinConnectionsSource.contacts_resolved.toLocaleString()} connections…`
                    : "Importing… large exports can take several minutes"
                  : linkedinConnectionsSource.sync_state === "complete"
                    ? `Found LinkedIn profiles for ${networkStatus?.linkedin_matched_count.toLocaleString() ?? linkedinConnectionsSource.contacts_resolved.toLocaleString()} of your contacts`
                    : linkedinConnectionsSource.sync_state === "failed"
                      ? (linkedinConnectionsSource.sync_error ??
                        "Import failed — try uploading again")
                      : null}
              </p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 sm:justify-end">
          {step.id === "linkedin_profile" ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setLinkedinProfileDialogOpen(true)}
              disabled={
                uploadMutation.isPending ||
                linkedinProfileProcessing ||
                inProgress
              }
            >
              {inProgress ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Plus className="size-4" />
              )}
              {complete ? "Re-upload" : "Upload"}
            </Button>
          ) : null}
          {step.id === "gmail" ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => connectMutation.mutate("google_mail")}
              disabled={connectMutation.isPending || inProgress}
            >
              <Plus className="size-4" />
              {complete ? "Reconnect" : "Connect"}
            </Button>
          ) : null}
          {step.id === "phone" ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPhoneDialogOpen(true)}
              disabled={uploadMutation.isPending || inProgress}
            >
              {inProgress ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Plus className="size-4" />
              )}
              {complete ? "Re-upload" : "Upload"}
            </Button>
          ) : null}
          {step.id === "linkedin" ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setLinkedinConnectionsDialogOpen(true)}
              disabled={uploadMutation.isPending || inProgress}
            >
              {inProgress ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Plus className="size-4" />
              )}
              {complete ? "Re-upload" : "Upload"}
            </Button>
          ) : null}
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
            "Phone contacts are your network. LinkedIn and Gmail enrich them with professional context."}
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
            Add Gmail and LinkedIn data to your phone contacts. Raw imports stay
            behind the scenes — only your phone network is shown in People.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {setupSteps
            .filter((step) => step.phase === "enrich")
            .map((step) => renderStepRow(step))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Phase 3 · Strong ties</CardTitle>
          <CardDescription>
            People in your phone who are also LinkedIn connections.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <StrongTiesStep
            networkStatus={networkStatus}
            strongTies={strongTiesQuery.data}
            isLoading={networkStatusQuery.isLoading || strongTiesQuery.isLoading}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Phase 4 · Discover where they work</CardTitle>
          <CardDescription>
            Scrape LinkedIn profiles for strong ties to find current employers.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LinkedInEnrichmentStep
            networkStatus={networkStatus}
            enrichmentStatus={scrapingDogStatusQuery.data}
            isLoading={
              networkStatusQuery.isLoading || scrapingDogStatusQuery.isLoading
            }
            isPending={enrichStrongTiesMutation.isPending}
            onEnrich={() => enrichStrongTiesMutation.mutate()}
          />
        </CardContent>
      </Card>

      <Card className="opacity-70">
        <CardHeader>
          <CardTitle>Phase 5 · Take action</CardTitle>
          <CardDescription>Coming soon</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            Find job openings at target companies
          </div>
          <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            Generate a recommended outreach plan
          </div>
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
              void scrapingDogStatusQuery.refetch();
            }}
            disabled={
              sourcesQuery.isFetching ||
              networkStatusQuery.isFetching ||
              scrapingDogStatusQuery.isFetching
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
