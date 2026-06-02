"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { Search } from "lucide-react";

import {
  CompactCell,
  CompactSortHeader,
  CompactTableShell,
} from "@/components/data-table/compact-table";
import { EntityActionsMenu } from "@/components/entity-actions-menu";
import { OrgDetailPanel } from "@/components/org-detail-panel";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { ListOrgsResult, OrgDetailResult, OrgListItem } from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";

export default function OrganizationsPage() {
  const [search, setSearch] = useState<string>("");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "name", desc: false },
  ]);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);

  const orgsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () => proxyPost<ListOrgsResult>("list-orgs"),
  });

  const detailQuery = useQuery({
    queryKey: ["organization", selectedOrgId],
    queryFn: () =>
      proxyPost<OrgDetailResult>("get-org", {
        org_id: selectedOrgId,
      }),
    enabled: selectedOrgId !== null,
  });

  const columns: ColumnDef<OrgListItem>[] = useMemo(
    () => [
      {
        accessorKey: "name",
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Organization" />
        ),
        cell: ({ row }) => <CompactCell value={row.original.name} />,
        meta: { width: "w-[8rem]" },
      },
      {
        accessorKey: "primary_domain",
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Domain" />
        ),
        cell: ({ row }) => (
          <CompactCell value={row.original.primary_domain ?? "—"} />
        ),
        meta: { width: "w-[6rem]" },
      },
      {
        id: "categories",
        accessorFn: (row: OrgListItem) => row.categories.join(", "),
        header: "Categories",
        cell: ({ row }) => (
          <CompactCell
            value={row.original.categories.join(", ") || "—"}
            title={row.original.categories.join(", ")}
          />
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
            <EntityActionsMenu entityLabel={row.original.name} />
          </div>
        ),
        meta: { width: "w-[2rem]", stickyRight: true },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: orgsQuery.data?.orgs ?? [],
    columns,
    state: { sorting, globalFilter: search },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    globalFilterFn: (row, _columnId, filterValue: string) => {
      const query: string = filterValue.trim().toLowerCase();
      if (!query) {
        return true;
      }
      const org: OrgListItem = row.original;
      const haystack: string = [
        org.name,
        org.primary_domain,
        org.categories.join(" "),
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

  const selectedOrg: OrgListItem | undefined = orgsQuery.data?.orgs.find(
    (org: OrgListItem) => org.org_id === selectedOrgId,
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Organizations</h1>
          <p className="text-xs text-muted-foreground">
            {orgsQuery.data?.message ?? "Loading organizations…"}
          </p>
        </div>
        <div className="relative w-full max-w-sm">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search organizations…"
            className="h-8 pl-8 text-xs"
          />
        </div>
      </div>

      {orgsQuery.error ? (
        <Alert variant="destructive">
          <AlertDescription>{orgsQuery.error.message}</AlertDescription>
        </Alert>
      ) : null}

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
            emptyMessage="No organizations match your search."
            minWidth="24rem"
            onRowClick={(org: OrgListItem) => setSelectedOrgId(org.org_id)}
          />
        )}
      </div>

      <Sheet
        open={selectedOrgId !== null}
        onOpenChange={(open: boolean) => {
          if (!open) {
            setSelectedOrgId(null);
          }
        }}
      >
        <SheetContent className="flex w-full flex-col p-0 sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>{selectedOrg?.name ?? "Organization"}</SheetTitle>
            <SheetDescription>
              {selectedOrg?.primary_domain ?? "Organization details"}
            </SheetDescription>
          </SheetHeader>
          {detailQuery.isLoading ? (
            <div className="space-y-3 px-6 py-4">
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : detailQuery.data ? (
            <OrgDetailPanel org={detailQuery.data} />
          ) : detailQuery.error ? (
            <div className="px-6 py-4">
              <Alert variant="destructive">
                <AlertDescription>{detailQuery.error.message}</AlertDescription>
              </Alert>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
