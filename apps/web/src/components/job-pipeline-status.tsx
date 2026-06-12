"use client";

import { useMemo } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";

import { RotatingStatusText } from "@/components/ui/rotating-status-text";
import type { JobScanStatusResult } from "@/lib/api-types";
import type { JobEventsState } from "@/lib/use-job-events";

const SCANNING_SUBTEXT: readonly string[] = [
  "Checking careers pages",
  "Looking for newly posted roles",
  "Skipping jobs you've already seen",
] as const;

const SCORING_SUBTEXT: readonly string[] = [
  "Comparing roles to your target",
  "Checking seniority fit",
  "Weighing location and commute",
] as const;

type PipelinePhase = "scanning" | "scoring" | "idle";

interface JobPipelineStatusProps {
  scanStatus: JobScanStatusResult | undefined;
  jobEvents: JobEventsState;
}

function resolvePipelinePhase(
  scanStatus: JobScanStatusResult | undefined,
  jobEvents: JobEventsState,
): PipelinePhase {
  const scanningActive: boolean =
    scanStatus !== undefined &&
    scanStatus.total > 0 &&
    (scanStatus.scanning_active || scanStatus.scanned < scanStatus.total);

  if (scanningActive) {
    return "scanning";
  }
  if (jobEvents.scoringActive) {
    return "scoring";
  }
  return "idle";
}

function buildRotatingMessages(
  phase: PipelinePhase,
  currentOrgName: string | null,
): readonly string[] {
  if (phase === "scanning") {
    if (currentOrgName !== null && currentOrgName.trim() !== "") {
      return [`Checking ${currentOrgName}…`, ...SCANNING_SUBTEXT];
    }
    return SCANNING_SUBTEXT;
  }
  if (phase === "scoring") {
    return SCORING_SUBTEXT;
  }
  return [];
}

export function JobPipelineStatus({
  scanStatus,
  jobEvents,
}: JobPipelineStatusProps): React.JSX.Element | null {
  const phase: PipelinePhase = resolvePipelinePhase(scanStatus, jobEvents);
  const scoringActive: boolean = jobEvents.scoringActive;
  const scoringProgress = jobEvents.scoringProgress;
  const currentOrgName: string | null = jobEvents.currentScanOrgName;

  const scanningActive: boolean = phase === "scanning";
  const scanComplete: boolean =
    scanStatus !== undefined &&
    scanStatus.total > 0 &&
    scanStatus.scanned >= scanStatus.total &&
    !scanStatus.scanning_active;

  const rotatingMessages: readonly string[] = useMemo(
    () => buildRotatingMessages(phase, currentOrgName),
    [phase, currentOrgName],
  );

  if (scanStatus === undefined || scanStatus.total === 0) {
    return null;
  }

  const isActive: boolean = phase !== "idle";

  let headline: React.ReactNode;
  if (scanningActive) {
    headline = (
      <>
        <span className="font-medium">Finding new jobs</span>
        <span className="text-muted-foreground">
          {" "}
          ({scanStatus.scanned} of {scanStatus.total} companies checked)
        </span>
        {scoringActive ? (
          <span className="text-muted-foreground">
            {" "}
            — ranking matches as they come in
          </span>
        ) : null}
      </>
    );
  } else if (scoringActive) {
    headline = (
      <>
        <span className="font-medium">Ranking jobs against your profile</span>
        <span className="text-muted-foreground">
          {" "}
          ({scoringProgress?.scored ?? 0} of {scoringProgress?.total ?? 0})
        </span>
      </>
    );
  } else {
    headline = (
      <>
        <span className="font-medium">Up to date</span>
        <span className="text-muted-foreground">
          {" "}
          · {scanStatus.scanned} of {scanStatus.total} companies checked today
        </span>
      </>
    );
  }

  return (
    <div className="flex flex-col gap-1 rounded-lg border bg-muted/40 px-4 py-2.5">
      <div className="flex items-center gap-2 text-sm">
        {isActive ? (
          <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
        ) : scanComplete ? (
          <CheckCircle2 className="size-3.5 shrink-0 text-green-600" />
        ) : null}
        <div className="min-w-0">{headline}</div>
      </div>
      {isActive && rotatingMessages.length > 0 ? (
        <RotatingStatusText
          messages={rotatingMessages}
          className="pl-5 text-xs text-muted-foreground"
        />
      ) : null}
    </div>
  );
}
