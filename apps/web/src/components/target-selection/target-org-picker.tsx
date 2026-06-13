"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Star, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
  CompactCell,
  CompactSortHeader,
  CompactTableShell,
} from "@/components/data-table/compact-table";
import { OrgLogo } from "@/components/org-logo";
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
import type { ListOrgsResult, OrgListItem } from "@/lib/api-types";
import { formatIndustryTags } from "@/lib/industry-tags";
import { proxyPost } from "@/lib/proxy-client";
import { cn } from "@/lib/utils";
import {
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";

import {
  filterOrgsByScope,
  orgMatchesSearch,
} from "./filter-orgs-by-scope";
import { TargetScopePanel } from "./target-scope-panel";
import type { TargetSelectionConfig } from "./target-selection-config";
import {
  defaultTargetScope,
  targetScopeToPayload,
  type TargetScope,
} from "./types";
import { useOrgListMembership } from "./use-org-list-membership";

export interface TargetOrgPickerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  config: TargetSelectionConfig;
  scope: TargetScope;
  onScopeChange: (scope: TargetScope) => void;
  onScopePersist?: (scope: TargetScope) => Promise<void>;
}

export function TargetOrgPicker({
  open,
  onOpenChange,
  config,
  scope,
  onScopeChange,
  onScopePersist,
}: TargetOrgPickerProps) {
  const [search, setSearch] = useState<string>("");
  const [scopeExpanded, setScopeExpanded] = useState<boolean>(true);
  const [sorting, setSorting] = useState<SortingState>([
    { id: "name", desc: false },
  ]);

  const orgsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () =>
      proxyPost<ListOrgsResult>("list-orgs", { include_shared: true }),
    staleTime: 0,
    enabled: open,
  });

  const {
    selectedOrgIds,
    selectedCount,
    isPending,
    toggleOrg,
    bulkUpdate,
    bulkUpdateAsync,
    replaceSelection,
  } = useOrgListMembership(config.listName);

  const allOrgs: OrgListItem[] = orgsQuery.data?.orgs ?? [];

  const scopedOrgs: OrgListItem[] = useMemo(
    () => filterOrgsByScope(allOrgs, scope),
    [allOrgs, scope],
  );

  const selectedOrgs: OrgListItem[] = useMemo(() => {
    const byId = new Map(allOrgs.map((org) => [org.org_id, org]));
    return [...selectedOrgIds]
      .map((orgId) => byId.get(orgId))
      .filter((org): org is OrgListItem => org !== undefined)
      .sort((left, right) => left.name.localeCompare(right.name));
  }, [allOrgs, selectedOrgIds]);

  const applyMatchingMutation = useMutation({
    mutationFn: async (mode: "add" | "replace") => {
      const orgIds: string[] = scopedOrgs.map((org) => org.org_id);
      if (mode === "replace") {
        await replaceSelection(orgIds);
        return orgIds.length;
      }
      const toAdd: string[] = orgIds.filter((id) => !selectedOrgIds.has(id));
      if (toAdd.length > 0) {
        await bulkUpdateAsync(toAdd, "add");
      }
      return toAdd.length;
    },
    onSuccess: (addedCount: number, mode: "add" | "replace") => {
      if (mode === "replace") {
        toast.success(
          `Updated list to ${scopedOrgs.length.toLocaleString()} matching companies`,
        );
        return;
      }
      if (addedCount === 0) {
        toast.message("All matching companies are already selected");
        return;
      }
      toast.success(
        `Added ${addedCount.toLocaleString()} companies — remove any you don't want below`,
      );
    },
    onError: () => {
      toast.error("Failed to update company list");
    },
  });

  const handleScopeChange = (nextScope: TargetScope): void => {
    onScopeChange(nextScope);
    void onScopePersist?.(nextScope);
  };

  const selectAllRef = useRef<() => void>(() => {});
  const clearAllRef = useRef<() => void>(() => {});

  const columns: ColumnDef<OrgListItem>[] = useMemo(
    () => [
      {
        accessorKey: "name",
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Organization" />
        ),
        cell: ({ row }) => (
          <div className="flex items-center gap-1.5 truncate">
            <OrgLogo
              domain={row.original.primary_domain}
              name={row.original.name}
              size={16}
            />
            <CompactCell value={row.original.name} />
          </div>
        ),
        meta: { width: "w-[10rem]" },
      },
      {
        id: "categories",
        accessorFn: (row: OrgListItem) => formatIndustryTags(row.categories),
        header: "Category",
        cell: ({ row }) => (
          <CompactCell value={formatIndustryTags(row.original.categories)} />
        ),
        meta: { width: "w-[8rem]" },
      },
      {
        id: "contacts",
        accessorFn: (row: OrgListItem) => row.contact_count,
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
        meta: { width: "w-[5rem]" },
      },
      {
        id: "shared_by",
        accessorFn: (row: OrgListItem) => row.shared_from.join(", "),
        header: "Shared by",
        cell: ({ row }) => {
          const sharers: string[] = row.original.shared_from;
          if (sharers.length === 0) {
            return <CompactCell value="—" />;
          }
          return (
            <span className="text-xs text-muted-foreground">
              {sharers.map((name) => `via ${name}`).join(", ")}
            </span>
          );
        },
        meta: { width: "w-[6rem]" },
      },
      {
        id: "selected",
        header: () => (
          <div className="flex flex-col items-center gap-0.5">
            <span className="text-[10px] font-medium leading-none">Selected</span>
            <span className="flex gap-1 text-[10px] leading-none text-muted-foreground">
              <button
                type="button"
                className="underline underline-offset-2 hover:text-foreground"
                onClick={() => selectAllRef.current()}
              >
                All
              </button>
              <span className="opacity-50">|</span>
              <button
                type="button"
                className="underline underline-offset-2 hover:text-foreground"
                onClick={() => clearAllRef.current()}
              >
                None
              </button>
            </span>
          </div>
        ),
        cell: ({ row }) => {
          const isSelected: boolean = selectedOrgIds.has(row.original.org_id);
          return (
            <Button
              variant="ghost"
              size="icon"
              className="size-6 shrink-0"
              disabled={isPending}
              onClick={(event) => {
                event.stopPropagation();
                toggleOrg(row.original.org_id, isSelected);
              }}
              aria-label={
                isSelected
                  ? `Remove ${row.original.name}`
                  : `Add ${row.original.name}`
              }
            >
              <Star
                className={cn(
                  "size-3.5",
                  isSelected && "fill-amber-400 text-amber-400",
                )}
              />
            </Button>
          );
        },
        enableSorting: false,
        meta: { width: "w-[4rem]" },
      },
    ],
    [bulkUpdate, isPending, selectedOrgIds, toggleOrg],
  );

  const table = useReactTable({
    data: scopedOrgs,
    columns,
    state: { sorting, globalFilter: search },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    getRowId: (row) => row.org_id,
    globalFilterFn: (row, _columnId, filterValue: string) =>
      orgMatchesSearch(row.original, filterValue),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  selectAllRef.current = (): void => {
    const orgIdsToAdd: string[] = table
      .getFilteredRowModel()
      .rows.map((row) => row.original.org_id)
      .filter((orgId) => !selectedOrgIds.has(orgId));
    bulkUpdate(orgIdsToAdd, "add");
  };

  clearAllRef.current = (): void => {
    const orgIdsToRemove: string[] = table
      .getFilteredRowModel()
      .rows.map((row) => row.original.org_id)
      .filter((orgId) => selectedOrgIds.has(orgId));
    bulkUpdate(orgIdsToRemove, "remove");
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-0 p-0 sm:max-w-3xl">
        <SheetHeader className="border-b px-4 py-3">
          <SheetTitle>{config.title}</SheetTitle>
          <SheetDescription>{config.description}</SheetDescription>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
          {selectedCount > 0 ? (
            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">
                {selectedCount.toLocaleString()} selected
              </p>
              <div className="flex flex-wrap gap-1.5">
                {selectedOrgs.slice(0, 12).map((org) => (
                  <span
                    key={org.org_id}
                    className="inline-flex items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-xs"
                  >
                    <OrgLogo
                      domain={org.primary_domain}
                      name={org.name}
                      size={14}
                    />
                    <span className="max-w-[8rem] truncate">{org.name}</span>
                    <button
                      type="button"
                      className="rounded-full p-0.5 hover:bg-muted"
                      aria-label={`Remove ${org.name}`}
                      onClick={() => toggleOrg(org.org_id, true)}
                    >
                      <X className="size-3" />
                    </button>
                  </span>
                ))}
                {selectedOrgs.length > 12 ? (
                  <span className="self-center text-xs text-muted-foreground">
                    +{(selectedOrgs.length - 12).toLocaleString()} more
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}

          <TargetScopePanel
            scope={scope}
            onScopeChange={handleScopeChange}
            allOrgs={allOrgs}
            selectedCount={selectedCount}
            onApplyMatching={(mode) => applyMatchingMutation.mutate(mode)}
            applyPending={applyMatchingMutation.isPending || isPending}
            collapsed={selectedCount > 0 && !scopeExpanded}
            onToggleCollapsed={() => setScopeExpanded((current) => !current)}
          />

          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search companies…"
                className="h-8 w-48"
              />
              <span className="text-xs text-muted-foreground">
                {table.getFilteredRowModel().rows.length.toLocaleString()} shown
              </span>
            </div>

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
                  emptyMessage="No companies match your filters."
                  minWidth="40rem"
                />
              )}
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            <Link
              href={config.graphLinkHref}
              className="underline underline-offset-2 hover:text-foreground"
            >
              {config.graphLinkLabel}
            </Link>
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function useTargetOrgPickerScope(
  initialScope: TargetScope = defaultTargetScope(),
): {
  scope: TargetScope;
  setScope: (scope: TargetScope) => void;
  scopePayload: ReturnType<typeof targetScopeToPayload>;
} {
  const [scope, setScope] = useState<TargetScope>(initialScope);
  return {
    scope,
    setScope,
    scopePayload: targetScopeToPayload(scope),
  };
}
