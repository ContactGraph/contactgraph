import type { SyncState } from "@/lib/api-types";
import { Badge } from "@/components/ui/badge";

const syncVariantMap: Record<
  SyncState,
  "default" | "secondary" | "success" | "warning" | "destructive" | "outline"
> = {
  pending: "secondary",
  syncing: "warning",
  partial: "warning",
  complete: "success",
  failed: "destructive",
};

export function SyncStateBadge({ state }: { state: SyncState }) {
  return (
    <Badge variant={syncVariantMap[state]} className="capitalize">
      {state.replace("_", " ")}
    </Badge>
  );
}

export function formatSourceType(sourceType: string): string {
  return sourceType
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char: string) => char.toUpperCase());
}

export function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatDateCompact(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "numeric",
    day: "numeric",
    year: "2-digit",
  }).format(new Date(value));
}

export function formatSourceAbbrev(sourceType: string): string {
  const abbreviations: Record<string, string> = {
    google_mail: "Gmail",
    google_contacts: "Contacts",
    google_calendar: "Calendar",
  };
  return abbreviations[sourceType] ?? formatSourceType(sourceType);
}
