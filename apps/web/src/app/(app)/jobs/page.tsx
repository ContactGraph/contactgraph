"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import {
  Bookmark,
  Download,
  ExternalLink,
  Loader2,
  RefreshCw,
  Settings,
  XCircle,
} from "lucide-react";
import Link from "next/link";

import {
  CompactCell,
  CompactSortHeader,
  CompactTableShell,
} from "@/components/data-table/compact-table";
import { JobDetailPanel } from "@/components/job-detail-panel";
import { JobSetupCards } from "@/components/setup/job-setup-cards";
import { UnsavedChangesDialog } from "@/components/unsaved-changes-dialog";
import {
  ResponsiveModal,
  ResponsiveModalContent,
  ResponsiveModalDescription,
  ResponsiveModalHeader,
  ResponsiveModalTitle,
  ResponsiveModalTrigger,
} from "@/components/ui/responsive-modal";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/ui/search-input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  FlatJobListResult,
  JobDiscoveryStatusResult,
  OrgJobItem,
  StartJobDiscoveryResult,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";
import { buildCsv, csvFilename, downloadCsv } from "@/lib/csv-export";
import { useOnboardingPhase } from "@/lib/use-onboarding-phase";
import { useJobBookmarks } from "@/lib/use-job-bookmarks";
import { useJobEvents } from "@/lib/use-job-events";

function formatSalary(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  if (min !== null && max !== null)
    return `$${min.toLocaleString()} – $${max.toLocaleString()}`;
  if (min !== null) return `$${min.toLocaleString()}+`;
  return `Up to $${max!.toLocaleString()}`;
}

function formatRelativeTime(iso: string): string {
  const diff: number = Date.now() - new Date(iso).getTime();
  const mins: number = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours: number = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days: number = Math.floor(hours / 24);
  return `${days}d ago`;
}

