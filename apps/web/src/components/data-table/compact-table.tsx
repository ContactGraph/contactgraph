"use client";

import { flexRender, type HeaderGroup, type Row, type Table } from "@tanstack/react-table";
import { ArrowUpDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    width?: string;
    stickyRight?: boolean;
  }
}

export const compactTableStyles = {
  table: "w-full min-w-full table-fixed border-separate border-spacing-0 text-xs leading-tight",
  thead: "border-b bg-muted/40",
  th: "overflow-hidden px-1.5 py-1 text-left font-medium text-muted-foreground",
  td: "overflow-hidden px-1.5 py-1 align-middle",
  row: "group border-b transition-colors hover:bg-muted/30",
  stickyRightHeader:
    "sticky right-0 z-20 border-l bg-muted/40 shadow-[-4px_0_6px_-4px_rgba(0,0,0,0.12)]",
  stickyRightCell:
    "sticky right-0 z-10 border-l bg-card shadow-[-4px_0_6px_-4px_rgba(0,0,0,0.08)] group-hover:bg-muted/30",
} as const;

function stickyClass(isSticky: boolean, variant: "header" | "body"): string {
  if (!isSticky) {
    return "";
  }
  return variant === "header"
    ? compactTableStyles.stickyRightHeader
    : compactTableStyles.stickyRightCell;
}

export function CompactTableShell<TData>({
  table,
  columnCount,
  emptyMessage,
  onRowClick,
  minWidth,
}: {
  table: Table<TData>;
  columnCount: number;
  emptyMessage: string;
  onRowClick?: (row: TData) => void;
  minWidth?: string;
}) {
  const rows: Row<TData>[] = table.getRowModel().rows;

  return (
    <div className="overflow-x-auto">
      <table
        className={compactTableStyles.table}
        style={minWidth ? { minWidth } : undefined}
      >
        <colgroup>
          {table.getAllLeafColumns().map((column) => (
            <col
              key={column.id}
              className={column.columnDef.meta?.width ?? "w-auto"}
            />
          ))}
        </colgroup>
        <thead className={compactTableStyles.thead}>
          {table.getHeaderGroups().map((headerGroup: HeaderGroup<TData>) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => {
                const isStickyRight: boolean =
                  header.column.columnDef.meta?.stickyRight === true;
                return (
                  <th
                    key={header.id}
                    className={cn(
                      compactTableStyles.th,
                      stickyClass(isStickyRight, "header"),
                    )}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columnCount}
                className="px-1.5 py-6 text-center text-muted-foreground"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={row.id}
                className={cn(
                  compactTableStyles.row,
                  onRowClick && "cursor-pointer",
                )}
                onClick={
                  onRowClick
                    ? () => {
                        onRowClick(row.original);
                      }
                    : undefined
                }
              >
                {row.getVisibleCells().map((cell) => {
                  const isStickyRight: boolean =
                    cell.column.columnDef.meta?.stickyRight === true;
                  return (
                    <td
                      key={cell.id}
                      className={cn(
                        compactTableStyles.td,
                        stickyClass(isStickyRight, "body"),
                      )}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function CompactCell({
  value,
  title,
  className,
}: {
  value: string;
  title?: string;
  className?: string;
}) {
  const displayTitle: string = title ?? value;
  return (
    <span
      className={cn("block truncate", className)}
      title={displayTitle !== "—" ? displayTitle : undefined}
    >
      {value}
    </span>
  );
}

export function CompactSortHeader({
  column,
  label,
}: {
  column: {
    getIsSorted: () => false | "asc" | "desc";
    toggleSorting: (desc?: boolean) => void;
  };
  label: string;
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="-ml-1 h-6 max-w-full px-1 text-xs font-medium"
      onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
    >
      <span className="truncate">{label}</span>
      <ArrowUpDown className="ml-0.5 size-3 shrink-0" />
    </Button>
  );
}

export function dateSortingFn(
  rowA: { getValue: (id: string) => unknown },
  rowB: { getValue: (id: string) => unknown },
  columnId: string,
): number {
  const left: string | null = rowA.getValue(columnId) as string | null;
  const right: string | null = rowB.getValue(columnId) as string | null;
  if (!left && !right) {
    return 0;
  }
  if (!left) {
    return 1;
  }
  if (!right) {
    return -1;
  }
  return left.localeCompare(right);
}
