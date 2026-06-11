"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { Download, Search } from "lucide-react";
import Link from "next/link";

import {
  CompactCell,
  CompactSortHeader,
  CompactTableShell,
} from "@/components/data-table/compact-table";
import { EntityActionsMenu } from "@/components/entity-actions-menu";
import { PersonDetailPanel } from "@/components/person-detail-panel";
import { UnsavedChangesDialog } from "@/components/unsaved-changes-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { ListPeopleResult, PersonDetailResult, PersonListItem } from "@/lib/api-types";
import type { EditableDetailPanelHandle } from "@/lib/editable-detail-panel";
import { buildCsv, csvFilename, downloadCsv } from "@/lib/csv-export";
import { proxyPost } from "@/lib/proxy-client";

export function PeopleView({
  embedded = false,
  viewingFilter = "mine",
}: {
  embedded?: boolean;
  viewingFilter?: string;
}) {
  const searchParams = useSearchParams();
  const [search, setSearch] = useState<string>(searchParams.get("search") ?? "");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "name", desc: false },
  ]);
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(
    searchParams.get("person") ?? null,
  );
  const [isDetailDirty, setIsDetailDirty] = useState<boolean>(false);
  const [discardDialogOpen, setDiscardDialogOpen] = useState<boolean>(false);
  const [isClosingSave, setIsClosingSave] = useState<boolean>(false);
  const detailPanelRef = useRef<EditableDetailPanelHandle>(null);

  const [sourceFilter, setSourceFilter] = useState<"all" | "phone_linkedin" | "phone_only" | "linkedin_only">("phone_linkedin");

  useEffect(() => {
    setIsDetailDirty(false);
  }, [selectedPersonId]);

  const closeDetailPanel = (): void => {
    setSelectedPersonId(null);
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

  const peopleQuery = useQuery({
    queryKey: ["people"],
    queryFn: () =>
      proxyPost<ListPeopleResult>("list-people", {
        network_only: false,
        include_shared: true,
      }),
  });

  const detailQuery = useQuery({
    queryKey: ["person", selectedPersonId],
    queryFn: () =>
      proxyPost<PersonDetailResult>("get-person", {
        person_id: selectedPersonId,
      }),
    enabled: selectedPersonId !== null,
  });

  const columns: ColumnDef<PersonListItem>[] = useMemo(
    () => [
      {
        id: "name",
        accessorFn: (row: PersonListItem) => row.display_name,
        header: ({ column }) => <CompactSortHeader column={column} label="Name" />,
        cell: ({ row }) => {
          const person: PersonListItem = row.original;
          return (
            <div className="flex items-center gap-1.5 truncate">
              {person.is_claimed ? (
                <img
                  src={person.avatar_url ?? ""}
                  alt=""
                  className="size-5 shrink-0 rounded-full object-cover"
                  referrerPolicy="no-referrer"
                />
              ) : null}
              <span className="truncate">{person.display_name}</span>
              {person.is_claimed ? (
                <Badge variant="secondary" className="shrink-0 px-1 py-0 text-[10px] font-medium uppercase tracking-wide">
                  Active
                </Badge>
              ) : null}
              {person.shared_from ? (
                <Badge variant="outline" className="shrink-0 px-1 py-0 text-[10px] text-muted-foreground">
                  via {person.shared_from}
                </Badge>
              ) : null}
            </div>
          );
        },
        meta: { width: "w-[12rem]" },
      },
      {
        accessorKey: "phone",
        header: "Phone",
        cell: ({ row }) => (
          <CompactCell value={row.original.shared_from ? "—" : (row.original.phone ?? "—")} />
        ),
        meta: { width: "w-[5.5rem]" },
      },
      {
        accessorKey: "primary_email",
        header: ({ column }) => <CompactSortHeader column={column} label="Email" />,
        cell: ({ row }) => (
          <CompactCell
            value={
              row.original.shared_from
                ? "—"
                : (row.original.primary_email ?? row.original.emails[0] ?? "—")
            }
          />
        ),
        meta: { width: "w-[9rem]" },
      },
      {
        accessorKey: "current_role",
        header: ({ column }) => <CompactSortHeader column={column} label="Title" />,
        cell: ({ row }) => (
          <CompactCell value={row.original.current_role ?? "—"} />
        ),
        meta: { width: "w-[7rem]" },
      },
      {
        id: "company",
        accessorFn: (row: PersonListItem) => row.org_name ?? "",
        header: ({ column }) => <CompactSortHeader column={column} label="Company" />,
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
        meta: { width: "w-[7rem]" },
      },
      {
        id: "linkedin",
        accessorFn: (row: PersonListItem) => row.linkedin_url ?? "",
        header: "LinkedIn",
        cell: ({ row }) => {
          if (row.original.shared_from) return <CompactCell value="—" />;
          const url: string | null = row.original.linkedin_url;
          if (!url) return <CompactCell value="—" />;
          return (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              Profile ↗
            </a>
          );
        },
        meta: { width: "w-[4rem]" },
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => {
          if (row.original.shared_from) return null;
          return (
            <div className="flex justify-end">
              <EntityActionsMenu
                entityLabel={row.original.display_name}
                personId={row.original.person_id}
                onEdit={() => setSelectedPersonId(row.original.person_id)}
              />
            </div>
          );
        },
        meta: { width: "w-[2rem]", stickyRight: true },
      },
    ],
    [],
  );

  const filteredPeople: PersonListItem[] = useMemo(() => {
    const all: PersonListItem[] = peopleQuery.data?.people ?? [];

    // First: filter by whose contacts we're viewing
    let rows: PersonListItem[];
    if (viewingFilter === "all") {
      rows = all;
    } else if (viewingFilter === "mine") {
      rows = all.filter((p: PersonListItem) => !p.shared_from);
    } else {
      rows = all.filter((p: PersonListItem) => p.shared_from === viewingFilter);
    }

    // Second: apply source filter (only meaningful for own contacts)
    if (viewingFilter === "mine" && sourceFilter !== "all") {
      rows = rows.filter((p: PersonListItem) => {
        const hasPhone: boolean = !!p.phone;
        const hasLinkedin: boolean = !!p.linkedin_url;
        switch (sourceFilter) {
          case "phone_linkedin":
            return hasPhone && hasLinkedin;
          case "phone_only":
            return hasPhone && !hasLinkedin;
          case "linkedin_only":
            return !hasPhone && hasLinkedin;
          default:
            return true;
        }
      });
    }

    return rows;
  }, [peopleQuery.data?.people, viewingFilter, sourceFilter]);

  const table = useReactTable({
    data: filteredPeople,
    columns,
    state: { sorting, globalFilter: search },
    onSortingChange: setSorting,
    onGlobalFilterChange: setSearch,
    globalFilterFn: (row, _columnId, filterValue: string) => {
      const query: string = filterValue.trim().toLowerCase();
      if (!query) {
        return true;
      }
      const person: PersonListItem = row.original;
      const haystack: string = [
        person.display_name,
        person.primary_email,
        person.phone,
        person.org_name,
        person.current_role,
        person.is_strong_tie ? "professional tie" : "",
        person.shared_from ? `via ${person.shared_from}` : "",
        person.emails.join(" "),
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

  const selectedPerson: PersonListItem | undefined =
    peopleQuery.data?.people.find(
      (person: PersonListItem) => person.person_id === selectedPersonId,
    );

  const handleDownloadCsv = (): void => {
    const rows: PersonListItem[] = table
      .getSortedRowModel()
      .rows.map((row) => row.original);
    const csv: string = buildCsv(
      [
        "Name",
        "Phone",
        "Email",
        "Title",
        "Company",
        "Professional Tie",
        "LinkedIn",
      ],
      rows.map((person: PersonListItem) => [
        person.display_name,
        person.phone ?? "",
        person.primary_email ?? person.emails[0] ?? "",
        person.current_role ?? "",
        person.org_name ?? "",
        person.is_strong_tie ? "yes" : "",
        person.linkedin_url ?? "",
      ]),
    );
    downloadCsv(csvFilename("people"), csv);
  };

  return (
    <div className="space-y-3">
      {!embedded ? (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">People</h1>
            <p className="text-xs text-muted-foreground">
              {peopleQuery.isLoading
                ? "Loading your network…"
                : peopleQuery.data
                  ? `${table.getFilteredRowModel().rows.length.toLocaleString()} contacts shown`
                  : "No network data available."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative w-64">
              <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search people…"
                className="h-8 pl-8 text-sm focus:w-80 transition-all duration-200"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 shrink-0 text-xs"
              onClick={handleDownloadCsv}
              disabled={peopleQuery.isLoading || table.getRowModel().rows.length === 0}
            >
              <Download />
              CSV
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <p className="text-xs text-muted-foreground">
            {peopleQuery.isLoading
              ? "Loading your network…"
              : peopleQuery.data
                ? `${table.getFilteredRowModel().rows.length.toLocaleString()} contacts shown`
                : "No network data available."}
          </p>
          <div className="flex items-center gap-2">
            <div className="relative w-64">
              <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search people…"
                className="h-8 pl-8 text-sm focus:w-80 transition-all duration-200"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 shrink-0 text-xs"
              onClick={handleDownloadCsv}
              disabled={peopleQuery.isLoading || table.getRowModel().rows.length === 0}
            >
              <Download />
              CSV
            </Button>
          </div>
        </div>
      )}

      {viewingFilter === "mine" ? (
        <div className="flex gap-1">
          {([
            ["phone_linkedin", "Phone + LinkedIn"],
            ["phone_only", "Phone only"],
            ["linkedin_only", "LinkedIn only"],
            ["all", "All sources"],
          ] as const).map(([value, label]) => (
            <Button
              key={value}
              type="button"
              variant={sourceFilter === value ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs px-2.5"
              onClick={() => setSourceFilter(value)}
            >
              {label}
            </Button>
          ))}
        </div>
      ) : null}

      {peopleQuery.error ? (
        <Alert variant="destructive">
          <AlertDescription>{peopleQuery.error.message}</AlertDescription>
        </Alert>
      ) : null}

      <div className="overflow-hidden rounded-md border bg-card">
        {peopleQuery.isLoading ? (
          <div className="space-y-1.5 p-2">
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
          </div>
        ) : (
          <CompactTableShell
            table={table}
            columnCount={columns.length}
            emptyMessage="No phone contacts in your network yet. Import them from Graph Settings."
            minWidth="44rem"
            onRowClick={(person: PersonListItem) =>
              setSelectedPersonId(person.person_id)
            }
          />
        )}
      </div>

      <Sheet
        open={selectedPersonId !== null}
        onOpenChange={handleDetailSheetOpenChange}
      >
        <SheetContent className="flex w-full flex-col p-0 sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>{selectedPerson?.display_name ?? "Contact"}</SheetTitle>
            <SheetDescription>
              {selectedPerson?.shared_from
                ? `Shared by ${selectedPerson.shared_from}`
                : (selectedPerson?.primary_email ?? "Contact details")}
            </SheetDescription>
          </SheetHeader>
          {selectedPerson?.shared_from ? (
            <div className="space-y-4 px-6 py-4">
              <div className="rounded-md border bg-muted/50 p-4 text-sm text-muted-foreground">
                <p className="font-medium text-foreground">
                  {selectedPerson.display_name}
                </p>
                {selectedPerson.current_role || selectedPerson.org_name ? (
                  <p className="mt-1">
                    {[selectedPerson.current_role, selectedPerson.org_name]
                      .filter(Boolean)
                      .join(" at ")}
                  </p>
                ) : null}
                <p className="mt-3">
                  Contact info is not shared. Ask{" "}
                  <span className="font-medium text-foreground">
                    {selectedPerson.shared_from}
                  </span>{" "}
                  for an intro if you&rsquo;d like to connect.
                </p>
              </div>
            </div>
          ) : detailQuery.isLoading ? (
            <div className="space-y-3 px-6 py-4">
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : detailQuery.data ? (
            <PersonDetailPanel
              ref={detailPanelRef}
              key={`${selectedPersonId}-${detailQuery.dataUpdatedAt}`}
              person={detailQuery.data}
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
