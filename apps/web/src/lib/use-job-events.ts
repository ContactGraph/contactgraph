"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

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

export function useJobEvents(): JobEventsState {
  const queryClient = useQueryClient();
  const [state, setState] = useState<JobEventsState>(INITIAL_JOB_EVENTS_STATE);

  useEffect(() => {
    const eventSource: EventSource = new EventSource("/api/events/jobs");

    const invalidateJobQueries = (): void => {
      void queryClient.invalidateQueries({ queryKey: ["job-discovery-status"] });
      void queryClient.invalidateQueries({ queryKey: ["flat-jobs"] });
    };

    eventSource.onmessage = (messageEvent: MessageEvent<string>) => {
      let payload: unknown;
      try {
        payload = JSON.parse(messageEvent.data) as unknown;
      } catch {
        return;
      }

      if (!isJobEventPayload(payload)) {
        return;
      }

      switch (payload.type) {
        case "discovery_progress":
          setState((current) => ({
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
          invalidateJobQueries();
          break;
        case "discovery_complete":
          setState((current) => ({
            ...current,
            discoveryRunning: false,
            discoveryProgress: null,
          }));
          invalidateJobQueries();
          break;
        case "discovery_cancelled":
          setState((current) => ({
            ...current,
            discoveryRunning: false,
            discoveryProgress: null,
          }));
          invalidateJobQueries();
          break;
        case "scoring_progress":
          setState((current) => ({
            ...current,
            scoringActive: true,
            scoringProgress: {
              scored: payload.scored,
              total: payload.total,
            },
          }));
          invalidateJobQueries();
          break;
        case "scoring_complete":
        case "scoring_cancelled":
          setState((current) => ({
            ...current,
            scoringActive: false,
            scoringProgress: null,
          }));
          invalidateJobQueries();
          break;
        default:
          break;
      }
    };

    return () => {
      eventSource.close();
    };
  }, [queryClient]);

  return state;
}
