"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { SetupStepStatusIcon } from "@/components/setup/setup-step-status-icon";
import { filterOrgsByScope } from "@/components/target-selection/filter-orgs-by-scope";
import { TargetOrgPicker } from "@/components/target-selection/target-org-picker";
import { TargetScopePanel } from "@/components/target-selection/target-scope-panel";
import { JOB_TARGET_SELECTION_CONFIG } from "@/components/target-selection/target-selection-config";
import {
  defaultTargetScope,
  targetScopeFromPayload,
  targetScopeToPayload,
  type TargetScope,
} from "@/components/target-selection/types";
import { useOrgListMembership } from "@/components/target-selection/use-org-list-membership";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  JobPreferencesResult,
  JobTargetScopePayload,
  ListOrgsResult,
  SetJobTargetScopeRequest,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";

interface JobTargetCompaniesCardProps {
  targetComplete: boolean;
  enrichmentInProgress: boolean;
  enrichmentProgressLabel: string;
}

export function JobTargetCompaniesCard({
  targetComplete,
  enrichmentInProgress,
  enrichmentProgressLabel,
}: JobTargetCompaniesCardProps) {
  const queryClient = useQueryClient();
  const [pickerOpen, setPickerOpen] = useState<boolean>(false);
  const [scope, setScope] = useState<TargetScope>(defaultTargetScope());
  const [applyPending, setApplyPending] = useState<boolean>(false);

  const jobPreferencesQuery = useQuery({
    queryKey: ["job-preferences"],
    queryFn: () => proxyPost<JobPreferencesResult>("get-job-preferences"),
  });

  const orgsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () =>
      proxyPost<ListOrgsResult>("list-orgs", { include_shared: true }),
    staleTime: 0,
  });

  const { selectedCount, selectedOrgIds, bulkUpdateAsync, replaceSelection, isPending } =
    useOrgListMembership(JOB_TARGET_SELECTION_CONFIG.listName);

  useEffect(() => {
    const payload: JobTargetScopePayload | null | undefined =
      jobPreferencesQuery.data?.target_scope;
    if (payload !== undefined) {
      setScope(targetScopeFromPayload(payload));
    }
  }, [jobPreferencesQuery.data?.target_scope]);

  const persistScopeMutation = useMutation({
    mutationFn: (nextScope: TargetScope) =>
      proxyPost<JobPreferencesResult>("set-job-target-scope", {
        target_scope: targetScopeToPayload(nextScope),
      } satisfies SetJobTargetScopeRequest),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["job-preferences"] });
    },
    onError: () => {
      toast.error("Failed to save filter preferences");
    },
  });

  const allOrgs = orgsQuery.data?.orgs ?? [];
  const matchingCount: number = useMemo(
    () => filterOrgsByScope(allOrgs, scope).length,
    [allOrgs, scope],
  );

  const handleScopeChange = (nextScope: TargetScope): void => {
    setScope(nextScope);
    persistScopeMutation.mutate(nextScope);
  };

  const handleApplyMatching = async (mode: "add" | "replace"): Promise<void> => {
    setApplyPending(true);
    try {
      const matchingOrgIds: string[] = filterOrgsByScope(allOrgs, scope).map(
        (org) => org.org_id,
      );
      if (mode === "replace") {
        await replaceSelection(matchingOrgIds);
        toast.success(
          `Updated list to ${matchingOrgIds.length.toLocaleString()} matching companies`,
        );
        return;
      }
      const toAdd: string[] = matchingOrgIds.filter(
        (orgId) => !selectedOrgIds.has(orgId),
      );
      if (toAdd.length === 0) {
        toast.message("All matching companies are already selected");
        return;
      }
      await bulkUpdateAsync(toAdd, "add");
      toast.success(
        `Added ${toAdd.length.toLocaleString()} companies — remove any you don't want`,
      );
    } catch {
      toast.error("Failed to update company list");
    } finally {
      setApplyPending(false);
    }
  };

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="mt-0.5 shrink-0">
              <SetupStepStatusIcon
                complete={targetComplete}
                inProgress={enrichmentInProgress && !targetComplete}
              />
            </div>
            <div className="space-y-1">
              <CardTitle className="text-base">
                {JOB_TARGET_SELECTION_CONFIG.title}
              </CardTitle>
              <CardDescription>
                {JOB_TARGET_SELECTION_CONFIG.description}
              </CardDescription>
              {enrichmentInProgress ? (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" />
                  {enrichmentProgressLabel}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {selectedCount === 0
                    ? "0 organizations selected for job search"
                    : `${selectedCount.toLocaleString()} organization${selectedCount === 1 ? "" : "s"} selected for job search`}
                </p>
              )}
            </div>
          </div>
          {!enrichmentInProgress ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPickerOpen(true)}
            >
              {JOB_TARGET_SELECTION_CONFIG.manageButtonLabel}
            </Button>
          ) : null}
        </CardHeader>

        {!enrichmentInProgress && selectedCount === 0 ? (
          <CardContent className="pt-0">
            <TargetScopePanel
              scope={scope}
              onScopeChange={handleScopeChange}
              allOrgs={allOrgs}
              selectedCount={selectedCount}
              onApplyMatching={(mode) => {
                void handleApplyMatching(mode);
              }}
              applyPending={
                isPending || applyPending || orgsQuery.isLoading
              }
            />
            {matchingCount === 0 && !orgsQuery.isLoading ? (
              <p className="mt-3 text-xs text-muted-foreground">
                No companies match yet. Import contacts and enrich organizations
                from Graph setup, or adjust filters above.
              </p>
            ) : null}
          </CardContent>
        ) : null}
      </Card>

      <TargetOrgPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        config={JOB_TARGET_SELECTION_CONFIG}
        scope={scope}
        onScopeChange={setScope}
        onScopePersist={async (nextScope) => {
          await persistScopeMutation.mutateAsync(nextScope);
        }}
      />
    </>
  );
}
