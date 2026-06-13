"use client";

import { Loader2, MoreHorizontal, Pencil, Sparkles } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { EnrichPersonResult } from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";

interface EntityActionsMenuProps {
  entityLabel: string;
  personId: string;
  onEdit?: () => void;
  triggerClassName?: string;
}

export function EntityActionsMenu({
  entityLabel,
  personId,
  onEdit,
  triggerClassName,
}: EntityActionsMenuProps) {
  const queryClient = useQueryClient();

  const enrichMutation = useMutation({
    mutationFn: () =>
      proxyPost<EnrichPersonResult>("enrich-person", { person_id: personId }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["people"] });
      await queryClient.invalidateQueries({ queryKey: ["person", personId] });
    },
  });

  const notifyComingSoon = (action: string): void => {
    window.alert(`${action} for ${entityLabel} is coming soon.`);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={triggerClassName ?? "size-6 shrink-0"}
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
            enrichMutation.mutate();
          }}
          disabled={enrichMutation.isPending}
        >
          {enrichMutation.isPending ? (
            <Loader2 className="mr-2 size-4 animate-spin" />
          ) : (
            <Sparkles className="mr-2 size-4" />
          )}
          {enrichMutation.isPending ? "Enriching…" : "Enrich"}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onEdit?.();
          }}
          disabled={onEdit === undefined}
        >
          <Pencil className="mr-2 size-4" />
          Edit
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => notifyComingSoon("Merge")}>
          Merge with contact
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-destructive focus:text-destructive"
          onClick={() => notifyComingSoon("Delete")}
        >
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
