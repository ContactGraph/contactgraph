"use client";

import Link from "next/link";
import { Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ListStrongTiesResult, NetworkStatusResult } from "@/lib/api-types";

interface StrongTiesStepProps {
  networkStatus: NetworkStatusResult | undefined;
  strongTies: ListStrongTiesResult | undefined;
  isLoading: boolean;
}

export function StrongTiesStep({
  networkStatus,
  strongTies,
  isLoading,
}: StrongTiesStepProps) {
  const visible: boolean =
    (networkStatus?.phone_imported ?? false) &&
    (networkStatus?.linkedin_imported ?? false);
  const count: number = networkStatus?.strong_tie_count ?? 0;

  if (!visible) {
    return null;
  }

  const preview = strongTies?.strong_ties.slice(0, 5) ?? [];

  return (
    <div className="rounded-lg border bg-muted/20 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Users className="size-5 text-primary" />
            <p className="font-medium">Your strong professional ties</p>
            <Badge variant="secondary">{count}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {count > 0
              ? `${count} people in your phone are also LinkedIn connections — your strong professional ties.`
              : "No overlaps yet between phone contacts and LinkedIn connections."}
          </p>
          {preview.length > 0 ? (
            <ul className="text-sm text-muted-foreground">
              {preview.map((tie) => (
                <li key={tie.person_id}>
                  {tie.name}
                  {tie.current_company ? ` · ${tie.current_company}` : ""}
                </li>
              ))}
              {count > preview.length ? (
                <li>…and {count - preview.length} more</li>
              ) : null}
            </ul>
          ) : null}
        </div>
        <Button asChild variant="outline" size="sm" disabled={isLoading || count === 0}>
          <Link href="/people">View in People</Link>
        </Button>
      </div>
    </div>
  );
}
