"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bookmark,
  Building2,
  ExternalLink,
  Loader2,
  MapPin,
  Users,
} from "lucide-react";
import Link from "next/link";

import { JobInterestButtons } from "@/components/job-interest-buttons";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { JobDetailResult, OrgJobItem } from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";
import { useJobBookmarks } from "@/lib/use-job-bookmarks";

function MatchBadge({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <Badge variant="secondary" className="text-xs">
        Unscored
      </Badge>
    );
  }
  const color: string =
    score >= 70
      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
      : score >= 40
        ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
        : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-semibold ${color}`}
    >
      {score}%
    </span>
  );
}

function formatSalary(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  if (min !== null && max !== null)
    return `$${min.toLocaleString()} – $${max.toLocaleString()}`;
  if (min !== null) return `$${min.toLocaleString()}+`;
  return `Up to $${max!.toLocaleString()}`;
}

function stripFormatting(text: string): string {
  let cleaned: string = text
    .replace(/<[^>]+>/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ");
  cleaned = cleaned
    .replace(/#{1,6}\s+/g, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__(.+?)__/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/_(.+?)_/g, "$1")
    .replace(/~~(.+?)~~/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/^[-*+]\s+/gm, "• ")
    .replace(/^\d+\.\s+/gm, "");
  return cleaned.replace(/\s{2,}/g, " ").trim();
}

function SubScoreRow({
  label,
  score,
  reason,
  weight,
}: {
  label: string;
  score: number | null;
  reason: string | null;
  weight: number;
}) {
  if (score === null) return null;
  const barColor: string =
    score >= 70
      ? "bg-green-500"
      : score >= 40
        ? "bg-yellow-500"
        : "bg-red-400";
  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-2">
        <span className="w-24 shrink-0 text-xs font-medium">{label}</span>
        <div className="h-1.5 flex-1 rounded-full bg-muted">
          <div
            className={`h-full rounded-full ${barColor}`}
            style={{ width: `${score}%` }}
          />
        </div>
        <span className="w-8 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
          {score}
        </span>
        <span className="w-8 shrink-0 text-right text-[10px] text-muted-foreground/60">
          ×{weight}%
        </span>
      </div>
      {reason ? (
        <p className="pl-[6.5rem] text-xs text-muted-foreground">{reason}</p>
      ) : null}
    </div>
  );
}

export function JobDetailPanel({
  jobId,
  onSelectPerson,
}: {
  jobId: string;
  onSelectPerson?: (personId: string) => void;
}) {
  const { toggle: toggleBookmark, isBookmarked } = useJobBookmarks();

  const detailQuery = useQuery({
    queryKey: ["job-detail", jobId],
    queryFn: () =>
      proxyPost<JobDetailResult>("get-job-detail", { job_id: jobId }),
    enabled: jobId !== "",
  });

  const invalidateDetail = (): void => {
    void detailQuery.refetch();
  };

  if (detailQuery.isLoading) {
    return (
      <div className="space-y-4 px-6 py-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (detailQuery.error) {
    return (
      <div className="px-6 py-4 text-sm text-destructive">
        {detailQuery.error.message}
      </div>
    );
  }

  const data: JobDetailResult | undefined = detailQuery.data;
  if (!data) return null;

  const job: OrgJobItem = data.job;
  const salary: string | null = formatSalary(job.salary_min, job.salary_max);
  const ownContacts = data.contacts.filter((contact) => contact.shared_from === null);
  const sharedContacts = data.contacts.filter((contact) => contact.shared_from !== null);
  const metaParts: string[] = [
    job.location,
    job.department,
    job.remote_status,
  ].filter((v): v is string => v !== null && v !== undefined);

  return (
    <div className="flex-1 space-y-5 overflow-y-auto px-6 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <MatchBadge score={job.match_score} />
            {salary ? (
              <span className="text-sm font-medium text-muted-foreground">
                {salary}
              </span>
            ) : null}
          </div>
          {job.role_score !== null ||
          job.seniority_score !== null ||
          job.location_score !== null ||
          job.qualification_score !== null ? (
            <div className="space-y-1.5 rounded-md border bg-muted/30 px-3 py-2">
              <SubScoreRow
                label="Function"
                score={job.role_score}
                reason={job.role_reason}
                weight={45}
              />
              <SubScoreRow
                label="Qualification"
                score={job.qualification_score}
                reason={job.qualification_reason}
                weight={25}
              />
              <SubScoreRow
                label="Seniority"
                score={job.seniority_score}
                reason={job.seniority_reason}
                weight={15}
              />
              <SubScoreRow
                label="Location"
                score={job.location_score}
                reason={job.location_reason}
                weight={15}
              />
            </div>
          ) : job.relevance_reason ? (
            <p className="text-sm text-muted-foreground">
              {job.relevance_reason}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <JobInterestButtons
            jobId={job.job_id}
            userInterest={job.user_interest}
            onChanged={invalidateDetail}
          />
          <button
            type="button"
            className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground"
            onClick={() => toggleBookmark(job.job_id)}
            aria-label={
              isBookmarked(job.job_id) ? "Remove bookmark" : "Bookmark"
            }
          >
            <Bookmark
              className={`size-5 ${isBookmarked(job.job_id) ? "fill-current text-foreground" : ""}`}
            />
          </button>
        </div>
      </div>

      {metaParts.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <MapPin className="size-3.5" />
          {metaParts.join(" · ")}
        </div>
      ) : null}

      {job.description_snippet ? (
        <div className="space-y-1">
          <h3 className="text-sm font-medium">Description</h3>
          <p className="whitespace-pre-line text-sm text-muted-foreground">
            {stripFormatting(job.description_snippet)}
          </p>
        </div>
      ) : null}

      <Button variant="default" size="sm" asChild>
        <a href={job.url} target="_blank" rel="noopener noreferrer">
          View posting
          <ExternalLink className="ml-1.5 size-3.5" />
        </a>
      </Button>

      {data.org_primary_domain || data.org_description ? (
        <div className="space-y-1.5 rounded-lg border p-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Building2 className="size-4" />
            <Link
              href={`/graph?tab=organizations&org=${encodeURIComponent(job.org_id ?? "")}`}
              className="text-primary hover:underline"
            >
              {job.org_name}
            </Link>
            {data.org_primary_domain ? (
              <span className="text-xs text-muted-foreground">
                {data.org_primary_domain}
              </span>
            ) : null}
          </div>
          {data.org_description ? (
            <p className="text-xs text-muted-foreground">
              {data.org_description}
            </p>
          ) : null}
        </div>
      ) : null}

      {ownContacts.length > 0 ? (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-sm font-medium">
            <Users className="size-4" />
            Your contacts ({data.contact_count})
          </div>
          <div className="space-y-1">
            {ownContacts.map((contact) => (
              <button
                key={contact.person_id}
                type="button"
                className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted"
                onClick={() => onSelectPerson?.(contact.person_id)}
              >
                <span className="truncate font-medium">
                  {contact.display_name}
                </span>
                {contact.current_role ? (
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {contact.current_role}
                  </span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {sharedContacts.length > 0 ? (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
            <Users className="size-4" />
            Contacts via friends ({job.shared_contact_count})
          </div>
          <div className="space-y-1">
            {sharedContacts.map((contact) => (
              <div
                key={`${contact.person_id}-${contact.shared_from ?? "shared"}`}
                className="flex w-full items-center justify-between rounded px-2 py-1.5 text-sm"
              >
                <div className="min-w-0">
                  <span className="truncate font-medium">
                    {contact.display_name}
                  </span>
                  {contact.shared_from ? (
                    <p className="truncate text-xs text-muted-foreground">
                      via {contact.shared_from}
                    </p>
                  ) : null}
                </div>
                {contact.current_role ? (
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {contact.current_role}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="space-y-1 text-xs text-muted-foreground/60">
        <p>Source: {job.source}</p>
        {job.posted_at ? (
          <p>Posted: {new Date(job.posted_at).toLocaleDateString()}</p>
        ) : null}
        <p>First seen: {new Date(job.first_seen_at).toLocaleDateString()}</p>
      </div>
    </div>
  );
}
