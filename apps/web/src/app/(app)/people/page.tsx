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
  dateSortingFn,
} from "@/components/data-table/compact-table";
import { EntityActionsMenu } from "@/components/entity-actions-menu";
import { PersonDetailPanel } from "@/components/person-detail-panel";
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
import type { ListPeopleResult, PersonDetailResult, PersonListItem } from "@/lib/api-types";
import { formatDateCompact, formatSourceAbbrev } from "@/lib/formatters";
import { proxyPost } from "@/lib/proxy-client";

export default function PeoplePage() {
  const [search, setSearch] = useState<string>("");
  const [sorting, setSorting] = useState<SortingState>([
    { id: "tie_strength_score", desc: true },
  ]);
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null);

  const peopleQuery = useQuery({
    queryKey: ["people"],
    queryFn: () => proxyPost<ListPeopleResult>("list-people"),
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
        accessorKey: "first_name",
        header: ({ column }) => <CompactSortHeader column={column} label="First" />,
        cell: ({ row }) => (
          <CompactCell value={row.original.first_name || "—"} />
        ),
        meta: { width: "w-[4.25rem]" },
      },
      {
        accessorKey: "last_name",
        header: ({ column }) => <CompactSortHeader column={column} label="Last" />,
        cell: ({ row }) => (
          <CompactCell value={row.original.last_name || "—"} />
        ),
        meta: { width: "w-[4.25rem]" },
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
        meta: { width: "w-[7rem]" },
      },
      {
        accessorKey: "phone",
        header: "Phone",
        cell: ({ row }) => (
          <CompactCell value={row.original.phone ?? "—"} />
        ),
        meta: { width: "w-[5.25rem]" },
      },
      {
        accessorKey: "org_name",
        header: ({ column }) => <CompactSortHeader column={column} label="Org" />,
        cell: ({ row }) => (
          <CompactCell value={row.original.org_name ?? "—"} />
        ),
        meta: { width: "w-[5.5rem]" },
      },
      {
        accessorKey: "current_role",
        header: "Role",
        cell: ({ row }) => (
          <CompactCell value={row.original.current_role ?? "—"} />
        ),
        meta: { width: "w-[4.75rem]" },
      },
      {
        accessorKey: "tie_strength_score",
        header: ({ column }) => (
          <CompactSortHeader column={column} label="Tie" />
        ),
        cell: ({ row }) => (
          <CompactCell
            value={row.original.tie_strength_score.toFixed(2)}
            title={`Tie strength: ${row.original.tie_strength_score.toFixed(2)}`}
          />
        ),
        meta: { width: "w-[3rem]" },
      },
      {
        id: "sources",
        accessorFn: (row: PersonListItem) => row.sources.join(", "),
        header: "Src",
        cell: ({ row }) => (
          <CompactCell
            value={
              row.original.sources.length > 0
                ? row.original.sources
                    .map((source: string) => formatSourceAbbrev(source))
                    .join(", ")
                : "—"
            }
            title={row.original.sources.join(", ")}
          />
        ),
        meta: { width: "w-[3.75rem]" },
      },
      {
        accessorKey: "first_contact_at",
        header: ({ column }) => <CompactSortHeader column={column} label="First" />,
        cell: ({ row }) => (
          <CompactCell value={formatDateCompact(row.original.first_contact_at)} />
        ),
        sortingFn: dateSortingFn,
        meta: { width: "w-[3.5rem]" },
      },
      {
        accessorKey: "last_contact_at",
        header: ({ column }) => <CompactSortHeader column={column} label="Last" />,
        cell: ({ row }) => (
          <CompactCell value={formatDateCompact(row.original.last_contact_at)} />
        ),
        sortingFn: dateSortingFn,
        meta: { width: "w-[3.5rem]" },
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <EntityActionsMenu entityLabel={row.original.display_name} />
          </div>
        ),
        meta: { width: "w-[2rem]", stickyRight: true },
      },
    ],
    [],
  );

  const table = useReactTable({
    data: peopleQuery.data?.people ?? [],
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
        person.first_name,
        person.last_name,
        person.primary_email,
        person.phone,
        person.org_name,
        person.current_role,
        person.emails.join(" "),
        person.sources.join(" "),
        person.tie_strength_score.toString(),
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

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">People</h1>
          <p className="text-xs text-muted-foreground">
            {peopleQuery.data?.message ?? "Loading contacts…"}
          </p>
        </div>
        <div className="relative w-full max-w-sm">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search people…"
            className="h-8 pl-8 text-xs"
          />
        </div>
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
            emptyMessage="No contacts match your search."
            minWidth="49rem"
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
            <PersonDetailPanel person={detailQuery.data} />
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
