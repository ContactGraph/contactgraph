"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { OrgListItem, ViewTrustedUsersResult } from "@/lib/api-types";
import { formatCompanySize } from "@/lib/company-size";
import { proxyPost } from "@/lib/proxy-client";
import { cn } from "@/lib/utils";

import { filterOrgsByScope } from "./filter-orgs-by-scope";
import {
  INDUSTRY_SCOPE_PRESETS,
  presetIdsFromTags,
  presetTagsForSelection,
} from "./industry-scope-presets";
import { MINE_SHARER_KEY, type TargetScope } from "./types";

interface TargetScopePanelProps {
  scope: TargetScope;
  onScopeChange: (scope: TargetScope) => void;
  allOrgs: ReadonlyArray<OrgListItem>;
  selectedCount: number;
  onApplyMatching: (mode: "add" | "replace") => void;
  applyPending?: boolean;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

export function TargetScopePanel({
  scope,
  onScopeChange,
  allOrgs,
  selectedCount,
  onApplyMatching,
  applyPending = false,
  collapsed = false,
  onToggleCollapsed,
}: TargetScopePanelProps) {
  const trustQuery = useQuery({
    queryKey: ["trust-list"],
    queryFn: () => proxyPost<ViewTrustedUsersResult>("view-trusted-users"),
    staleTime: 60 * 1000,
  });

  const availableSharers: string[] = useMemo(() => {
    return (trustQuery.data?.members ?? [])
      .map((member) => member.name ?? member.email)
      .sort((left, right) => left.localeCompare(right));
  }, [trustQuery.data?.members]);

  const availableSizeBands: string[] = useMemo(() => {
    const bands = new Set<string>();
    for (const org of allOrgs) {
      if (org.company_size_band) {
        bands.add(org.company_size_band);
      }
    }
    return [...bands].sort();
  }, [allOrgs]);

  const selectedPresetIds: ReadonlySet<string> = presetIdsFromTags(
    scope.industryTags,
  );

  const matchingOrgs: OrgListItem[] = useMemo(
    () => filterOrgsByScope(allOrgs, scope),
    [allOrgs, scope],
  );

  const togglePreset = (presetId: string): void => {
    const nextPresetIds = new Set(selectedPresetIds);
    if (nextPresetIds.has(presetId)) {
      nextPresetIds.delete(presetId);
    } else {
      nextPresetIds.add(presetId);
    }
    onScopeChange({
      ...scope,
      industryTags: presetTagsForSelection(nextPresetIds),
    });
  };

  const toggleSharer = (sharerKey: string, checked: boolean): void => {
    const nextSharers = new Set(scope.sharerNames);
    if (checked) {
      nextSharers.add(sharerKey);
    } else {
      nextSharers.delete(sharerKey);
      if (nextSharers.size === 0) {
        nextSharers.add(MINE_SHARER_KEY);
      }
    }
    onScopeChange({ ...scope, sharerNames: nextSharers });
  };

  const toggleSizeBand = (band: string): void => {
    const nextBands = new Set(scope.sizeBands);
    if (nextBands.has(band)) {
      nextBands.delete(band);
    } else {
      nextBands.add(band);
    }
    onScopeChange({ ...scope, sizeBands: nextBands });
  };

  const handleApply = (): void => {
    if (selectedCount > 0) {
      onApplyMatching("add");
      return;
    }
    onApplyMatching("replace");
  };

  if (collapsed) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          {matchingOrgs.length.toLocaleString()} companies match current filters
        </span>
        {onToggleCollapsed ? (
          <Button
            type="button"
            variant="link"
            className="h-auto p-0 text-xs"
            onClick={onToggleCollapsed}
          >
            Edit filters
          </Button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-4 rounded-md border bg-muted/20 p-3">
      <div className="space-y-2">
        <Label className="text-xs font-medium">Industries</Label>
        <p className="text-[11px] text-muted-foreground">
          Leave empty to include all industries.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {INDUSTRY_SCOPE_PRESETS.map((preset) => {
            const selected: boolean = selectedPresetIds.has(preset.id);
            return (
              <button
                key={preset.id}
                type="button"
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                  selected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-background hover:bg-muted",
                )}
                onClick={() => togglePreset(preset.id)}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-xs font-medium">Graph sources</Label>
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 rounded border"
              checked={scope.sharerNames.has(MINE_SHARER_KEY)}
              onChange={(event) =>
                toggleSharer(MINE_SHARER_KEY, event.target.checked)
              }
            />
            My network
          </label>
          {availableSharers.map((sharerName) => (
            <label key={sharerName} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 rounded border"
                checked={scope.sharerNames.has(sharerName)}
                onChange={(event) =>
                  toggleSharer(sharerName, event.target.checked)
                }
              />
              {sharerName}&apos;s contacts
            </label>
          ))}
        </div>
      </div>

      {availableSizeBands.length > 0 ? (
        <div className="space-y-2">
          <Label className="text-xs font-medium">Company size</Label>
          <div className="flex flex-wrap gap-1.5">
            {availableSizeBands.map((band) => {
              const selected: boolean = scope.sizeBands.has(band);
              return (
                <button
                  key={band}
                  type="button"
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                    selected
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-background hover:bg-muted",
                  )}
                  onClick={() => toggleSizeBand(band)}
                >
                  {formatCompanySize(band, null)}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm">
          <span className="font-medium">{matchingOrgs.length.toLocaleString()}</span>{" "}
          {matchingOrgs.length === 1 ? "company" : "companies"} in your network match
          {selectedCount > 0 ? (
            <Badge variant="secondary" className="ml-2">
              {selectedCount.toLocaleString()} selected
            </Badge>
          ) : null}
        </p>
        <Button
          type="button"
          size="sm"
          disabled={matchingOrgs.length === 0 || applyPending}
          onClick={handleApply}
        >
          {selectedCount > 0 ? "Add matching companies" : "Use matching companies"}
        </Button>
        {selectedCount > 0 ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={matchingOrgs.length === 0 || applyPending}
            onClick={() => onApplyMatching("replace")}
          >
            Replace with matching
          </Button>
        ) : null}
      </div>
    </div>
  );
}
