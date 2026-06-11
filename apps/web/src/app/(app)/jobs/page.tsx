"use client";

import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Loader2,
  RefreshCw,
  Settings,
  Users,
} from "lucide-react";
import Link from "next/link";

import { PersonDetailPanel } from "@/components/person-detail-panel";
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
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  JobDiscoveryStatusResult,
  ListOrgJobsResult,
  ListOrgListsResult,
  ListOrgsResult,
  OrgDetailResult,
  OrgJobItem,
  OrgListItem,
  OrgPersonSummary,
  PersonDetailResult,
  StartJobDiscoveryResult,
  StartSingleOrgDiscoveryResult,
} from "@/lib/api-types";
import type { EditableDetailPanelHandle } from "@/lib/editable-detail-panel";
import { proxyPost } from "@/lib/proxy-client";
import { findJobProspectsList } from "@/lib/setup-utils";
import { useOnboardingPhase } from "@/lib/use-onboarding-phase";

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

function hasRelevanceData(data: ListOrgJobsResult | undefined): boolean {
  if (!data) return false;
  return data.companies.some((c) =>
    c.jobs.some((j) => j.is_relevant !== null),
  );
}

interface OrgTile {
  org_id: string;
  org_name: string;
  primary_domain: string | null;
  description: string | null;
  contact_count: number;
  last_checked_at: string | null;
  jobs: OrgJobItem[];
  allJobs: OrgJobItem[];
  status: "scanning" | "done" | "no-jobs";
}

const CONTACTS_COLLAPSED_LIMIT: number = 3;

function OrgContactsList({
  orgId,
  contactCount,
  onSelectPerson,
}: {
  orgId: string;
  contactCount: number;
  onSelectPerson: (personId: string) => void;
}) {
  const [expanded, setExpanded] = useState<boolean>(false);
  const orgDetailQuery = useQuery({
    queryKey: ["org-detail", orgId],
    queryFn: () => proxyPost<OrgDetailResult>("get-org", { org_id: orgId }),
    staleTime: 120_000,
  });

  const people: readonly OrgPersonSummary[] =
    orgDetailQuery.data?.people ?? [];

  if (contactCount === 0) return null;

  if (orgDetailQuery.isLoading) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Users className="size-3" />
        <Loader2 className="size-3 animate-spin" />
        Loading {contactCount} contact{contactCount !== 1 ? "s" : ""}…
      </div>
    );
  }

  if (people.length === 0) return null;

  const visiblePeople: readonly OrgPersonSummary[] =
    expanded ? people : people.slice(0, CONTACTS_COLLAPSED_LIMIT);
  const hiddenCount: number = people.length - visiblePeople.length;

  return (
    <div className="flex items-center gap-1 text-xs text-muted-foreground">
      <Users className="size-3 shrink-0" />
      <span className="flex flex-wrap items-center gap-x-0.5">
        {visiblePeople.map((person, idx) => (
          <span key={person.person_id}>
            {idx > 0 ? ", " : ""}
            <button
              type="button"
              className="text-primary underline-offset-2 hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                onSelectPerson(person.person_id);
              }}
            >
              {person.display_name}
            </button>
            {person.current_role ? (
              <span className="text-muted-foreground/70">
                {" "}
                ({person.current_role})
              </span>
            ) : null}
            {person.shared_from ? (
              <span className="ml-0.5 inline-flex items-center rounded border px-1 py-0 text-[10px] text-muted-foreground">
                via {person.shared_from}
              </span>
            ) : null}
          </span>
        ))}
        {hiddenCount > 0 ? (
          <button
            type="button"
            className="ml-0.5 text-primary underline-offset-2 hover:underline"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(true);
            }}
          >
            and {hiddenCount} other{hiddenCount !== 1 ? "s" : ""}
          </button>
        ) : null}
        {expanded && people.length > CONTACTS_COLLAPSED_LIMIT ? (
          <button
            type="button"
            className="ml-0.5 text-primary underline-offset-2 hover:underline"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(false);
            }}
          >
            Show less
          </button>
        ) : null}
      </span>
    </div>
  );
}

