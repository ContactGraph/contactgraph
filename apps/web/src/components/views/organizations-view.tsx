"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import {
  ChevronDown,
  Download,
  MoreHorizontal,
  Pencil,
  Star,
  Users,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import {
  CompactCell,
  CompactSortHeader,
  CompactTableShell,
} from "@/components/data-table/compact-table";
import { OrgDetailPanel } from "@/components/org-detail-panel";
import { UnsavedChangesDialog } from "@/components/unsaved-changes-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SearchInput } from "@/components/ui/search-input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type {
  CreateOrgListResult,
  ListOrgListsResult,
  ListOrgsResult,
  ModifyOrgListMembershipResult,
  OrgDetailResult,
  OrgListItem,
  OrgListSummary,
} from "@/lib/api-types";
import type { EditableDetailPanelHandle } from "@/lib/editable-detail-panel";
import { formatCompanySize } from "@/lib/company-size";
import { buildCsv, csvFilename, downloadCsv } from "@/lib/csv-export";
import { formatIndustryTag, formatIndustryTags } from "@/lib/industry-tags";
import { proxyPost } from "@/lib/proxy-client";
import {
  findJobProspectsList,
  JOB_PROSPECTS_LIST_NAME,
} from "@/lib/setup-utils";
import { cn } from "@/lib/utils";

function websiteUrl(domain: string | null): string | null {
  if (!domain) {
    return null;
  }
  if (domain.startsWith("http://") || domain.startsWith("https://")) {
    return domain;
  }
  return `https://${domain}`;
}

function CompactLinkCell({
  href,
  label,
}: {
  href: string | null;
  label: string;
}) {
  if (!href) {
    return <CompactCell value="—" />;
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="block truncate text-primary underline-offset-2 hover:underline"
      title={href}
      onClick={(event) => event.stopPropagation()}
    >
      {label}
    </a>
  );
}

