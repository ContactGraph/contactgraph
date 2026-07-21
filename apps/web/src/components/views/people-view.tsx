"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";
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
import { ChevronDown, Download, ListFilter, Loader2 } from "lucide-react";
import Link from "next/link";

import {
  CompactCell,
  CompactSortHeader,
  CompactTableShell,
} from "@/components/data-table/compact-table";
import { EntityActionsMenu } from "@/components/entity-actions-menu";
import { OrgLogo } from "@/components/org-logo";
import { PersonDetailPanel } from "@/components/person-detail-panel";
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
import type { ListPeopleResult, PersonDetailResult, PersonListItem } from "@/lib/api-types";
import type { EditableDetailPanelHandle } from "@/lib/editable-detail-panel";
import { buildCsv, csvFilename, downloadCsv } from "@/lib/csv-export";
import { proxyPost } from "@/lib/proxy-client";

interface PeopleFilters {
  contactable: boolean;
  email: boolean;
  phone: boolean;
  company: boolean;
  position: boolean;
}

type PeopleFilterKey = keyof PeopleFilters;

const DEFAULT_PEOPLE_FILTERS: PeopleFilters = {
  contactable: true,
  email: false,
  phone: false,
  company: true,
  position: false,
};

const EMPTY_PEOPLE_FILTERS: PeopleFilters = {
  contactable: false,
  email: false,
  phone: false,
  company: false,
  position: false,
};

