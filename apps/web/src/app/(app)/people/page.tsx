"use client";

import { useMemo, useState } from "react";
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

import {
  CompactCell,
  CompactSortHeader,
  CompactTableShell,
} from "@/components/data-table/compact-table";
import { EntityActionsMenu } from "@/components/entity-actions-menu";
import { PersonDetailPanel } from "@/components/person-detail-panel";
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
import { buildCsv, csvFilename, downloadCsv } from "@/lib/csv-export";
import { proxyPost } from "@/lib/proxy-client";

export default function PeoplePage() {
  const searchParams = useSearchParams();
  const [search, setSearch] = useState<string>(searchParams.get("search") ?? "");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "name", desc: false },
  ]);
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null);

  const [filter, setFilter] = useState<"all" | "phone_linkedin" | "phone_only" | "linkedin_only">("phone_linkedin");

  const peopleQuery = useQuery({
    queryKey: ["people"],
    queryFn: () =>
      proxyPost<ListPeopleResult>("list-people", { network_only: false }),
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
              <span className="truncate">{person.display_name}</span>
              {person.is_strong_tie ? (
                <Badge variant="secondary" className="shrink-0 px-1 py-0 text-[10px]">
                  Pro
                </Badge>
              ) : null}
            </div>
          );
        },
        meta: { width: "w-[10rem]" },
      },
      {
        accessorKey: "phone",
        header: "Phone",
        cell: ({ row }) => (
          <CompactCell value={row.original.phone ?? "—"} />
        ),
        meta: { width: "w-[5.5rem]" },
      },
      {
        accessorKey: "primary_email",
        header: ({ column }) => <CompactSortHeader column={column} label="Email" />,
        cell: ({ row }) => (
          <CompactCell
            value={
              row.original.primary_email ?? row.original.emails[0] ?? "—"
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
        cell: ({ row }) => (
          <CompactCell value={row.original.org_name ?? "—"} />
        ),
        meta: { width: "w-[7rem]" },
      },
      {
        id: "linkedin",
        accessorFn: (row: PersonListItem) => row.linkedin_url ?? "",
        header: "LinkedIn",
        cell: ({ row }) => {
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
        cell: ({ row }) => (
          <div className="flex justify-end">
            <EntityActionsMenu
              entityLabel={row.original.display_name}
              personId={row.original.person_id}
            />
          </div>
        ),
        meta: { width: "w-[2rem]", stickyRight: true },
      },
    ],
    [],
  );

  const filteredPeople: PersonListItem[] = useMemo(() => {
    const all: PersonListItem[] = peopleQuery.data?.people ?? [];
    if (filter === "all") return all;
    return all.filter((p: PersonListItem) => {
      const hasPhone: boolean = !!p.phone;
      const hasLinkedin: boolean = !!p.linkedin_url;
      switch (filter) {
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
  }, [peopleQuery.data?.people, filter]);

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

      <div className="flex gap-1">
        {([
          ["phone_linkedin", "Phone + LinkedIn"],
          ["phone_only", "Phone only"],
          ["linkedin_only", "LinkedIn only"],
          ["all", "All"],
        ] as const).map(([value, label]) => (
          <Button
            key={value}
            type="button"
            variant={filter === value ? "default" : "outline"}
            size="sm"
            className="h-8 text-xs px-2.5"
            onClick={() => setFilter(value)}
          >
            {label}
          </Button>
        ))}
      </div>

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
            emptyMessage="No phone contacts in your network yet. Import them from Sources."
            minWidth="44rem"
            onRowClick={(person: PersonListItem) =>
              setSelectedPersonId(person.person_id)
            }
          />
        )}
      </div>

      <Sheet
        open={selectedPersonId !== null}
        onOpenChange={(open: boolean) => {
          if (!open) {
            setSelectedPersonId(null);
          }
        }}
      >
        <SheetContent className="flex w-full flex-col p-0 sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>{selectedPerson?.display_name ?? "Contact"}</SheetTitle>
            <SheetDescription>
              {selectedPerson?.primary_email ?? "Contact details"}
            </SheetDescription>
          </SheetHeader>
          {detailQuery.isLoading ? (
            <div className="space-y-3 px-6 py-4">
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : detailQuery.data ? (
            <PersonDetailPanel
              key={`${selectedPersonId}-${detailQuery.dataUpdatedAt}`}
              person={detailQuery.data}
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
    </div>
  );
}