function JobsListings() {
  const [showAll, setShowAll] = useState<boolean>(false);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [settingsDirty, setSettingsDirty] = useState<boolean>(false);
  const [settingsDiscardOpen, setSettingsDiscardOpen] =
    useState<boolean>(false);
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null);
  const [isDetailDirty, setIsDetailDirty] = useState<boolean>(false);
  const [discardDialogOpen, setDiscardDialogOpen] = useState<boolean>(false);
  const [isClosingSave, setIsClosingSave] = useState<boolean>(false);
  const [expandedOrgs, setExpandedOrgs] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [checkingOrgs, setCheckingOrgs] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const detailPanelRef = useRef<EditableDetailPanelHandle>(null);
  const queryClient = useQueryClient();

  const jobsQuery = useQuery({
    queryKey: ["org-jobs"],
    queryFn: () => proxyPost<ListOrgJobsResult>("list-org-jobs"),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data !== undefined && data.total_jobs === 0 ? 5000 : false;
    },
  });

  const orgListsQuery = useQuery({
    queryKey: ["org-lists"],
    queryFn: () => proxyPost<ListOrgListsResult>("list-org-lists"),
  });

  const orgsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () => proxyPost<ListOrgsResult>("list-orgs"),
    staleTime: 60_000,
  });

  const discoveryStatusQuery = useQuery({
    queryKey: ["job-discovery-status"],
    queryFn: () =>
      proxyPost<JobDiscoveryStatusResult>("get-job-discovery-status"),
    refetchInterval: (query) =>
      query.state.data?.state === "running" ? 2000 : false,
  });

  const personDetailQuery = useQuery({
    queryKey: ["person", selectedPersonId],
    queryFn: () =>
      proxyPost<PersonDetailResult>("get-person", {
        person_id: selectedPersonId,
      }),
    enabled: selectedPersonId !== null,
  });

  const checkAllMutation = useMutation({
    mutationFn: () =>
      proxyPost<StartJobDiscoveryResult>("start-job-discovery"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["job-discovery-status"] });
      void queryClient.invalidateQueries({ queryKey: ["org-jobs"] });
    },
  });

  const discoveryRunning: boolean =
    discoveryStatusQuery.data?.state === "running";

  const data: ListOrgJobsResult | undefined = jobsQuery.data;
  const loading: boolean = jobsQuery.isLoading || orgsQuery.isLoading;
  const hasRelevance: boolean = hasRelevanceData(data);

  const starredOrgIds: ReadonlySet<string> = useMemo(() => {
    const list = findJobProspectsList(orgListsQuery.data?.lists ?? []);
    return new Set(list?.org_ids ?? []);
  }, [orgListsQuery.data?.lists]);

  const orgNameMap: ReadonlyMap<string, OrgListItem> = useMemo(() => {
    const map = new Map<string, OrgListItem>();
    for (const org of orgsQuery.data?.orgs ?? []) {
      map.set(org.org_id, org);
    }
    return map;
  }, [orgsQuery.data?.orgs]);

  const lastCheckedMap: ReadonlyMap<string, string> = useMemo(() => {
    const map = new Map<string, string>();
    for (const company of data?.companies ?? []) {
      if (company.last_checked_at) {
        map.set(company.org_id, company.last_checked_at);
      }
    }
    return map;
  }, [data?.companies]);

  const jobsByOrgId: ReadonlyMap<
    string,
    { filtered: OrgJobItem[]; all: OrgJobItem[] }
  > = useMemo(() => {
    const map = new Map<
      string,
      { filtered: OrgJobItem[]; all: OrgJobItem[] }
    >();
    for (const company of data?.companies ?? []) {
      const filtered: OrgJobItem[] =
        !hasRelevance || showAll
          ? company.jobs
          : company.jobs.filter((j) => j.is_relevant !== false);
      map.set(company.org_id, { filtered, all: company.jobs });
    }
    return map;
  }, [data?.companies, hasRelevance, showAll]);

  const orgTiles: OrgTile[] = useMemo(() => {
    const tiles: OrgTile[] = [];
    for (const orgId of starredOrgIds) {
      const orgInfo: OrgListItem | undefined = orgNameMap.get(orgId);
      const company = (data?.companies ?? []).find((c) => c.org_id === orgId);
      const jobData = jobsByOrgId.get(orgId);
      const jobs: OrgJobItem[] = jobData?.filtered ?? [];
      const allJobs: OrgJobItem[] = jobData?.all ?? [];
      const status: OrgTile["status"] =
        allJobs.length > 0
          ? "done"
          : discoveryRunning || checkingOrgs.has(orgId)
            ? "scanning"
            : "no-jobs";
      tiles.push({
        org_id: orgId,
        org_name: company?.org_name ?? orgInfo?.name ?? "Unknown",
        primary_domain:
          company?.primary_domain ?? orgInfo?.primary_domain ?? null,
        description: company?.description ?? orgInfo?.description ?? null,
        contact_count:
          (orgInfo?.contact_count ?? 0) + (orgInfo?.shared_contact_count ?? 0),
        last_checked_at: lastCheckedMap.get(orgId) ?? null,
        jobs,
        allJobs,
        status,
      });
    }
    tiles.sort((a, b) => {
      if (a.jobs.length > 0 && b.jobs.length === 0) return -1;
      if (a.jobs.length === 0 && b.jobs.length > 0) return 1;
      return a.org_name.localeCompare(b.org_name);
    });
    return tiles;
  }, [
    starredOrgIds,
    orgNameMap,
    jobsByOrgId,
    lastCheckedMap,
    data?.companies,
    discoveryRunning,
    checkingOrgs,
  ]);

  const totalShown: number = orgTiles.reduce(
    (acc, t) => acc + t.jobs.length,
    0,
  );

  const handleCheckOrg = async (orgId: string): Promise<void> => {
    setCheckingOrgs((prev) => new Set([...prev, orgId]));
    try {
      await proxyPost<StartSingleOrgDiscoveryResult>(
        "start-single-org-job-discovery",
        { org_id: orgId },
      );
      await queryClient.invalidateQueries({ queryKey: ["org-jobs"] });
    } finally {
      setCheckingOrgs((prev) => {
        const next = new Set(prev);
        next.delete(orgId);
        return next;
      });
    }
  };

  const handleToggle = (orgId: string, open: boolean): void => {
    setExpandedOrgs((prev) => {
      const next = new Set(prev);
      if (open) {
        next.add(orgId);
      } else {
        next.delete(orgId);
      }
      return next;
    });
  };

  const closeDetailPanel = (): void => {
    setSelectedPersonId(null);
    setIsDetailDirty(false);
    setDiscardDialogOpen(false);
  };

  const handleDetailSheetOpenChange = (open: boolean): void => {
    if (open) return;
    if (isDetailDirty) {
      setDiscardDialogOpen(true);
      return;
    }
    closeDetailPanel();
  };

  const handleSaveAndClose = async (): Promise<void> => {
    setIsClosingSave(true);
    try {
      const saved: boolean = (await detailPanelRef.current?.save()) ?? false;
      if (saved) closeDetailPanel();
    } finally {
      setIsClosingSave(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight">Open Jobs</h1>
            <p className="text-sm text-muted-foreground">
              {loading
                ? "Loading…"
                : discoveryRunning
                  ? `Scanning ${orgTiles.length} companies…`
                  : `${totalShown} jobs across ${orgTiles.length} companies`}
            </p>
          </div>
          <ResponsiveModal open={settingsOpen} onOpenChange={(open: boolean) => {
            if (!open && settingsDirty) {
              setSettingsDiscardOpen(true);
              return;
            }
            setSettingsOpen(open);
          }}>
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
          {hasRelevance ? (
            <div className="inline-flex h-8 items-center overflow-hidden rounded-md border text-xs">
              <button
                type="button"
                className={`h-full px-3 transition-colors ${
                  !showAll
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted"
                }`}
                onClick={() => setShowAll(false)}
              >
                Relevant ({data?.total_relevant ?? 0})
              </button>
              <button
                type="button"
                className={`h-full border-l px-3 transition-colors ${
                  showAll
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted"
                }`}
                onClick={() => setShowAll(true)}
              >
                All ({data?.total_jobs ?? 0})
              </button>
            </div>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            disabled={discoveryRunning || checkAllMutation.isPending}
            onClick={() => checkAllMutation.mutate()}
          >
            {discoveryRunning || checkAllMutation.isPending ? (
              <Loader2 className="mr-1.5 size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="mr-1.5 size-3.5" />
            )}
            Check all
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : null}

      {!loading && orgTiles.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No companies starred. Go to{" "}
          <Link
            href="/graph?tab=organizations"
            className="font-medium underline"
          >
            Organizations
          </Link>{" "}
          and star some companies to monitor for jobs.
        </p>
      ) : (
        orgTiles.map((tile) => {
          const hiddenCount: number = tile.allJobs.length - tile.jobs.length;
          const isChecking: boolean = checkingOrgs.has(tile.org_id);
          const isOpen: boolean =
            expandedOrgs.has(tile.org_id) ||
            (tile.jobs.length > 0 && tile.jobs.length <= 5);
          return (
            <details
              key={tile.org_id}
              className="group rounded-lg border"
              open={isOpen}
              onToggle={(e) =>
                handleToggle(
                  tile.org_id,
                  (e.target as HTMLDetailsElement).open,
                )
              }
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 [&::-webkit-details-marker]:hidden">
                <div className="flex items-center gap-2">
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/graph?tab=organizations&org=${encodeURIComponent(tile.org_id)}`}
                        className="font-medium text-primary hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {tile.org_name}
                      </Link>
                      {tile.primary_domain ? (
                        <span className="text-xs text-muted-foreground">
                          {tile.primary_domain}
                        </span>
                      ) : null}
                      {tile.contact_count > 0 ? (
                        <span className="flex items-center gap-0.5 text-xs text-muted-foreground">
                          <Users className="size-3" />
                          {tile.contact_count}
                        </span>
                      ) : null}
                    </div>
                    {tile.description ? (
                      <p className="line-clamp-1 text-xs text-muted-foreground">
                        {tile.description}
                      </p>
                    ) : null}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    {tile.status === "scanning" || isChecking ? (
                      <>
                        <Loader2 className="size-3.5 animate-spin" />
                        Scanning…
                      </>
                    ) : tile.allJobs.length > 0 ? (
                      <>
                        <CheckCircle2 className="size-3.5 text-green-600" />
                        {tile.jobs.length} job
                        {tile.jobs.length !== 1 ? "s" : ""}
                        {hiddenCount > 0 ? (
                          <span className="text-muted-foreground/60">
                            (+{hiddenCount} filtered)
                          </span>
                        ) : null}
                      </>
                    ) : (
                      "No jobs found"
                    )}
                  </span>
                  <button
                    type="button"
                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
                    title="Check now"
                    disabled={isChecking || discoveryRunning}
                    onClick={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      void handleCheckOrg(tile.org_id);
                    }}
                  >
                    {isChecking ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="size-3.5" />
                    )}
                  </button>
                </div>
              </summary>

              <div className="space-y-3 px-4 pb-4 pt-3">
                <div className="flex items-center justify-between">
                  {tile.contact_count > 0 ? (
                    <OrgContactsList
                      orgId={tile.org_id}
                      contactCount={tile.contact_count}
                      onSelectPerson={setSelectedPersonId}
                    />
                  ) : (
                    <span />
                  )}
                  {tile.last_checked_at ? (
                    <span className="shrink-0 text-[10px] text-muted-foreground/60">
                      Checked {formatRelativeTime(tile.last_checked_at)}
                    </span>
                  ) : null}
                </div>

                <div className="border-t" />

                {tile.jobs.map((job) => {
                  const salary: string | null = formatSalary(
                    job.salary_min,
                    job.salary_max,
                  );
                  return (
                    <Card key={job.job_id}>
                      <CardHeader className="pb-2">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <CardTitle className="text-base">
                              {job.title}
                            </CardTitle>
                            <CardDescription>
                              {[
                                job.location,
                                job.department,
                                job.remote_status,
                              ]
                                .filter(Boolean)
                                .join(" · ")}
                            </CardDescription>
                          </div>
                          <div className="flex items-center gap-1.5">
                            {job.relevance_reason ? (
                              <Badge
                                variant="outline"
                                className="text-xs font-normal"
                              >
                                {job.relevance_reason}
                              </Badge>
                            ) : null}
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        {job.description_snippet ? (
                          <p className="text-sm text-muted-foreground">
                            {job.description_snippet}
                          </p>
                        ) : null}
                        {salary ? (
                          <p className="text-sm font-medium">{salary}</p>
                        ) : null}
                        <Button
                          variant="link"
                          className="h-auto p-0"
                          asChild
                        >
                          <a
                            href={job.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            View posting
                            <ExternalLink className="ml-1 size-3.5" />
                          </a>
                        </Button>
                      </CardContent>
                    </Card>
                  );
                })}

                {hiddenCount > 0 && !showAll ? (
                  <button
                    type="button"
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => setShowAll(true)}
                  >
                    <ChevronDown className="size-3.5" />
                    Show all {tile.allJobs.length} jobs ({hiddenCount} hidden by
                    relevance filter)
                  </button>
                ) : null}

                {tile.jobs.length === 0 && hiddenCount === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    {tile.status === "scanning" || isChecking
                      ? "Scanning for open positions…"
                      : "No open positions found yet."}
                  </p>
                ) : null}
              </div>
            </details>
          );
        })
      )}

      <Sheet
        open={selectedPersonId !== null}
        onOpenChange={handleDetailSheetOpenChange}
      >
        <SheetContent className="flex w-full flex-col p-0 sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>
              {personDetailQuery.data?.display_name ?? "Contact"}
            </SheetTitle>
            <SheetDescription>
              {personDetailQuery.data?.current_role ??
                personDetailQuery.data?.org_name ??
                "Contact details"}
            </SheetDescription>
          </SheetHeader>
          {personDetailQuery.isLoading ? (
            <div className="space-y-3 px-6 py-4">
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : personDetailQuery.data ? (
            <PersonDetailPanel
              ref={detailPanelRef}
              key={`${selectedPersonId}-${personDetailQuery.dataUpdatedAt}`}
              person={personDetailQuery.data}
              onDirtyChange={setIsDetailDirty}
            />
          ) : personDetailQuery.error ? (
            <div className="px-6 py-4">
              <Alert variant="destructive">
                <AlertDescription>
                  {personDetailQuery.error.message}
                </AlertDescription>
              </Alert>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>

      <UnsavedChangesDialog
        open={discardDialogOpen}
        onOpenChange={setDiscardDialogOpen}
        onSave={handleSaveAndClose}
        onDiscard={closeDetailPanel}
        isSaving={isClosingSave}
      />

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

  return <JobsListings />;
}