function MatchBadge({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <span className="text-xs text-muted-foreground/50">—</span>
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
      className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[11px] font-semibold leading-none ${color}`}
    >
      {score}%
    </span>
  );
}

type JobFilter = "bookmarked" | "relevant" | "all";

function JobsTable() {
  const [search, setSearch] = useState<string>("");
  const [filter, setFilter] = useState<JobFilter>("relevant");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "match", desc: true },
  ]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [settingsDirty, setSettingsDirty] = useState<boolean>(false);
  const [settingsDiscardOpen, setSettingsDiscardOpen] =
    useState<boolean>(false);
  const queryClient = useQueryClient();
  const { bookmarks, toggle: toggleBookmark, isBookmarked } = useJobBookmarks();
  const jobEvents = useJobEvents();

  const jobsQuery = useQuery({
    queryKey: ["flat-jobs"],
    queryFn: () => proxyPost<FlatJobListResult>("list-flat-jobs"),
  });

  const discoveryStatusQuery = useQuery({
    queryKey: ["job-discovery-status"],
    queryFn: () =>
      proxyPost<JobDiscoveryStatusResult>("get-job-discovery-status"),
  });

  const checkAllMutation = useMutation({
    mutationFn: () =>
      proxyPost<StartJobDiscoveryResult>("start-job-discovery"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["job-discovery-status"] });
      void queryClient.invalidateQueries({ queryKey: ["flat-jobs"] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => proxyPost<{ ok: boolean }>("cancel-job-discovery"),
    onSuccess: () => {
      toast.success("Cancelling… will stop after the current batch finishes.");
      void queryClient.invalidateQueries({ queryKey: ["job-discovery-status"] });
      void queryClient.invalidateQueries({ queryKey: ["flat-jobs"] });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const discoveryStatus: JobDiscoveryStatusResult | undefined =
    discoveryStatusQuery.data;
  const discoveryRunning: boolean =
    jobEvents.discoveryRunning || discoveryStatus?.state === "running";
  const scoringActive: boolean = jobEvents.scoringActive;

  const data: FlatJobListResult | undefined = jobsQuery.data;
  const loading: boolean = jobsQuery.isLoading;
  const hasScores: boolean = useMemo(
    () => (data?.jobs ?? []).some((j) => j.match_score !== null),
    [data?.jobs],
  );

  const filteredJobs: OrgJobItem[] = useMemo(() => {
    const all: OrgJobItem[] = data?.jobs ?? [];
    if (filter === "bookmarked") {
      return all.filter((j) => bookmarks.has(j.job_id));
    }
    if (filter === "relevant" && hasScores) {
      return all.filter((j) => j.is_relevant === true);
    }
    return all;
  }, [data?.jobs, filter, hasScores, bookmarks]);

  const columns: ColumnDef<OrgJobItem>[] = useMemo(
    () => [
      {
        id: "match",
        accessorFn: (row: OrgJobItem) => row.match_score ?? 0,
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Match" />
        ),
        cell: ({ row }) => <MatchBadge score={row.original.match_score} />,
        meta: { width: "w-[3.5rem]" },
      },
      {
        id: "title",
        accessorFn: (row: OrgJobItem) => row.title,
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Title" />
        ),
        cell: ({ row }) => (
          <CompactCell value={row.original.title} className="font-medium" />
        ),
        meta: { width: "w-[14rem]" },
      },
      {
        id: "company",
        accessorFn: (row: OrgJobItem) => row.org_name ?? "",
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Company" />
        ),
        cell: ({ row }) => {
          const orgName: string | null = row.original.org_name;
          if (!orgName) return <CompactCell value="—" />;
          return (
            <Link
              href={`/graph?tab=organizations&search=${encodeURIComponent(orgName)}`}
              className="block truncate text-xs text-primary hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              {orgName}
            </Link>
          );
        },
        meta: { width: "w-[8rem]" },
      },
      {
        id: "location",
        accessorFn: (row: OrgJobItem) => row.location ?? "",
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Location" />
        ),
        cell: ({ row }) => {
          const loc: string | null = row.original.location;
          const remote: string | null = row.original.remote_status;
          return (
            <div className="flex items-center gap-1 truncate">
              <CompactCell value={loc ?? "—"} />
              {remote ? (
                <Badge
                  variant="secondary"
                  className="shrink-0 px-1 py-0 text-[10px]"
                >
                  {remote}
                </Badge>
              ) : null}
            </div>
          );
        },
        meta: { width: "w-[8rem]" },
      },
      {
        id: "salary",
        accessorFn: (row: OrgJobItem) => row.salary_min ?? row.salary_max ?? 0,
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Salary" />
        ),
        cell: ({ row }) => (
          <CompactCell
            value={
              formatSalary(row.original.salary_min, row.original.salary_max) ??
              "—"
            }
          />
        ),
        meta: { width: "w-[7rem]" },
      },
      {
        id: "posted",
        accessorFn: (row: OrgJobItem) => row.posted_at ?? row.first_seen_at,
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Posted" />
        ),
        cell: ({ row }) => {
          const dateStr: string | null =
            row.original.posted_at ?? row.original.first_seen_at;
          return <CompactCell value={dateStr ? formatRelativeTime(dateStr) : "—"} />;
        },
        meta: { width: "w-[4rem]" },
      },
      {
        id: "bookmark",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <button
            type="button"
            className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
            onClick={(e) => {
              e.stopPropagation();
              toggleBookmark(row.original.job_id);
            }}
            aria-label={
              isBookmarked(row.original.job_id)
                ? "Remove bookmark"
                : "Bookmark"
            }
          >
            <Bookmark
              className={`size-3.5 ${isBookmarked(row.original.job_id) ? "fill-current text-foreground" : ""}`}
            />
          </button>
        ),
        meta: { width: "w-[2rem]" },
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <a
            href={row.original.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex justify-end rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
            onClick={(e) => e.stopPropagation()}
            aria-label="View posting"
          >
            <ExternalLink className="size-3.5" />
          </a>
        ),
        meta: { width: "w-[2rem]", stickyRight: true },
      },
    ],
    [toggleBookmark, isBookmarked],
  );

  const table = useReactTable({
    data: filteredJobs,
    columns,
    state: { sorting, globalFilter: search },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    globalFilterFn: (row, _columnId, filterValue: string) => {
      const query: string = filterValue.trim().toLowerCase();
      if (!query) return true;
      const job: OrgJobItem = row.original;
      const haystack: string = [
        job.title,
        job.org_name,
        job.location,
        job.department,
        job.remote_status,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const selectedJob: OrgJobItem | undefined = (data?.jobs ?? []).find(
    (j) => j.job_id === selectedJobId,
  );

  const handleDownloadCsv = (): void => {
    const rows: OrgJobItem[] = table
      .getSortedRowModel()
      .rows.map((r) => r.original);
    const csv: string = buildCsv(
      ["Match", "Company", "Title", "Location", "Department", "Remote", "Salary", "URL"],
      rows.map((job) => [
        job.match_score !== null ? `${job.match_score}%` : "",
        job.org_name ?? "",
        job.title,
        job.location ?? "",
        job.department ?? "",
        job.remote_status ?? "",
        formatSalary(job.salary_min, job.salary_max) ?? "",
        job.url,
      ]),
    );
    downloadCsv(csvFilename("jobs"), csv);
  };

  const visibleCount: number = table.getRowModel().rows.length;
  const totalCount: number = data?.total_jobs ?? 0;

  const discoveryProgress = jobEvents.discoveryProgress;
  const scoringProgress = jobEvents.scoringProgress;

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">Open Jobs</h1>
          <p className="text-sm text-muted-foreground">
            {loading
              ? "Loading…"
              : `${visibleCount} of ${totalCount} jobs`}
          </p>
        </div>
        <ResponsiveModal
          open={settingsOpen}
          onOpenChange={(open: boolean) => {
            if (!open && settingsDirty) {
              setSettingsDiscardOpen(true);
              return;
            }
            setSettingsOpen(open);
          }}
        >
          <ResponsiveModalTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="size-8 shrink-0"
              aria-label="Jobs Settings"
            >
              <Settings className="size-4" />
            </Button>
          </ResponsiveModalTrigger>
          <ResponsiveModalContent>
            <ResponsiveModalHeader>
              <ResponsiveModalTitle>Jobs Settings</ResponsiveModalTitle>
              <ResponsiveModalDescription>
                Update your role preferences, location, and target companies.
              </ResponsiveModalDescription>
            </ResponsiveModalHeader>
            <JobSetupCards compact onDirtyChange={setSettingsDirty} />
          </ResponsiveModalContent>
        </ResponsiveModal>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search jobs…"
          className="h-8 w-48"
        />

        <div className="inline-flex h-8 items-center overflow-hidden rounded-md border text-xs">
          {bookmarks.size > 0 ? (
            <button
              type="button"
              className={`h-full px-3 transition-colors ${
                filter === "bookmarked"
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted"
              }`}
              onClick={() => setFilter("bookmarked")}
            >
              Bookmarked ({bookmarks.size})
            </button>
          ) : null}
          {hasScores ? (
            <button
              type="button"
              className={`h-full px-3 transition-colors ${bookmarks.size > 0 ? "border-l" : ""} ${
                filter === "relevant"
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted"
              }`}
              onClick={() => setFilter("relevant")}
            >
              Relevant ({data?.total_relevant ?? 0})
            </button>
          ) : null}
          <button
            type="button"
            className={`h-full border-l px-3 transition-colors ${
              filter === "all"
                ? "bg-primary text-primary-foreground"
                : "hover:bg-muted"
            }`}
            onClick={() => setFilter("all")}
          >
            All ({totalCount})
          </button>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {discoveryRunning || scoringActive ? (
            <Button
              variant="outline"
              size="sm"
              disabled={cancelMutation.isPending}
              onClick={() => cancelMutation.mutate()}
            >
              {cancelMutation.isPending ? (
                <Loader2 className="mr-1.5 size-3.5 animate-spin" />
              ) : (
                <XCircle className="mr-1.5 size-3.5" />
              )}
              Cancel
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              disabled={checkAllMutation.isPending}
              onClick={() => checkAllMutation.mutate()}
            >
              {checkAllMutation.isPending ? (
                <Loader2 className="mr-1.5 size-3.5 animate-spin" />
              ) : (
                <RefreshCw className="mr-1.5 size-3.5" />
              )}
              Check all
            </Button>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleDownloadCsv}
            disabled={loading || visibleCount === 0}
          >
            <Download className="mr-1.5 size-3.5" />
            CSV
          </Button>
        </div>
      </div>

      {discoveryRunning || scoringActive ? (
        <div className="flex flex-col gap-1.5 rounded-lg border bg-muted/40 px-4 py-2.5">
          {discoveryRunning ? (
            <div className="flex items-center gap-2 text-sm">
              <Loader2 className="size-3.5 animate-spin text-primary" />
              <span className="font-medium">Scanning</span>
              <span className="text-muted-foreground">
                {discoveryProgress?.progressMessage ??
                  discoveryStatus?.progress_message ??
                  `${discoveryProgress?.orgsProcessed ?? discoveryStatus?.orgs_processed ?? 0} of ${discoveryProgress?.orgsTotal ?? discoveryStatus?.orgs_total ?? 0} companies`}
              </span>
              {(discoveryProgress?.jobsFound ?? discoveryStatus?.jobs_found ?? 0) > 0 ? (
                <span className="text-muted-foreground">
                  · {discoveryProgress?.jobsFound ?? discoveryStatus?.jobs_found ?? 0} jobs found
                  {(discoveryProgress?.newJobs ?? discoveryStatus?.new_jobs ?? 0) > 0
                    ? ` (${discoveryProgress?.newJobs ?? discoveryStatus?.new_jobs ?? 0} new)`
                    : ""}
                </span>
              ) : null}
            </div>
          ) : null}
          {scoringActive ? (
            <div className="flex items-center gap-2 text-sm">
              <Loader2 className="size-3.5 animate-spin text-primary" />
              <span className="font-medium">Scoring jobs</span>
              <span className="text-muted-foreground">
                ({scoringProgress?.scored ?? 0} of {scoringProgress?.total ?? totalCount})
              </span>
            </div>
          ) : null}
        </div>
      ) : null}

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : (
        <CompactTableShell
          table={table}
          columnCount={columns.length}
          emptyMessage={
            totalCount === 0
              ? "No jobs found yet. Star companies and run Check All."
              : "No jobs match the current filter."
          }
          onRowClick={(job: OrgJobItem) => setSelectedJobId(job.job_id)}
          minWidth="44rem"
        />
      )}

      <Sheet
        open={selectedJobId !== null}
        onOpenChange={(open: boolean) => {
          if (!open) setSelectedJobId(null);
        }}
      >
        <SheetContent className="flex w-full flex-col p-0 sm:max-w-xl">
          <SheetHeader className="px-6 pt-6">
            <SheetTitle>{selectedJob?.title ?? "Job"}</SheetTitle>
            <SheetDescription>
              {selectedJob?.org_name ?? "Job details"}
            </SheetDescription>
          </SheetHeader>
          {selectedJobId ? (
            <JobDetailPanel jobId={selectedJobId} />
          ) : null}
        </SheetContent>
      </Sheet>

      <UnsavedChangesDialog
        open={settingsDiscardOpen}
        onOpenChange={setSettingsDiscardOpen}
        onSave={() => {
          setSettingsDiscardOpen(false);
        }}
        onDiscard={() => {
          setSettingsDiscardOpen(false);
          setSettingsDirty(false);
          setSettingsOpen(false);
        }}
      />
    </div>
  );
}

export default function JobsPage() {
  const onboarding = useOnboardingPhase();

  if (onboarding.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!onboarding.graphReady) {
    return (
      <div className="space-y-4">
        <Alert>
          <AlertDescription>
            Complete graph setup first — import phone contacts and LinkedIn
            connections on{" "}
            <Link href="/graph" className="font-medium underline">
              My Graph
            </Link>
            .
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (onboarding.phase === "job-setup") {
    return <JobSetupCards />;
  }

  return <JobsTable />;
}
