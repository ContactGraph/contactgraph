"use client";

import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useState, type Dispatch, type SetStateAction } from "react";

export interface DiscoveryProgressState {
  orgsProcessed: number;
  orgsTotal: number;
  jobsFound: number;
  newJobs: number;
  progressMessage: string | null;
}

export interface ScoringProgressState {
  scored: number;
  total: number;
}

export interface JobEventsState {
  discoveryRunning: boolean;
  discoveryProgress: DiscoveryProgressState | null;
  scoringActive: boolean;
  scoringProgress: ScoringProgressState | null;
}

const INITIAL_JOB_EVENTS_STATE: JobEventsState = {
  discoveryRunning: false,
  discoveryProgress: null,
  scoringActive: false,
  scoringProgress: null,
};

type JobEventPayload =
  | {
      type: "discovery_progress";
      orgs_processed: number;
      orgs_total: number;
      jobs_found: number;
      new_jobs: number;
      progress_message: string | null;
    }
  | {
      type: "discovery_complete";
      jobs_found: number;
      new_jobs: number;
    }
  | { type: "discovery_cancelled" }
  | {
      type: "scan_progress";
      scanning_active: boolean;
    }
  | {
      type: "scoring_progress";
      scored: number;
      total: number;
    }
  | {
      type: "scoring_complete";
      scored: number;
      total: number;
    }
  | {
      type: "scoring_cancelled";
      scored: number;
      total: number;
    };

function isJobEventPayload(value: unknown): value is JobEventPayload {
  if (typeof value !== "object" || value === null || !("type" in value)) {
    return false;
  }
  return typeof value.type === "string";
}

let sharedEventSource: EventSource | null = null;
let subscriberCount: number = 0;
const queryClientRef: { current: QueryClient | null } = { current: null };
const stateListeners: Set<Dispatch<SetStateAction<JobEventsState>>> = new Set();

function invalidateJobQueries(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: ["job-scan-status"] });
  void queryClient.invalidateQueries({ queryKey: ["flat-jobs"] });
}

function broadcastState(
  updater: (current: JobEventsState) => JobEventsState,
): void {
  for (const setState of stateListeners) {
    setState(updater);
  }
}

function handleJobEvent(queryClient: QueryClient, payload: JobEventPayload): void {
  switch (payload.type) {
    case "discovery_progress":
      broadcastState((current) => ({
        ...current,
        discoveryRunning: true,
        discoveryProgress: {
          orgsProcessed: payload.orgs_processed,
          orgsTotal: payload.orgs_total,
          jobsFound: payload.jobs_found,
          newJobs: payload.new_jobs,
          progressMessage: payload.progress_message,
        },
      }));
      invalidateJobQueries(queryClient);
      break;
    case "discovery_complete":
      broadcastState((current) => ({
        ...current,
        discoveryRunning: false,
        discoveryProgress: null,
      }));
      invalidateJobQueries(queryClient);
      break;
    case "discovery_cancelled":
      broadcastState((current) => ({
        ...current,
        discoveryRunning: false,
        discoveryProgress: null,
      }));
      invalidateJobQueries(queryClient);
      break;
    case "scan_progress":
      invalidateJobQueries(queryClient);
      break;
    case "scoring_progress":
      broadcastState((current) => ({
        ...current,
        scoringActive: true,
        scoringProgress: {
          scored: payload.scored,
          total: payload.total,
        },
      }));
      invalidateJobQueries(queryClient);
      break;
    case "scoring_complete":
    case "scoring_cancelled":
      broadcastState((current) => ({
        ...current,
        scoringActive: false,
        scoringProgress: null,
      }));
      invalidateJobQueries(queryClient);
      break;
    default:
      break;
  }
}

export function useJobEvents(): JobEventsState {
  const queryClient = useQueryClient();
  const [state, setState] = useState<JobEventsState>(INITIAL_JOB_EVENTS_STATE);

  useEffect(() => {
    queryClientRef.current = queryClient;
    stateListeners.add(setState);
    subscriberCount += 1;

    if (sharedEventSource === null) {
      const eventSource: EventSource = new EventSource("/api/events/jobs");

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

        if (!isJobEventPayload(payload)) {
          return;
        }

        handleJobEvent(client, payload);
      };

      sharedEventSource = eventSource;
    }

    return () => {
      stateListeners.delete(setState);
      subscriberCount -= 1;
      if (subscriberCount === 0 && sharedEventSource !== null) {
        sharedEventSource.close();
        sharedEventSource = null;
        queryClientRef.current = null;
      }
    };
  }, [queryClient]);

  return state;
}
