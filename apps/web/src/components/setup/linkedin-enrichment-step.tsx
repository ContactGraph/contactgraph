"use client";

import Link from "next/link";
import { Building2, Loader2, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  NetworkStatusResult,
  ScrapingDogEnrichmentStatusResult,
} from "@/lib/api-types";

interface LinkedInEnrichmentStepProps {
  networkStatus: NetworkStatusResult | undefined;
  enrichmentStatus: ScrapingDogEnrichmentStatusResult | undefined;
  isLoading: boolean;
  isPending: boolean;
  onEnrich: () => void;
}

export function LinkedInEnrichmentStep({
  networkStatus,
  enrichmentStatus,
  isLoading,
  isPending,
  onEnrich,
}: LinkedInEnrichmentStepProps) {
  const visible: boolean = (networkStatus?.strong_tie_count ?? 0) > 0;
  const running: boolean =
    enrichmentStatus?.state === "running" || isPending;
  const complete: boolean =
    enrichmentStatus?.state === "complete" ||
    enrichmentStatus?.state === "partial";
  const strongTieCount: number = networkStatus?.strong_tie_count ?? 0;
  const enrichedCount: number =
    enrichmentStatus?.enriched_count ??
    networkStatus?.enriched_strong_tie_count ??
    0;
  const companyCount: number = networkStatus?.target_company_count ?? 0;

  if (!visible) {
    return null;
  }

  const progressTotal: number = enrichmentStatus?.total ?? strongTieCount;
  const progressDone: number = Math.max(
    enrichmentStatus?.complete ?? 0,
    enrichedCount,
  );

  return (
    <div className="rounded-lg border bg-muted/20 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Building2 className="size-5 text-primary" />
            <p className="font-medium">Discover where they work</p>
            {complete ? <Badge variant="secondary">Enriched</Badge> : null}
          </div>
          <p className="text-sm text-muted-foreground">
            Scrape LinkedIn profiles for your strong professional ties to find current employers.
          </p>
          {running ? (
            <p className="text-xs text-muted-foreground">
              Enriching {progressDone} of {progressTotal} strong professional ties…
            </p>
          ) : complete ? (
            <p className="text-xs text-muted-foreground">
              {enrichedCount} strong professional ties enriched
              {companyCount > 0
                ? ` · they work at ${companyCount} companies`
                : ""}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              {strongTieCount} strong professional ties ready for LinkedIn enrichment.
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            onClick={onEnrich}
            disabled={isLoading || running || strongTieCount === 0}
          >
            {running ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            {running ? "Enriching…" : complete ? "Re-enrich" : "Enrich LinkedIn profiles"}
          </Button>
          {companyCount > 0 ? (
            <Button asChild variant="outline" size="sm">
              <Link href="/target-companies">View target companies</Link>
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