export function OrganizationsView({
  embedded = false,
  viewingFilter = "mine",
}: {
  embedded?: boolean;
  viewingFilter?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState<string>(searchParams.get("search") ?? "");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "name", desc: false },
  ]);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(
    searchParams.get("org") ?? null,
  );
  const [isDetailDirty, setIsDetailDirty] = useState<boolean>(false);
  const [discardDialogOpen, setDiscardDialogOpen] = useState<boolean>(false);
  const [isClosingSave, setIsClosingSave] = useState<boolean>(false);
  const [selectedCategories, setSelectedCategories] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [selectedSizeBands, setSelectedSizeBands] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const detailPanelRef = useRef<EditableDetailPanelHandle>(null);

  useEffect(() => {
    setIsDetailDirty(false);
  }, [selectedOrgId]);

  const closeDetailPanel = (): void => {
    setSelectedOrgId(null);
    setIsDetailDirty(false);
    setDiscardDialogOpen(false);
  };

  const handleDetailSheetOpenChange = (open: boolean): void => {
    if (open) {
      return;
    }
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
      if (saved) {
        closeDetailPanel();
      }
    } finally {
      setIsClosingSave(false);
    }
  };

  const orgsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () =>
      proxyPost<ListOrgsResult>("list-orgs", { include_shared: true }),
    staleTime: 0,
  });

  const orgListsQuery = useQuery({
    queryKey: ["org-lists"],
    queryFn: () => proxyPost<ListOrgListsResult>("list-org-lists"),
  });

  const detailQuery = useQuery({
    queryKey: ["organization", selectedOrgId],
    queryFn: () =>
      proxyPost<OrgDetailResult>("get-org", {
        org_id: selectedOrgId,
      }),
    enabled: selectedOrgId !== null,
  });

  const invalidateOrgLists = async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: ["org-lists"] });
  };

  const ensureJobProspectsListId = useCallback(async (): Promise<string> => {
    const existingList: OrgListSummary | undefined = findJobProspectsList(
      orgListsQuery.data?.lists ?? [],
    );
    if (existingList !== undefined) {
      return existingList.list_id;
    }
    const result: CreateOrgListResult = await proxyPost<CreateOrgListResult>(
      "create-org-list",
      { name: JOB_PROSPECTS_LIST_NAME },
    );
    await invalidateOrgLists();
    return result.list_id;
  }, [orgListsQuery.data?.lists, queryClient]);

  const applyOptimisticStarUpdate = useCallback(
    (orgIds: string[], action: "star" | "unstar"): ListOrgListsResult | undefined => {
      const previous: ListOrgListsResult | undefined =
        queryClient.getQueryData<ListOrgListsResult>(["org-lists"]);
      queryClient.setQueryData<ListOrgListsResult>(["org-lists"], (old) => {
        if (old === undefined) {
          return old;
        }
        return {
          ...old,
          lists: old.lists.map((list) => {
            if (list.name !== JOB_PROSPECTS_LIST_NAME) {
              return list;
            }
            const currentIds = new Set(list.org_ids);
            if (action === "star") {
              for (const id of orgIds) {
                currentIds.add(id);
              }
            } else {
              for (const id of orgIds) {
                currentIds.delete(id);
              }
            }
            return {
              ...list,
              org_ids: [...currentIds],
              org_count: currentIds.size,
            };
          }),
        };
      });
      return previous;
    },
    [queryClient],
  );

  const starToggleMutation = useMutation({
    mutationFn: async ({
      orgId,
      isStarred,
    }: {
      orgId: string;
      isStarred: boolean;
    }) => {
      if (isStarred) {
        const list: OrgListSummary | undefined = findJobProspectsList(
          orgListsQuery.data?.lists ?? [],
        );
        if (list === undefined) {
          return null;
        }
        return proxyPost<ModifyOrgListMembershipResult>("remove-orgs-from-list", {
          list_id: list.list_id,
          org_ids: [orgId],
        });
      }
      const listId: string = await ensureJobProspectsListId();
      return proxyPost<ModifyOrgListMembershipResult>("add-orgs-to-list", {
        list_id: listId,
        org_ids: [orgId],
      });
    },
    onMutate: async ({ orgId, isStarred }) => {
      await queryClient.cancelQueries({ queryKey: ["org-lists"] });
      const previous = applyOptimisticStarUpdate(
        [orgId],
        isStarred ? "unstar" : "star",
      );
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(["org-lists"], context.previous);
      }
      toast.error("Failed to update star");
    },
    onSettled: async () => {
      await invalidateOrgLists();
    },
  });

  const bulkStarMutation = useMutation({
    mutationFn: async ({
      orgIds,
      action,
    }: {
      orgIds: string[];
      action: "star" | "unstar";
    }) => {
      if (orgIds.length === 0) {
        return null;
      }
      if (action === "unstar") {
        const list: OrgListSummary | undefined = findJobProspectsList(
          orgListsQuery.data?.lists ?? [],
        );
        if (list === undefined) {
          return null;
        }
        return proxyPost<ModifyOrgListMembershipResult>("remove-orgs-from-list", {
          list_id: list.list_id,
          org_ids: orgIds,
        });
      }
      const listId: string = await ensureJobProspectsListId();
      return proxyPost<ModifyOrgListMembershipResult>("add-orgs-to-list", {
        list_id: listId,
        org_ids: orgIds,
      });
    },
    onMutate: async ({ orgIds, action }) => {
      await queryClient.cancelQueries({ queryKey: ["org-lists"] });
      const previous = applyOptimisticStarUpdate(orgIds, action);
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(["org-lists"], context.previous);
      }
      toast.error("Failed to update stars");
    },
    onSettled: async () => {
      await invalidateOrgLists();
    },
  });

  const allOrgs: OrgListItem[] = orgsQuery.data?.orgs ?? [];
  const orgLists: OrgListSummary[] = orgListsQuery.data?.lists ?? [];
  const jobProspectsList: OrgListSummary | undefined =
    findJobProspectsList(orgLists);
  const starredOrgIds: ReadonlySet<string> = useMemo(
    () => new Set(jobProspectsList?.org_ids ?? []),
    [jobProspectsList?.org_ids],
  );
  const starredCount: number = jobProspectsList?.org_count ?? 0;

  const availableCategories: string[] = useMemo(() => {
    const tags = new Set<string>();
    for (const org of allOrgs) {
      for (const tag of org.categories) {
        tags.add(tag);
      }
    }
    return [...tags].sort((left, right) =>
      formatIndustryTag(left).localeCompare(formatIndustryTag(right)),
    );
  }, [allOrgs]);

  const availableSizeBands: string[] = useMemo(() => {
    const bands = new Set<string>();
    for (const org of allOrgs) {
      if (org.company_size_band) {
        bands.add(org.company_size_band);
      }
    }
    return [...bands].sort();
  }, [allOrgs]);


  const filteredOrgs: OrgListItem[] = useMemo(() => {
    let rows: OrgListItem[] = allOrgs;

    // Filter by whose orgs we're viewing
    if (viewingFilter === "mine") {
      rows = rows.filter((org) => org.contact_count > 0);
    } else if (viewingFilter !== "all") {
      rows = rows.filter((org) =>
        org.shared_from.includes(viewingFilter),
      );
    }

    if (selectedCategories.size > 0) {
      rows = rows.filter((org) =>
        org.categories.some((tag) => selectedCategories.has(tag)),
      );
    }
    if (selectedSizeBands.size > 0) {
      rows = rows.filter(
        (org) =>
          org.company_size_band !== null &&
          selectedSizeBands.has(org.company_size_band),
      );
    }
    return rows;
  }, [allOrgs, viewingFilter, selectedCategories, selectedSizeBands]);

  const starAllRef = useRef<() => void>(() => {});
  const unstarAllRef = useRef<() => void>(() => {});

  const columns: ColumnDef<OrgListItem>[] = useMemo(() => {
    const baseColumns: ColumnDef<OrgListItem>[] = [];

    baseColumns.push(
      {
        accessorKey: "name",
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Organization" />
        ),
        cell: ({ row }) => <CompactCell value={row.original.name} />,
        meta: { width: "w-[8rem]" },
      },
      {
        id: "description",
        accessorFn: (row: OrgListItem) => row.description ?? "",
        header: "Description",
        cell: ({ row }) => (
          <CompactCell
            value={row.original.description ?? "—"}
            title={row.original.description ?? undefined}
          />
        ),
        meta: { width: "w-[12rem]" },
      },
      {
        id: "website",
        accessorFn: (row: OrgListItem) => row.primary_domain ?? "",
        header: "Website",
        cell: ({ row }) => (
          <CompactLinkCell
            href={websiteUrl(row.original.primary_domain)}
            label={row.original.primary_domain ?? "—"}
          />
        ),
        meta: { width: "w-[7rem]" },
      },
      {
        id: "jobs",
        accessorFn: (row: OrgListItem) => row.careers_url ?? "",
        header: "Jobs",
        cell: ({ row }) => (
          <CompactLinkCell href={row.original.careers_url} label="Careers" />
        ),
        meta: { width: "w-[4.5rem]" },
      },
      {
        id: "size",
        accessorFn: (row: OrgListItem) =>
          formatCompanySize(row.company_size_band, row.employee_count),
        header: "Size",
        cell: ({ row }) => (
          <CompactCell
            value={formatCompanySize(
              row.original.company_size_band,
              row.original.employee_count,
            )}
          />
        ),
        meta: { width: "w-[7rem]" },
      },
      {
        id: "categories",
        accessorFn: (row: OrgListItem) => formatIndustryTags(row.categories),
        header: "Categories",
        cell: ({ row }) => (
          <CompactCell value={formatIndustryTags(row.original.categories)} />
        ),
        meta: { width: "w-[6.5rem]" },
      },
      {
        accessorKey: "contact_count",
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Contacts" />
        ),
        cell: ({ row }) => {
          const own: number = row.original.contact_count;
          const shared: number = row.original.shared_contact_count;
          if (shared > 0) {
            return (
              <span className="text-xs">
                {own > 0 ? `${own} + ` : ""}
                <span className="text-muted-foreground">{shared} shared</span>
              </span>
            );
          }
          return <CompactCell value={own.toString()} />;
        },
        meta: { width: "w-[5.5rem]" },
      },
      {
        id: "shared_by",
        accessorFn: (row: OrgListItem) => row.shared_from.join(", "),
        header: "Shared by",
        cell: ({ row }) => {
          const sharers: string[] = row.original.shared_from;
          if (sharers.length === 0) return <CompactCell value="—" />;
          return (
            <span className="text-xs text-muted-foreground">
              {sharers.map((name) => `via ${name}`).join(", ")}
            </span>
          );
        },
        meta: { width: "w-[5.5rem]" },
      },
      {
        id: "star",
        header: () => (
          <div className="flex flex-col items-center gap-0.5">
            <span className="text-[10px] font-medium leading-none">Job Prospect</span>
            <span className="flex gap-1 text-[10px] leading-none text-muted-foreground">
              Select
              <button
                type="button"
                className="underline underline-offset-2 hover:text-foreground"
                onClick={() => starAllRef.current()}
              >
                All
              </button>
              <span className="opacity-50">|</span>
              <button
                type="button"
                className="underline underline-offset-2 hover:text-foreground"
                onClick={() => unstarAllRef.current()}
              >
                None
              </button>
            </span>
          </div>
        ),
        cell: ({ row }) => {
          const isStarred: boolean = starredOrgIds.has(row.original.org_id);
          return (
            <Button
              variant="ghost"
              size="icon"
              className="size-6 shrink-0"
              disabled={starToggleMutation.isPending}
              onClick={(event) => {
                event.stopPropagation();
                starToggleMutation.mutate({
                  orgId: row.original.org_id,
                  isStarred,
                });
              }}
              aria-label={
                isStarred
                  ? `Remove ${row.original.name} from job prospects`
                  : `Add ${row.original.name} to job prospects`
              }
            >
              <Star
                className={cn(
                  "size-3.5",
                  isStarred && "fill-amber-400 text-amber-400",
                )}
              />
            </Button>
          );
        },
        enableSorting: false,
        meta: { width: "w-[5rem]" },
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6 shrink-0"
                  onClick={(event) => event.stopPropagation()}
                >
                  <MoreHorizontal className="size-3.5" />
                  <span className="sr-only">Open menu</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel>Actions</DropdownMenuLabel>
                <DropdownMenuItem
                  onClick={(event) => {
                    event.stopPropagation();
                    setSelectedOrgId(row.original.org_id);
                  }}
                >
                  <Pencil className="mr-2 size-4" />
                  Edit
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={(event) => {
                    event.stopPropagation();
                    router.push(
                      `/graph?tab=people&search=${encodeURIComponent(row.original.name)}`,
                    );
                  }}
                >
                  <Users className="mr-2 size-4" />
                  View contacts
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
        meta: { width: "w-[2rem]", stickyRight: true },
      },
    );

    return baseColumns;
  }, [router, starredOrgIds, starToggleMutation]);

  const table = useReactTable({
    data: filteredOrgs,
    columns,
    state: { sorting, globalFilter: search },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    getRowId: (row) => row.org_id,
    globalFilterFn: (row, _columnId, filterValue: string) => {
      const query: string = filterValue.trim().toLowerCase();
      if (!query) {
        return true;
      }
      const org: OrgListItem = row.original;
      const haystack: string = [
        org.name,
        org.primary_domain,
        org.description,
        org.categories.map((tag) => formatIndustryTags([tag])).join(" "),
        ...org.shared_from.map((name) => `via ${name}`),
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

  const getMatchingOrgIds = useCallback((): string[] => {
    return table
      .getFilteredRowModel()
      .rows.map((row) => row.original.org_id);
  }, [table]);

  const handleStarAllMatching = useCallback((): void => {
    const orgIdsToStar: string[] = getMatchingOrgIds().filter(
      (orgId) => !starredOrgIds.has(orgId),
    );
    bulkStarMutation.mutate({ orgIds: orgIdsToStar, action: "star" });
  }, [bulkStarMutation, getMatchingOrgIds, starredOrgIds]);

  const handleUnstarAllMatching = useCallback((): void => {
    const orgIdsToUnstar: string[] = getMatchingOrgIds().filter((orgId) =>
      starredOrgIds.has(orgId),
    );
    bulkStarMutation.mutate({ orgIds: orgIdsToUnstar, action: "unstar" });
  }, [bulkStarMutation, getMatchingOrgIds, starredOrgIds]);

  starAllRef.current = handleStarAllMatching;
  unstarAllRef.current = handleUnstarAllMatching;

  const selectedOrg: OrgListItem | undefined = allOrgs.find(
    (org: OrgListItem) => org.org_id === selectedOrgId,
  );

  const handleDownloadCsv = (): void => {
    const rows: OrgListItem[] = table
      .getSortedRowModel()
      .rows.map((row) => row.original);
    const csv: string = buildCsv(
      [
        "Organization",
        "Description",
        "Website",
        "Jobs",
        "Size",
        "Categories",
        "Contacts",
      ],
      rows.map((org: OrgListItem) => [
        org.name,
        org.description ?? "",
        org.primary_domain ?? "",
        org.careers_url ?? "",
        formatCompanySize(org.company_size_band, org.employee_count),
        formatIndustryTags(org.categories),
        org.contact_count.toString(),
      ]),
    );
    downloadCsv(csvFilename("organizations"), csv);
  };

  const toggleCategory = (tag: string): void => {
    setSelectedCategories((current) => {
      const next = new Set(current);
      if (next.has(tag)) {
        next.delete(tag);
      } else {
        next.add(tag);
      }
      return next;
    });
  };

  const toggleSizeBand = (band: string): void => {
    setSelectedSizeBands((current) => {
      const next = new Set(current);
      if (next.has(band)) {
        next.delete(band);
      } else {
        next.add(band);
      }
      return next;
    });
  };


  const starMutationPending: boolean =
    starToggleMutation.isPending || bulkStarMutation.isPending;

  const hasActiveFilters: boolean =
    selectedCategories.size > 0 || selectedSizeBands.size > 0;

  return (
    <div className="space-y-2">
      {!embedded ? (
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Organizations</h1>
          <p className="text-xs text-muted-foreground">
            {orgsQuery.isLoading
              ? "Loading…"
              : `${table.getFilteredRowModel().rows.length} of ${allOrgs.length} shown`}
          </p>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {orgsQuery.isLoading
            ? "Loading…"
            : `${table.getFilteredRowModel().rows.length} of ${allOrgs.length} shown`}
        </p>
      )}

      {orgsQuery.error ? (
        <Alert variant="destructive">
          <AlertDescription>{orgsQuery.error.message}</AlertDescription>
        </Alert>
      ) : null}

      {/* Toolbar: search, filters, select, actions — single row */}
      <div className="flex flex-wrap items-center gap-2">
        <SearchInput
          containerClassName="w-48"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search…"
        />

        {/* Category filter */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="h-8 text-xs">
              Category
              {selectedCategories.size > 0 ? (
                <Badge variant="secondary" className="ml-1">
                  {selectedCategories.size}
                </Badge>
              ) : null}
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="max-h-72 overflow-y-auto">
            {availableCategories.length === 0 ? (
              <DropdownMenuItem disabled>No categories</DropdownMenuItem>
            ) : (
              availableCategories.map((tag) => (
                <DropdownMenuCheckboxItem
                  key={tag}
                  checked={selectedCategories.has(tag)}
                  onCheckedChange={() => toggleCategory(tag)}
                >
                  {formatIndustryTag(tag)}
                </DropdownMenuCheckboxItem>
              ))
            )}
            {selectedCategories.size > 0 ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setSelectedCategories(new Set())}>
                  Clear
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Size filter */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="h-8 text-xs">
              Size
              {selectedSizeBands.size > 0 ? (
                <Badge variant="secondary" className="ml-1">
                  {selectedSizeBands.size}
                </Badge>
              ) : null}
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="max-h-72 overflow-y-auto">
            {availableSizeBands.length === 0 ? (
              <DropdownMenuItem disabled>No size data</DropdownMenuItem>
            ) : (
              availableSizeBands.map((band) => (
                <DropdownMenuCheckboxItem
                  key={band}
                  checked={selectedSizeBands.has(band)}
                  onCheckedChange={() => toggleSizeBand(band)}
                >
                  {formatCompanySize(band, null)}
                </DropdownMenuCheckboxItem>
              ))
            )}
            {selectedSizeBands.size > 0 ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setSelectedSizeBands(new Set())}>
                  Clear
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>

        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 text-xs"
            onClick={() => {
              setSelectedCategories(new Set());
              setSelectedSizeBands(new Set());
            }}
          >
            Clear filters
          </Button>
        )}

        <span className="text-xs text-muted-foreground">
          {starredCount} of {allOrgs.length} starred for jobs
        </span>

        <div className="ml-auto flex items-center gap-2">
          {/* CSV export */}
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={handleDownloadCsv}
            disabled={orgsQuery.isLoading || table.getRowModel().rows.length === 0}
          >
            <Download className="size-3.5" />
            CSV
          </Button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-md border bg-card">
        {orgsQuery.isLoading ? (
          <div className="space-y-1.5 p-2">
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
          </div>
        ) : (
          <CompactTableShell
            table={table}
            columnCount={columns.length}
            emptyMessage="No organizations match your filters."
            minWidth="50rem"
            onRowClick={(org: OrgListItem) => {
              setSelectedOrgId(org.org_id);
            }}
          />
        )}
      </div>

      {/* Org detail sheet */}
      <Sheet
        open={selectedOrgId !== null}
        onOpenChange={handleDetailSheetOpenChange}
      >
        <SheetContent className="flex w-full flex-col p-0 sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>{selectedOrg?.name ?? "Organization"}</SheetTitle>
            <SheetDescription>
              {selectedOrg?.description ??
                selectedOrg?.primary_domain ??
                "Organization details"}
            </SheetDescription>
          </SheetHeader>
          {detailQuery.isLoading ? (
            <div className="space-y-3 px-6 py-4">
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : detailQuery.data ? (
            <OrgDetailPanel
              ref={detailPanelRef}
              key={`${selectedOrgId}-${detailQuery.dataUpdatedAt}`}
              org={detailQuery.data}
              onDirtyChange={setIsDetailDirty}
            />
          ) : detailQuery.error ? (
            <div className="px-6 py-4">
              <Alert variant="destructive">
                <AlertDescription>{detailQuery.error.message}</AlertDescription>
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
    </div>
  );
}
