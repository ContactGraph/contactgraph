"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, Loader2, Plus, RefreshCw, Sparkles, User } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  ConnectSourceResult,
  EnrichmentStatusResult,
  ListSourcesResult,
  PollConnectResult,
  SourceSummary,
  SourceType,
  StartEnrichmentResult,
  SyncSourceResult,
  SyncState,
  UploadSourceResult,
  UserProfileResult,
} from "@/lib/api-types";
import { formatSourceType, SyncStateBadge } from "@/lib/formatters";
import { proxyPost } from "@/lib/proxy-client";

const IMPORT_COMPLETE_STATES: ReadonlySet<SyncState> = new Set([
  "partial",
  "complete",
]);

type SetupStepId =
  | "gmail"
  | "calendar"
  | "phone"
  | "linkedin_profile"
  | "linkedin"
  | "enrich";

interface SetupStep {
  id: SetupStepId;
  title: string;
  description: string;
  optional?: boolean;
}

const setupSteps: ReadonlyArray<SetupStep> = [
  {
    id: "gmail",
    title: "Connect Gmail",
    description: "Import contacts and email relationships from your inbox.",
  },
  {
    id: "calendar",
    title: "Connect Google Calendar",
    description: "Add people you've met via calendar events.",
    optional: true,
  },
  {
    id: "phone",
    title: "Upload phone contacts",
    description:
      "Export from the Contacts app (Lists → long-press → Export), then upload the .vcf file.",
    optional: true,
  },
  {
    id: "linkedin_profile",
    title: "Set up your profile",
    description:
      "Upload your LinkedIn PDF (Profile \u2192 Save to PDF) to help identify your contacts.",
    optional: true,
  },
  {
    id: "linkedin",
    title: "Upload LinkedIn connections",
    description:
      "Import Connections.csv (Settings \u2192 Get a copy of your data, takes 24h) for identity matching.",
    optional: true,
  },
  {
    id: "enrich",
    title: "Enrich contacts",
    description:
      "Find where your contacts work now. Add your name and location below first for best results.",
  },
];

function sourceForType(
  sources: ReadonlyArray<SourceSummary>,
  type: SourceType,
): SourceSummary | undefined {
  return sources.find((source) => source.source_type === type);
}

