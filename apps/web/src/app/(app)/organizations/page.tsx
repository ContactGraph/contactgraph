"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
  type SortingState,
} from "@tanstack/react-table";
import {
  CheckSquare,
  ChevronDown,
  Download,
  ListPlus,
  ListX,
  MoreHorizontal,
  Pencil,
  Search,
  Square,
  Trash2,
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
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

function SelectionCheckbox({
  checked,
  indeterminate,
  onChange,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: (checked: boolean) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.indeterminate = indeterminate === true;
    }
  }, [indeterminate]);

  return (
    <input
      ref={inputRef}
      type="checkbox"
      className="size-3.5 accent-primary"
      checked={checked}
      onChange={(event) => onChange(event.target.checked)}
      onClick={(event) => event.stopPropagation()}
    />
  );
}

export default function OrganizationsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState<string>("");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "name", desc: false },
  ]);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [isDetailDirty, setIsDetailDirty] = useState<boolean>(false);
  const [discardDialogOpen, setDiscardDialogOpen] = useState<boolean>(false);
  const [isClosingSave, setIsClosingSave] = useState<boolean>(false);
  const [selectMode, setSelectMode] = useState<boolean>(false);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [selectedCategories, setSelectedCategories] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [selectedSizeBands, setSelectedSizeBands] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [activeListId, setActiveListId] = useState<string | null>(null);
  const [newListName, setNewListName] = useState<string>("");
  const detailPanelRef = useRef<EditableDetailPanelHandle>(null);
  const appliedListFromUrl = useRef<boolean>(false);

  useEffect(() => {
    setIsDetailDirty(false);
  }, [selectedOrgId]);

  useEffect(() => {
    if (!selectMode) {
      setRowSelection({});
    }
  }, [selectMode]);

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
    queryFn: () => proxyPost<ListOrgsResult>("list-orgs"),
    staleTime: 0,
  });

  const orgListsQuery = useQuery({
    queryKey: ["org-lists"],
    queryFn: () => proxyPost<ListOrgListsResult>("list-org-lists"),
  });

  useEffect(() => {
    if (appliedListFromUrl.current) {
      return;
    }
    const listParam: string | null = searchParams.get("list");
    if (listParam === null) {
      appliedListFromUrl.current = true;
      return;
    }
    if (orgListsQuery.isLoading) {
      return;
    }
    const listExists: boolean = (orgListsQuery.data?.lists ?? []).some(
      (list) => list.list_id === listParam,
    );
    if (listExists) {
      setActiveListId(listParam);
    }
    appliedListFromUrl.current = true;
  }, [searchParams, orgListsQuery.isLoading, orgListsQuery.data?.lists]);

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

  const createListMutation = useMutation({
    mutationFn: (name: string) =>
      proxyPost<CreateOrgListResult>("create-org-list", { name }),
    onSuccess: async (result: CreateOrgListResult) => {
      toast.success(result.message);
      setNewListName("");
      await invalidateOrgLists();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const renameListMutation = useMutation({
    mutationFn: ({ listId, name }: { listId: string; name: string }) =>
      proxyPost("rename-org-list", { list_id: listId, name }),
    onSuccess: async () => {
      await invalidateOrgLists();
    },
  });

  const deleteListMutation = useMutation({
    mutationFn: (listId: string) =>
      proxyPost("delete-org-list", { list_id: listId }),
    onSuccess: async (_result, listId) => {
      if (activeListId === listId) {
        setActiveListId(null);
      }
      await invalidateOrgLists();
    },
  });

  const addToListMutation = useMutation({
    mutationFn: ({ listId, orgIds }: { listId: string; orgIds: string[] }) =>
      proxyPost<ModifyOrgListMembershipResult>("add-orgs-to-list", {
        list_id: listId,
        org_ids: orgIds,
      }),
    onSuccess: async (result: ModifyOrgListMembershipResult) => {
      toast.success(result.message);
      setRowSelection({});
      await invalidateOrgLists();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const removeFromListMutation = useMutation({
    mutationFn: ({ listId, orgIds }: { listId: string; orgIds: string[] }) =>
      proxyPost<ModifyOrgListMembershipResult>("remove-orgs-from-list", {
        list_id: listId,
        org_ids: orgIds,
      }),
    onSuccess: async (result: ModifyOrgListMembershipResult) => {
      toast.success(result.message);
      setRowSelection({});
      await invalidateOrgLists();
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const allOrgs: OrgListItem[] = orgsQuery.data?.orgs ?? [];
  const orgLists: OrgListSummary[] = orgListsQuery.data?.lists ?? [];

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

  const activeListOrgIds: ReadonlySet<string> = useMemo(() => {
    if (activeListId === null) {
      return new Set();
    }
    const activeList: OrgListSummary | undefined = orgLists.find(
      (entry) => entry.list_id === activeListId,
    );
    return new Set(activeList?.org_ids ?? []);
  }, [activeListId, orgLists]);

  const filteredOrgs: OrgListItem[] = useMemo(() => {
    let rows: OrgListItem[] = allOrgs;
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
    if (activeListId !== null) {
      rows = rows.filter((org) => activeListOrgIds.has(org.org_id));
    }
    return rows;
  }, [
    activeListId,
    activeListOrgIds,
    allOrgs,
    selectedCategories,
    selectedSizeBands,
  ]);

  const selectedOrgIds: string[] = useMemo(
    () => Object.keys(rowSelection).filter((orgId) => rowSelection[orgId]),
    [rowSelection],
  );

  const columns: ColumnDef<OrgListItem>[] = useMemo(() => {
    const baseColumns: ColumnDef<OrgListItem>[] = [];

    if (selectMode) {
      baseColumns.push({
        id: "select",
        header: ({ table }) => (
          <SelectionCheckbox
            checked={table.getIsAllPageRowsSelected()}
            indeterminate={table.getIsSomePageRowsSelected()}
            onChange={(checked) =>
              table.toggleAllPageRowsSelected(checked)
            }
          />
        ),
        cell: ({ row }) => (
          <SelectionCheckbox
            checked={row.getIsSelected()}
            onChange={(checked) => row.toggleSelected(checked)}
          />
        ),
        enableSorting: false,
        meta: { width: "w-[2rem]" },
      });
    }

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
          <CompactSortHeader column={column} label="#" />
        ),
        cell: ({ row }) => (
          <CompactCell value={row.original.contact_count.toString()} />
        ),
        meta: { width: "w-[2.5rem]" },
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
                      `/people?search=${encodeURIComponent(row.original.name)}`,
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
  }, [router, selectMode]);

  const table = useReactTable({
    data: filteredOrgs,
    columns,
    state: { sorting, globalFilter: search, rowSelection },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    onRowSelectionChange: setRowSelection,
    enableRowSelection: selectMode,
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

  const handleCreateList = (): void => {
    const trimmed: string = newListName.trim();
    if (!trimmed) {
      return;
    }
    createListMutation.mutate(trimmed);
  };

  const handleRenameList = (list: OrgListSummary): void => {
    const nextName: string | null = window.prompt(
      "Rename list",
      list.name,
    );
    if (nextName === null) {
      return;
    }
    const trimmed: string = nextName.trim();
    if (!trimmed || trimmed === list.name) {
      return;
    }
    renameListMutation.mutate({ listId: list.list_id, name: trimmed });
  };

  const [listsDialogOpen, setListsDialogOpen] = useState<boolean>(false);

  const listMutationPending: boolean =
    createListMutation.isPending ||
    addToListMutation.isPending ||
    removeFromListMutation.isPending;

  const hasActiveFilters: boolean =
    selectedCategories.size > 0 || selectedSizeBands.size > 0;

  return (
    <div className="space-y-2">
      {/* Header: title + list selector dropdown */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Organizations</h1>
          <p className="text-xs text-muted-foreground">
            {orgsQuery.isLoading
              ? "Loading…"
              : `${table.getFilteredRowModel().rows.length} of ${allOrgs.length} shown`}
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="h-8 text-xs">
              {activeListId !== null
                ? orgLists.find((entry) => entry.list_id === activeListId)?.name ?? "List"
                : "All organizations"}
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setListsDialogOpen(true)}>
              <Pencil className="mr-2 size-3.5" />
              Manage lists…
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuCheckboxItem
              checked={activeListId === null}
              onCheckedChange={() => setActiveListId(null)}
            >
              All organizations
            </DropdownMenuCheckboxItem>
            {orgLists.map((list) => (
              <DropdownMenuCheckboxItem
                key={list.list_id}
                checked={activeListId === list.list_id}
                onCheckedChange={() =>
                  setActiveListId(
                    activeListId === list.list_id ? null : list.list_id,
                  )
                }
              >
                {list.name} ({list.org_count})
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {orgsQuery.error ? (
        <Alert variant="destructive">
          <AlertDescription>{orgsQuery.error.message}</AlertDescription>
        </Alert>
      ) : null}

      {/* Toolbar: search, filters, select, actions — single row */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-48">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search…"
            className="h-8 pl-8 text-xs"
          />
        </div>

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

        <div className="ml-auto flex items-center gap-2">
          {/* Select mode toggle */}
          <Button
            variant={selectMode ? "default" : "outline"}
            size="sm"
            className="h-8 text-xs"
            onClick={() => setSelectMode((current) => !current)}
          >
            {selectMode ? <CheckSquare className="size-3.5" /> : <Square className="size-3.5" />}
            Select
          </Button>

          {/* Selection actions (inline when items selected) */}
          {selectMode && selectedOrgIds.length > 0 ? (
            <>
              <span className="text-xs text-muted-foreground">
                {selectedOrgIds.length} selected
              </span>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    size="sm"
                    className="h-8 text-xs"
                    disabled={listMutationPending}
                  >
                    <ListPlus className="size-3.5" />
                    Add to…
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {orgLists.length === 0 ? (
                    <DropdownMenuItem disabled>
                      No lists yet — create one first
                    </DropdownMenuItem>
                  ) : (
                    orgLists.map((list) => (
                      <DropdownMenuItem
                        key={list.list_id}
                        onClick={() =>
                          addToListMutation.mutate({
                            listId: list.list_id,
                            orgIds: selectedOrgIds,
                          })
                        }
                      >
                        {list.name}
                      </DropdownMenuItem>
                    ))
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
              {activeListId !== null ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-xs"
                  disabled={listMutationPending}
                  onClick={() =>
                    removeFromListMutation.mutate({
                      listId: activeListId,
                      orgIds: selectedOrgIds,
                    })
                  }
                >
                  <ListX className="size-3.5" />
                  Remove
                </Button>
              ) : null}
            </>
          ) : null}

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
            minWidth={selectMode ? "50rem" : "48rem"}
            onRowClick={(org: OrgListItem) => {
              if (selectMode) {
                setRowSelection((current) => {
                  const next: RowSelectionState = { ...current };
                  if (next[org.org_id]) {
                    delete next[org.org_id];
                  } else {
                    next[org.org_id] = true;
                  }
                  return next;
                });
                return;
              }
              setSelectedOrgId(org.org_id);
            }}
          />
        )}
      </div>

      {/* Manage Lists dialog */}
      <Dialog open={listsDialogOpen} onOpenChange={setListsDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Organization lists</DialogTitle>
            <DialogDescription>
              Create named lists to organize companies of interest.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            {orgLists.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No lists yet. Create one below.
              </p>
            ) : (
              <ul className="divide-y">
                {orgLists.map((list) => (
                  <li
                    key={list.list_id}
                    className="flex items-center justify-between py-2"
                  >
                    <div>
                      <p className="text-sm font-medium">{list.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {list.org_count} organization(s)
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => handleRenameList(list)}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-destructive hover:text-destructive"
                        onClick={() => deleteListMutation.mutate(list.list_id)}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex items-center gap-2">
              <Input
                value={newListName}
                onChange={(event) => setNewListName(event.target.value)}
                placeholder="New list name…"
                className="h-8 flex-1 text-xs"
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    handleCreateList();
                  }
                }}
              />
              <Button
                size="sm"
                className="h-8 text-xs"
                onClick={handleCreateList}
                disabled={
                  createListMutation.isPending || newListName.trim().length === 0
                }
              >
                Create
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

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