const PEOPLE_FILTER_OPTIONS: ReadonlyArray<{
  key: PeopleFilterKey;
  label: string;
}> = [
  { key: "contactable", label: "Email or phone" },
  { key: "email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "company", label: "Current company" },
  { key: "position", label: "Current position" },
];

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

  // `filters` updates synchronously so the menu checkboxes reflect clicks
  // instantly; `appliedFilters` is updated inside a transition so the expensive
  // table recompute happens at low priority (surfaced via `isFiltering`).
  const [filters, setFilters] = useState<PeopleFilters>(
    DEFAULT_PEOPLE_FILTERS,
  );
  const [appliedFilters, setAppliedFilters] = useState<PeopleFilters>(
    DEFAULT_PEOPLE_FILTERS,
  );
  const [isFiltering, startFilterTransition] = useTransition();

  const applyFilters = (next: PeopleFilters): void => {
    setFilters(next);
    startFilterTransition(() => {
      setAppliedFilters(next);
    });
  };

  const toggleFilter = (key: PeopleFilterKey): void => {
    applyFilters({ ...filters, [key]: !filters[key] });
  };

  const activeFilterCount: number =
    PEOPLE_FILTER_OPTIONS.filter((option) => filters[option.key]).length;
  const appliedFilterCount: number =
    PEOPLE_FILTER_OPTIONS.filter((option) => appliedFilters[option.key]).length;

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
        meta: { width: "w-[8rem] sm:w-[12rem]" },
      },
      {
        accessorKey: "current_role",
        header: ({ column }) => <CompactSortHeader column={column} label="Title" />,
        cell: ({ row }) => (
          <CompactCell value={row.original.current_role ?? "—"} />
        ),
        meta: { width: "w-[6rem] sm:w-[9rem]" },
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
              className="flex items-center gap-1.5 truncate text-xs text-primary no-underline"
              onClick={(e) => e.stopPropagation()}
            >
              <OrgLogo domain={row.original.org_primary_domain} name={orgName} size={16} />
              <span className="truncate">{orgName}</span>
            </Link>
          );
        },
        meta: { width: "w-[6rem] sm:w-[9rem]" },
      },
      {
        id: "jobs",
        accessorFn: (row: PersonListItem) => row.job_count,
        header: ({ column }) => <CompactSortHeader column={column} label="# Jobs" />,
        cell: ({ row }) => (
          <CompactCell value={row.original.job_count > 0 ? row.original.job_count.toString() : "—"} />
        ),
        meta: { width: "w-[3.5rem] sm:w-[5rem]" },
      },
      {
        accessorKey: "phone",
        header: "Phone",
        cell: ({ row }) => (
          <CompactCell value={row.original.shared_from ? "—" : (row.original.phone ?? "—")} />
        ),
        meta: { width: "w-[5.5rem] sm:w-[8rem]" },
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
        meta: { width: "w-[9rem] sm:w-[14rem]" },
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
              className="text-xs text-primary no-underline"
              onClick={(e) => e.stopPropagation()}
            >
              Profile ↗
            </a>
          );
        },
        meta: { width: "w-[4rem] sm:w-[6rem]" },
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
        meta: { width: "w-[2rem]", stickyRight: true, hiddenClass: "hidden sm:table-cell" },
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

    // Second: apply attribute filters (only meaningful for own contacts)
    if (viewingFilter === "mine" && appliedFilterCount > 0) {
      rows = rows.filter((p: PersonListItem) => {
        const hasPhone: boolean = !!p.phone;
        const hasEmail: boolean = !!(p.primary_email || p.emails.length > 0);
        const hasCompany: boolean = !!p.org_name;
        const hasPosition: boolean = !!p.current_role;
        if (appliedFilters.contactable && !(hasEmail || hasPhone)) return false;
        if (appliedFilters.email && !hasEmail) return false;
        if (appliedFilters.phone && !hasPhone) return false;
        if (appliedFilters.company && !hasCompany) return false;
        if (appliedFilters.position && !hasPosition) return false;
        return true;
      });
    }

    return rows;
  }, [peopleQuery.data?.people, viewingFilter, appliedFilters, appliedFilterCount]);

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

  const contactCountText: string = peopleQuery.isLoading
    ? "Loading your network…"
    : peopleQuery.data
      ? `${table.getFilteredRowModel().rows.length.toLocaleString()} contacts shown`
      : "No network data available.";

  return (
    <div className="space-y-2">
      {!embedded ? (
        <div>
          <h1 className="text-xl font-semibold tracking-tight">People</h1>
          <p className="text-xs text-muted-foreground">{contactCountText}</p>
        </div>
      ) : null}

      {peopleQuery.error ? (
        <Alert variant="destructive">
          <AlertDescription>{peopleQuery.error.message}</AlertDescription>
        </Alert>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput
          containerClassName="w-36 sm:w-48"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search people…"
        />

        {viewingFilter === "mine" ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs"
              >
                <ListFilter className="size-3.5" />
                <span>Filters</span>
                {activeFilterCount > 0 ? (
                  <Badge
                    variant="secondary"
                    className="ml-0.5 h-4 min-w-4 justify-center rounded-full px-1 text-[10px] tabular-nums"
                  >
                    {activeFilterCount}
                  </Badge>
                ) : null}
                <ChevronDown className="size-3 opacity-60" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-56">
              <DropdownMenuLabel>Show records with</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {PEOPLE_FILTER_OPTIONS.map((option) => (
                <DropdownMenuCheckboxItem
                  key={option.key}
                  checked={filters[option.key]}
                  onCheckedChange={() => toggleFilter(option.key)}
                  onSelect={(event) => event.preventDefault()}
                >
                  {option.label}
                </DropdownMenuCheckboxItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                disabled={activeFilterCount === 0}
                onSelect={() => applyFilters(EMPTY_PEOPLE_FILTERS)}
              >
                Clear filters
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}

        <Button
          type="button"
          variant="outline"
          size="icon"
          className="size-8 sm:hidden"
          onClick={handleDownloadCsv}
          disabled={peopleQuery.isLoading || table.getRowModel().rows.length === 0}
          aria-label="Download CSV"
        >
          <Download className="size-3.5" />
        </Button>

        <div className="ml-auto hidden items-center gap-2 sm:flex">
          {embedded ? (
            <span className="text-xs text-muted-foreground">{contactCountText}</span>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={handleDownloadCsv}
            disabled={peopleQuery.isLoading || table.getRowModel().rows.length === 0}
          >
            <Download className="size-3.5" />
            CSV
          </Button>
        </div>
      </div>

      <div className="relative overflow-hidden rounded-md border bg-card">
        {peopleQuery.isLoading ? (
          <div className="space-y-1.5 p-2">
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
          </div>
        ) : (
          <div
            className={
              isFiltering
                ? "pointer-events-none opacity-60 transition-opacity"
                : "transition-opacity"
            }
            aria-busy={isFiltering}
          >
            <CompactTableShell
              table={table}
              columnCount={columns.length}
              emptyMessage="No people match these filters. Try adjusting or clearing them, or import contacts from Graph Settings."
              minWidth="38rem"
              onRowClick={(person: PersonListItem) =>
                setSelectedPersonId(person.person_id)
              }
            />
          </div>
        )}
        {isFiltering ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="flex items-center gap-2 rounded-md border bg-background/95 px-3 py-1.5 text-xs text-muted-foreground shadow-sm">
              <Loader2 className="size-3.5 animate-spin" />
              Filtering…
            </div>
          </div>
        ) : null}
      </div>

      <Sheet
        open={selectedPersonId !== null}
        onOpenChange={handleDetailSheetOpenChange}
      >
        <SheetContent className="flex w-full flex-col p-0 sm:max-w-xl">
          <SheetHeader
            actions={
              selectedPerson !== undefined && selectedPerson.shared_from === null ? (
                <EntityActionsMenu
                  entityLabel={selectedPerson.display_name}
                  personId={selectedPerson.person_id}
                  triggerClassName="size-9 shrink-0"
                />
              ) : undefined
            }
          >
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
