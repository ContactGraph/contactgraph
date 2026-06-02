"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Plus } from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";
import type {
  ConnectSourceResult,
  ListSourcesResult,
  PollConnectResult,
  SourceType,
  SyncSourceResult,
} from "@/lib/api-types";
import { formatSourceType, SyncStateBadge } from "@/lib/formatters";
import { proxyPost } from "@/lib/proxy-client";

const connectableSources: ReadonlyArray<{
  type: SourceType;
  label: string;
}> = [
  { type: "google_mail", label: "Gmail" },
  { type: "google_contacts", label: "Google Contacts" },
];

export default function SourcesPage() {
  const queryClient = useQueryClient();
  const popupRef = useRef<Window | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [connectMessage, setConnectMessage] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);

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
        data?.sources.some((source) => source.sync_state === "syncing") ??
        false;
      return syncing ? 4000 : false;
    },
  });

  const syncMutation = useMutation({
    mutationFn: (sourceId?: string) =>
      proxyPost<SyncSourceResult>("sync-source", { source_id: sourceId ?? null }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
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

  const sources: ListSourcesResult["sources"] = sourcesQuery.data?.sources ?? [];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Sources</h1>
        <p className="text-muted-foreground">
          Connect and sync data sources that feed your contact graph.
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
          <CardTitle>Connect a source</CardTitle>
          <CardDescription>
            Add Gmail or Google Contacts to expand your graph.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {connectableSources.map((source) => (
            <Button
              key={source.type}
              variant="outline"
              onClick={() => connectMutation.mutate(source.type)}
              disabled={connectMutation.isPending}
            >
              <Plus className="size-4" />
              {source.label}
            </Button>
          ))}
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
            onClick={() => void sourcesQuery.refetch()}
            disabled={sourcesQuery.isFetching}
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
              No sources connected yet. Connect Gmail or Google Contacts above.
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
                    <p className="text-xs text-muted-foreground capitalize">
                      Connection: {source.connection_status.replace(/_/g, " ")}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    onClick={() =>
                      syncMutation.mutate(source.source_id)
                    }
                    disabled={
                      syncMutation.isPending ||
                      source.sync_state === "syncing"
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
