"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import {
  Bookmark,
  Download,
  ExternalLink,
  Settings,
} from "lucide-react";
import Link from "next/link";

import {
  CompactCell,
  CompactSortHeader,
  CompactTableShell,
} from "@/components/data-table/compact-table";
import { JobDetailPanel } from "@/components/job-detail-panel";
import { JobInterestButtons } from "@/components/job-interest-buttons";
import { JobPipelineStatus } from "@/components/job-pipeline-status";
import { OrgLogo } from "@/components/org-logo";
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
  JobScanStatusResult,
  OrgJobItem,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";
import { buildCsv, csvFilename, downloadCsv } from "@/lib/csv-export";
import { formatNetworkContactsLabel } from "@/lib/format-network-contacts-label";
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

function MatchBadge({
  score,
  pending = false,
}: {
  score: number | null;
  pending?: boolean;
}) {
  if (score === null) {
    return (
      <span
        className={`text-xs text-muted-foreground/50 ${pending ? "animate-pulse" : ""}`}
      >
        —
      </span>
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

type JobFilter = "new" | "liked" | "dismissed" | "bookmarked" | "all";

function useCountBump(value: number): boolean {
  const prevRef = useRef<number>(value);
  const [bump, setBump] = useState<boolean>(false);

  useEffect(() => {
    if (value > prevRef.current) {
      prevRef.current = value;
      setBump(true);
      const id: ReturnType<typeof setTimeout> = setTimeout(() => setBump(false), 800);
      return () => clearTimeout(id);
    }
    prevRef.current = value;
  }, [value]);

  return bump;
}

function jobMatchesSearch(job: OrgJobItem, query: string): boolean {
  if (!query) return true;
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
}

function JobsTable() {
  const [search, setSearch] = useState<string>("");
  const [filter, setFilter] = useState<JobFilter>("new");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "match", desc: true },
  ]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [settingsDirty, setSettingsDirty] = useState<boolean>(false);
  const [settingsDiscardOpen, setSettingsDiscardOpen] =
    useState<boolean>(false);
  const { bookmarks, toggle: toggleBookmark, isBookmarked } = useJobBookmarks();
  const jobEvents = useJobEvents();

  const [hiddenJobs, setHiddenJobs] = useState<ReadonlyMap<string, "interested" | "dismissed">>(new Map());

  const handleJobActed = useCallback((jobId: string, interest: "interested" | "dismissed"): void => {
    setTimeout(() => {
      setHiddenJobs((prev) => new Map([...prev, [jobId, interest]]));
    }, 400);
  }, []);

  const jobsQuery = useQuery({
    queryKey: ["flat-jobs"],
    queryFn: () => proxyPost<FlatJobListResult>("list-flat-jobs"),
  });

  const scanStatusQuery = useQuery({
    queryKey: ["job-scan-status"],
    queryFn: () => proxyPost<JobScanStatusResult>("get-job-scan-status"),
  });

  const scanStatus: JobScanStatusResult | undefined = scanStatusQuery.data;
  const scoringActive: boolean = jobEvents.scoringActive;

  const data: FlatJobListResult | undefined = jobsQuery.data;
  const loading: boolean = jobsQuery.isLoading;

  const allJobs: OrgJobItem[] = data?.jobs ?? [];
  const searchQuery: string = search.trim().toLowerCase();
  const isSearching: boolean = searchQuery.length > 0;

  const newCount: number = useMemo(
    () =>
      allJobs.filter(
        (j) => j.is_relevant === true && j.user_interest === null,
      ).length,
    [allJobs],
  );
  const likedCount: number = useMemo(() => {
    let count: number = allJobs.filter((j) => j.user_interest === "interested").length;
    for (const [jobId, interest] of hiddenJobs) {
      if (interest !== "interested") continue;
      const job: OrgJobItem | undefined = allJobs.find((j) => j.job_id === jobId);
      if (job && job.user_interest !== "interested") count++;
    }
    return count;
  }, [allJobs, hiddenJobs]);
  const dismissedCount: number = useMemo(() => {
    let count: number = allJobs.filter((j) => j.user_interest === "dismissed").length;
    for (const [jobId, interest] of hiddenJobs) {
      if (interest !== "dismissed") continue;
      const job: OrgJobItem | undefined = allJobs.find((j) => j.job_id === jobId);
      if (job && job.user_interest !== "dismissed") count++;
    }
    return count;
  }, [allJobs, hiddenJobs]);

  const likedBump: boolean = useCountBump(likedCount);
  const dismissedBump: boolean = useCountBump(dismissedCount);

  const tabFilteredJobs: OrgJobItem[] = useMemo(() => {
    const base: OrgJobItem[] = allJobs.filter((j) => !hiddenJobs.has(j.job_id));
    if (filter === "bookmarked") {
      return base.filter((j) => bookmarks.has(j.job_id));
    }
    if (filter === "new") {
      return base.filter(
        (j) => j.is_relevant === true && j.user_interest === null,
      );
    }
    if (filter === "liked") {
      return base.filter((j) => j.user_interest === "interested");
    }
    if (filter === "dismissed") {
      return base.filter((j) => j.user_interest === "dismissed");
    }
    return base;
  }, [allJobs, filter, bookmarks, hiddenJobs]);

  const filteredJobs: OrgJobItem[] = useMemo(() => {
    const base: OrgJobItem[] = isSearching ? allJobs : tabFilteredJobs;
    if (!isSearching) return base;
    return base.filter((job) => jobMatchesSearch(job, searchQuery));
  }, [allJobs, tabFilteredJobs, isSearching, searchQuery]);

  const columns: ColumnDef<OrgJobItem>[] = useMemo(
    () => [
      {
        id: "match",
        accessorFn: (row: OrgJobItem) => row.match_score ?? 0,
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Match" />
        ),
        cell: ({ row }) => (
          <MatchBadge
            score={row.original.match_score}
            pending={scoringActive && row.original.match_score === null}
          />
        ),
        meta: { width: "w-[3.5rem] sm:w-[5rem]" },
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
        meta: { width: "w-[14rem] sm:w-[21rem]" },
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
              className="flex items-center gap-1.5 truncate text-xs text-primary no-underline"
              onClick={(e) => e.stopPropagation()}
            >
              <OrgLogo
                domain={row.original.org_primary_domain}
                name={orgName}
                size={16}
              />
              <span className="truncate">{orgName}</span>
            </Link>
          );
        },
        meta: { width: "w-[8rem] sm:w-[12rem]" },
      },
      {
        id: "contacts",
        accessorFn: (row: OrgJobItem) => row.primary_contact_name ?? "",
        header: () => (
          <span className="truncate text-xs font-medium">Contacts</span>
        ),
        enableSorting: false,
        cell: ({ row }) => (
          <CompactCell
            className="text-xs"
            value={formatNetworkContactsLabel({
              primaryContactName: row.original.primary_contact_name,
              contactCount: row.original.contact_count,
              sharedPrimaryContactName: row.original.shared_primary_contact_name,
              sharedContactCount: row.original.shared_contact_count,
              sharedPrimaryBridgeName: row.original.shared_primary_bridge_name,
            })}
          />
        ),
        meta: { width: "w-[7rem] sm:w-[10.5rem]" },
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
        meta: { width: "w-[8rem] sm:w-[12rem]" },
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
        meta: { width: "w-[7rem] sm:w-[10.5rem]" },
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
        meta: { width: "w-[4rem] sm:w-[6rem]" },
      },
      {
        id: "interest",
        header: () => (
          <span className="truncate text-xs font-medium">Interest</span>
        ),
        enableSorting: false,
        cell: ({ row }) => (
          <JobInterestButtons
            jobId={row.original.job_id}
            userInterest={row.original.user_interest}
            compact
            onChanged={(interest) => handleJobActed(row.original.job_id, interest)}
          />
        ),
        meta: { width: "w-[4.5rem] sm:w-[5.5rem]" },
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
        meta: { width: "w-[2rem]", hiddenClass: "hidden sm:table-cell" },
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
        meta: { width: "w-[2rem]", stickyRight: true, hiddenClass: "hidden sm:table-cell" },
      },
    ],
    [toggleBookmark, isBookmarked, scoringActive, handleJobActed],
  );

  const table = useReactTable({
    data: filteredJobs,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getRowId: (row: OrgJobItem) => row.job_id,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
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

  const jobsCountLabel: string = loading
    ? "Loading…"
    : isSearching
      ? `${visibleCount} matching job${visibleCount === 1 ? "" : "s"} across all categories`
      : filter === "new"
        ? `${visibleCount} new job${visibleCount === 1 ? "" : "s"}`
        : filter === "liked"
          ? `${visibleCount} liked job${visibleCount === 1 ? "" : "s"}`
          : filter === "dismissed"
            ? `${visibleCount} dismissed job${visibleCount === 1 ? "" : "s"}`
            : `${visibleCount} of ${totalCount} jobs${
                scoringActive ? " · more jobs are still being ranked" : ""
              }`;

  return (
    <div className="space-y-2 sm:space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">Open Jobs</h1>
          <p className="text-sm text-muted-foreground">{jobsCountLabel}</p>
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
          <button
            type="button"
            className={`h-full px-3 transition-colors ${
              filter === "new"
                ? "bg-primary text-primary-foreground"
                : "hover:bg-muted"
            }`}
            onClick={() => setFilter("new")}
          >
            New ({newCount})
          </button>
          <button
            type="button"
            className={`h-full border-l px-3 transition-all duration-300 ${
              filter === "liked"
                ? "bg-primary text-primary-foreground"
                : "hover:bg-muted"
            } ${likedBump && filter !== "liked" ? "bg-muted text-base font-semibold" : "text-xs"}`}
            onClick={() => setFilter("liked")}
          >
            Liked ({likedCount})
          </button>
          <button
            type="button"
            className={`h-full border-l px-3 transition-all duration-300 ${
              filter === "dismissed"
                ? "bg-primary text-primary-foreground"
                : "hover:bg-muted"
            } ${dismissedBump && filter !== "dismissed" ? "bg-muted text-base font-semibold" : "text-xs"}`}
            onClick={() => setFilter("dismissed")}
          >
            Dismissed ({dismissedCount})
          </button>
          {bookmarks.size > 0 ? (
            <button
              type="button"
              className={`h-full border-l px-3 transition-colors ${
                filter === "bookmarked"
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted"
              }`}
              onClick={() => setFilter("bookmarked")}
            >
              Bookmarked ({bookmarks.size})
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

      <JobPipelineStatus scanStatus={scanStatus} jobEvents={jobEvents} />

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
              ? "No jobs found yet. Select companies and jobs will appear automatically once scanned."
              : "No jobs match the current filter."
          }
          onRowClick={(job: OrgJobItem) => setSelectedJobId(job.job_id)}
          minWidth="40rem"
        />
      )}

      <Sheet
        open={selectedJobId !== null}
        onOpenChange={(open: boolean) => {
          if (!open) setSelectedJobId(null);
        }}
      >
        <SheetContent className="flex w-full flex-col p-0 sm:max-w-xl">
          <SheetHeader
            actions={
              selectedJob !== undefined ? (
                <Button variant="ghost" size="icon" className="size-9 shrink-0" asChild>
                  <a
                    href={selectedJob.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="View posting"
                  >
                    <ExternalLink className="size-4" />
                  </a>
                </Button>
              ) : undefined
            }
          >
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
