"use client";

import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

type GraphEventPayload =
  | {
      type: "source_sync_progress";
      source_id: string;
      source_type: string;
      sync_state: string;
      contacts_found: number;
      contacts_resolved: number;
      contacts_pending: number;
      sync_error: string | null;
    }
  | {
      type: "source_sync_complete";
      source_id: string;
      source_type: string;
      contacts_found: number;
      contacts_resolved: number;
    }
  | {
      type: "source_sync_failed";
      source_id: string;
      source_type: string;
      sync_error: string | null;
    }
  | {
      type: "org_enrichment_progress";
      orgs_enriched: number;
      orgs_total: number;
      progress_message: string | null;
      state: "running";
    }
  | {
      type: "org_enrichment_complete";
      orgs_enriched: number;
      orgs_total: number;
    }
  | {
      type: "org_enrichment_failed";
      orgs_enriched: number;
      orgs_total: number;
      error: string | null;
    };

function isGraphEventPayload(value: unknown): value is GraphEventPayload {
  if (typeof value !== "object" || value === null || !("type" in value)) {
    return false;
  }
  return typeof value.type === "string";
}

let sharedEventSource: EventSource | null = null;
let subscriberCount: number = 0;
const queryClientRef: { current: QueryClient | null } = { current: null };

function handleGraphEvent(
  queryClient: QueryClient,
  payload: GraphEventPayload,
): void {
  switch (payload.type) {
    case "source_sync_progress":
    case "source_sync_complete":
    case "source_sync_failed":
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
      void queryClient.invalidateQueries({ queryKey: ["network-status"] });
      if (payload.source_type === "linkedin_connections_upload") {
        if (payload.type === "source_sync_complete") {
          void queryClient.invalidateQueries({ queryKey: ["organizations"] });
          void queryClient.invalidateQueries({ queryKey: ["org-enrichment-status"] });
        }
      }
      if (payload.source_type === "linkedin_profile_upload") {
        if (
          payload.type === "source_sync_complete" ||
          payload.type === "source_sync_failed"
        ) {
          void queryClient.invalidateQueries({ queryKey: ["user-profile"] });
        }
      }
      break;
    case "org_enrichment_progress":
    case "org_enrichment_complete":
    case "org_enrichment_failed":
      void queryClient.invalidateQueries({ queryKey: ["org-enrichment-status"] });
      if (payload.type === "org_enrichment_complete") {
        void queryClient.invalidateQueries({ queryKey: ["organizations"] });
      }
      break;
    default:
      break;
  }
}

export function useGraphEvents(): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    queryClientRef.current = queryClient;
    subscriberCount += 1;

    if (sharedEventSource === null) {
      const eventSource: EventSource = new EventSource("/api/events/graph");

      eventSource.onmessage = (messageEvent: MessageEvent<string>) => {
        const client: QueryClient | null = queryClientRef.current;
        if (client === null) {
          return;
        }

        let payload: unknown;
        try {
          payload = JSON.parse(messageEvent.data) as unknown;
        } catch {
          return;
        }

        if (!isGraphEventPayload(payload)) {
          return;
        }

        handleGraphEvent(client, payload);
      };

      sharedEventSource = eventSource;
    }

    return () => {
      subscriberCount -= 1;
      if (subscriberCount === 0 && sharedEventSource !== null) {
        sharedEventSource.close();
        sharedEventSource = null;
        queryClientRef.current = null;
      }
    };
  }, [queryClient]);
}
