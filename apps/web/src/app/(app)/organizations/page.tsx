"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { Download, MoreHorizontal, Pencil, Search, Users } from "lucide-react";
import { useRouter } from "next/navigation";

import {
  CompactCell,
  CompactSortHeader,
  CompactTableShell,
} from "@/components/data-table/compact-table";
import { OrgDetailPanel } from "@/components/org-detail-panel";
import { UnsavedChangesDialog } from "@/components/unsaved-changes-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
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
import type { ListOrgsResult, OrgDetailResult, OrgListItem } from "@/lib/api-types";
import type { EditableDetailPanelHandle } from "@/lib/editable-detail-panel";
import { formatCompanySize } from "@/lib/company-size";
import { buildCsv, csvFilename, downloadCsv } from "@/lib/csv-export";
import { formatIndustryTags } from "@/lib/industry-tags";
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

export default function OrganizationsPage() {
  const router = useRouter();
  const [search, setSearch] = useState<string>("");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "name", desc: false },
  ]);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [isDetailDirty, setIsDetailDirty] = useState<boolean>(false);
  const [discardDialogOpen, setDiscardDialogOpen] = useState<boolean>(false);
  const [isClosingSave, setIsClosingSave] = useState<boolean>(false);
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
    queryFn: () => proxyPost<ListOrgsResult>("list-orgs"),
    staleTime: 0,
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
          <CompactLinkCell
            href={row.original.careers_url}
            label="Careers"
          />
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
            title={formatCompanySize(
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
          <CompactCell
            value={formatIndustryTags(row.original.categories)}
            title={formatIndustryTags(row.original.categories)}
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
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedOrgId(row.original.org_id);
                  }}
                >
                  <Pencil className="mr-2 size-4" />
                  Edit
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
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

  const selectedOrg: OrgListItem | undefined = orgsQuery.data?.orgs.find(
    (org: OrgListItem) => org.org_id === selectedOrgId,
  );

  const handleDownloadCsv = (): void => {
    const rows: OrgListItem[] = table
      .getSortedRowModel()
      .rows.map((row) => row.original);
    const csv: string = buildCsv(
      ["Organization", "Description", "Website", "Jobs", "Size", "Categories", "Contacts"],
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

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Organizations</h1>
          <p className="text-xs text-muted-foreground">
            {orgsQuery.isLoading
              ? "Loading organizations…"
              : `${table.getFilteredRowModel().rows.length} organization(s) in your graph.`}
          </p>
        </div>
        <div className="flex w-full max-w-md items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search organizations…"
              className="h-8 pl-8 text-xs"
            />
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 shrink-0 text-xs"
            onClick={handleDownloadCsv}
            disabled={orgsQuery.isLoading || table.getRowModel().rows.length === 0}
          >
            <Download />
            CSV
          </Button>
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
            minWidth="48rem"
            onRowClick={(org: OrgListItem) => setSelectedOrgId(org.org_id)}
          />
        )}
      </div>

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
