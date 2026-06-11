"use client";

import { useCallback, useState } from "react";
import { Loader2, Merge, Settings } from "lucide-react";

import { GraphSetupCards } from "@/components/setup/graph-setup-cards";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { DedupPersonsResult } from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";

interface GraphSettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function GraphSettingsButton({
  open,
  onOpenChange,
}: GraphSettingsModalProps) {
  const [dedupPending, setDedupPending] = useState<boolean>(false);
  const [dedupResult, setDedupResult] = useState<string | null>(null);

  const handleDedup = useCallback(async () => {
    setDedupPending(true);
    setDedupResult(null);
    try {
      const result: DedupPersonsResult =
        await proxyPost<DedupPersonsResult>("dedup-persons");
      setDedupResult(result.message);
    } catch (err: unknown) {
      const msg: string =
        err instanceof Error ? err.message : "Dedup failed";
      setDedupResult(msg);
    } finally {
      setDedupPending(false);
    }
  }, []);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Settings className="size-4" />
          Graph Settings
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Graph Settings</DialogTitle>
          <DialogDescription>
            Re-upload contacts or add new imports to refresh your network.
          </DialogDescription>
        </DialogHeader>
        <GraphSetupCards compact />

        <div className="border-t pt-4">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <p className="text-sm font-medium">Merge duplicates</p>
              <p className="text-xs text-muted-foreground">
                Merge contacts that appear as separate records due to name
                variations or email aliases.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDedup}
              disabled={dedupPending}
              className="shrink-0"
            >
              {dedupPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Merge className="size-4" />
              )}
              {dedupPending ? "Merging…" : "Merge"}
            </Button>
          </div>
          {dedupResult !== null ? (
            <p className="mt-2 text-xs text-muted-foreground">{dedupResult}</p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