function stepComplete(
  stepId: SetupStepId,
  sources: ReadonlyArray<SourceSummary>,
  enrichment: EnrichmentStatusResult | undefined,
): boolean {
  switch (stepId) {
    case "gmail": {
      const source = sourceForType(sources, "google_mail");
      return source !== undefined && IMPORT_COMPLETE_STATES.has(source.sync_state);
    }
    case "calendar": {
      const source = sourceForType(sources, "google_calendar");
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
    case "enrich":
      return enrichment?.state === "complete";
    default:
      return false;
  }
}

function stepInProgress(
  stepId: SetupStepId,
  sources: ReadonlyArray<SourceSummary>,
  enrichment: EnrichmentStatusResult | undefined,
): boolean {
  if (stepId === "enrich") {
    return enrichment?.state === "running";
  }
  const typeMap: Partial<Record<SetupStepId, SourceType>> = {
    gmail: "google_mail",
    calendar: "google_calendar",
    phone: "phone_contacts_upload",
    linkedin_profile: "linkedin_profile_upload",
    linkedin: "linkedin_connections_upload",
  };
  const sourceType: SourceType | undefined = typeMap[stepId];
  if (sourceType === undefined) {
    return false;
  }
  const source = sourceForType(sources, sourceType);
  return source?.sync_state === "syncing";
}

function anyImportReady(sources: ReadonlyArray<SourceSummary>): boolean {
  return sources.some(
    (source) =>
      source.source_type !== "google_contacts" &&
      IMPORT_COMPLETE_STATES.has(source.sync_state),
  );
}

export default function SourcesPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const popupRef = useRef<Window | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const phoneInputRef = useRef<HTMLInputElement>(null);
  const linkedinInputRef = useRef<HTMLInputElement>(null);
  const [connectMessage, setConnectMessage] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [profileName, setProfileName] = useState<string>("");
  const [profileEmail, setProfileEmail] = useState<string>("");
  const [profileLocation, setProfileLocation] = useState<string>("");
  const [profileSaved, setProfileSaved] = useState<boolean>(false);

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
      return syncing ? 4000 : false;
    },
  });

  const enrichmentQuery = useQuery({
    queryKey: ["enrichment-status"],
    queryFn: () =>
      proxyPost<EnrichmentStatusResult>("get-enrichment-status"),
    refetchInterval: (query) => {
      const state: EnrichmentStatusResult["state"] | undefined =
        query.state.data?.state;
      return state === "running" || state === "pending" ? 3000 : false;
    },
  });

  const profileQuery = useQuery({
    queryKey: ["user-profile"],
    queryFn: () => proxyPost<UserProfileResult>("get-user-profile"),
  });

  useEffect(() => {
    const profile: UserProfileResult | undefined = profileQuery.data;
    if (profile === undefined) {
      return;
    }
    setProfileName(profile.display_name ?? "");
    setProfileEmail(profile.email ?? "");
    setProfileLocation(profile.location ?? "");
  }, [profileQuery.data]);

  const profileMutation = useMutation({
    mutationFn: (payload: { display_name: string; location: string }) =>
      proxyPost<UserProfileResult>("update-user-profile", payload),
    onSuccess: async () => {
      setProfileSaved(true);
      await queryClient.invalidateQueries({ queryKey: ["user-profile"] });
      window.setTimeout(() => setProfileSaved(false), 2500);
    },
  });

  const syncMutation = useMutation({
    mutationFn: (sourceId?: string) =>
      proxyPost<SyncSourceResult>("sync-source", { source_id: sourceId ?? null }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });

  const enrichMutation = useMutation({
    mutationFn: () => proxyPost<StartEnrichmentResult>("start-enrichment"),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["enrichment-status"] });
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (payload: {
      source_type: SourceType;
      filename: string;
      content: string;
    }) => proxyPost<UploadSourceResult>("upload-source", payload),
    onSuccess: async () => {
      setUploadError(null);
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
    onError: (error: Error) => {
      setUploadError(error.message);
    },
  });

  const pollConnect = useCallback(
    async (sessionId: string): Promise<void> => {
      const response: Response = await fetch(
        `/api/auth/poll?sid=${encodeURIComponent(sessionId)}`,
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
      await pollConnect(result.connect_session_id);
      pollTimerRef.current = setInterval(() => {
        void pollConnect(result.connect_session_id).catch(() => {
          clearPollTimer();
          setConnectError("OAuth polling failed");
        });
      }, 4000);
    },
    onError: (error: Error) => {
      setConnectError(error.message);
    },
  });

  const connectPhoneMutation = useMutation({
    mutationFn: () =>
      proxyPost<ConnectSourceResult>("connect-source", {
        source_type: "phone_contacts_upload",
      }),
    onSuccess: async (result: ConnectSourceResult) => {
      setConnectError(null);
      if (result.source_id) {
        router.push(`/sources/upload/${result.source_id}`);
        return;
      }
      if (result.upload_url) {
        window.location.href = result.upload_url;
        return;
      }
      setConnectError("Could not start phone contacts upload.");
    },
    onError: (error: Error) => {
      setConnectError(error.message);
    },
  });

  const handleFileUpload = useCallback(
    async (
      sourceType: SourceType,
      file: File | undefined,
    ): Promise<void> => {
      if (file === undefined) {
        return;
      }
      const content: string = await file.text();
      uploadMutation.mutate({
        source_type: sourceType,
        filename: file.name,
        content,
      });
    },
    [uploadMutation],
  );

  const sources: SourceSummary[] = sourcesQuery.data?.sources ?? [];
  const enrichment: EnrichmentStatusResult | undefined = enrichmentQuery.data;
  const importReady: boolean = anyImportReady(sources);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Setup</h1>
        <p className="text-muted-foreground">
          Import your contacts from multiple sources, then enrich to discover
          where people work now and what they are posting about.
        </p>
      </div>

      {connectError ? (
        <Alert variant="destructive">
          <AlertDescription>{connectError}</AlertDescription>
        </Alert>
      ) : null}
      {uploadError ? (
        <Alert variant="destructive">
          <AlertDescription>{uploadError}</AlertDescription>
        </Alert>
      ) : null}
      {connectMessage ? (
        <Alert>
          <AlertDescription>{connectMessage}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Your info</CardTitle>
          <CardDescription>
            Name and email come from Google sign-in. Location helps enrichment
            identify the right person for common names.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {profileQuery.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="profile-email">Your email</Label>
                  <Input
                    id="profile-email"
                    value={profileEmail}
                    readOnly
                    disabled
                    className="bg-muted"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="profile-name">Your name</Label>
                  <Input
                    id="profile-name"
                    placeholder="From Google account"
                    value={profileName}
                    onChange={(event) => setProfileName(event.target.value)}
                  />
                </div>
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="profile-location">Your location</Label>
                  <Input
                    id="profile-location"
                    placeholder="San Francisco, CA"
                    value={profileLocation}
                    onChange={(event) => setProfileLocation(event.target.value)}
                  />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={profileMutation.isPending}
                  onClick={() =>
                    profileMutation.mutate({
                      display_name: profileName.trim(),
                      location: profileLocation.trim(),
                    })
                  }
                >
                  {profileMutation.isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : null}
                  Save
                </Button>
                {profileSaved ? (
                  <span className="text-sm text-muted-foreground">Saved</span>
                ) : null}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Getting started</CardTitle>
          <CardDescription>
            Complete imports in any order. Enrichment runs once across your
            merged graph.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {setupSteps.map((step) => {
            const complete: boolean = stepComplete(step.id, sources, enrichment);
            const inProgress: boolean = stepInProgress(
              step.id,
              sources,
              enrichment,
            );
            const enrichEnabled: boolean =
              step.id !== "enrich" || importReady;

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
                      {step.optional ? (
                        <Badge variant="outline">Optional</Badge>
                      ) : null}
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {step.description}
                    </p>
                    {step.id === "enrich" && enrichment ? (
                      <p className="text-xs text-muted-foreground">
                        {enrichment.state === "running" && enrichment.contacts_total > 0
                          ? `Processed ${enrichment.contacts_enriched} of ${enrichment.contacts_total} contacts…`
                          : enrichment.message}
                        {enrichment.state === "complete" && enrichment.completed_at
                          ? ` · ${new Date(enrichment.completed_at).toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
                          : null}
                      </p>
                    ) : null}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 sm:justify-end">
                  {step.id === "gmail" ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => connectMutation.mutate("google_mail")}
                      disabled={connectMutation.isPending || inProgress}
                    >
                      <Plus className="size-4" />
                      Connect
                    </Button>
                  ) : null}
                  {step.id === "calendar" ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => connectMutation.mutate("google_calendar")}
                      disabled={connectMutation.isPending || inProgress}
                    >
                      <Plus className="size-4" />
                      Connect
                    </Button>
                  ) : null}
                  {step.id === "phone" ? (
                    <>
                      <input
                        ref={phoneInputRef}
                        type="file"
                        accept=".vcf,.vcard,.csv,text/vcard,text/csv"
                        className="hidden"
                        onChange={(event) => {
                          void handleFileUpload(
                            "phone_contacts_upload",
                            event.target.files?.[0],
                          );
                          event.target.value = "";
                        }}
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => connectPhoneMutation.mutate()}
                        disabled={
                          connectPhoneMutation.isPending ||
                          uploadMutation.isPending ||
                          inProgress
                        }
                      >
                        Upload contacts
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => phoneInputRef.current?.click()}
                        disabled={uploadMutation.isPending || inProgress}
                      >
                        Quick upload
                      </Button>
                    </>
                  ) : null}
                  {step.id === "linkedin_profile" ? (
                    <Button
                      variant="outline"
                      size="sm"
                      asChild
                    >
                      <Link href="/profile">
                        <User className="size-4" />
                        Set up profile
                      </Link>
                    </Button>
                  ) : null}
                  {step.id === "linkedin" ? (
                    <>
                      <input
                        ref={linkedinInputRef}
                        type="file"
                        accept=".csv,text/csv"
                        className="hidden"
                        onChange={(event) => {
                          void handleFileUpload(
                            "linkedin_connections_upload",
                            event.target.files?.[0],
                          );
                          event.target.value = "";
                        }}
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => linkedinInputRef.current?.click()}
                        disabled={uploadMutation.isPending || inProgress}
                      >
                        Upload CSV
                      </Button>
                    </>
                  ) : null}
                  {step.id === "enrich" ? (
                    <Button
                      size="sm"
                      onClick={() => enrichMutation.mutate()}
                      disabled={
                        !enrichEnabled ||
                        enrichMutation.isPending ||
                        inProgress
                      }
                    >
                      {enrichMutation.isPending || inProgress ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Sparkles className="size-4" />
                      )}
                      {inProgress
                        ? "Enriching…"
                        : complete
                          ? "Re-enrich"
                          : "Enrich now"}
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div>
            <CardTitle>Connected sources</CardTitle>
            <CardDescription>
              {sourcesQuery.data?.message ?? "Loading sources…"}
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void sourcesQuery.refetch();
              void enrichmentQuery.refetch();
            }}
            disabled={sourcesQuery.isFetching || enrichmentQuery.isFetching}
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
              No sources connected yet. Start with Gmail above.
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
                      {source.contacts_resolved} resolved ·{" "}
                      {source.contacts_pending} pending ·{" "}
                      {source.contacts_found} found
                    </p>
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
    </div>
  );
}
