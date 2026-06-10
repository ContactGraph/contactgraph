"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ExternalLink, Loader2 } from "lucide-react";
import Link from "next/link";

import { JobSetupCards } from "@/components/setup/job-setup-cards";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ListOrgJobsResult, OrgJobItem } from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";
import { useOnboardingPhase } from "@/lib/use-onboarding-phase";

function formatSalary(min: number | null, max: number | null): string | null {
  if (min === null && max === null) {
    return null;
  }
  if (min !== null && max !== null) {
    return `$${min.toLocaleString()} – $${max.toLocaleString()}`;
  }
  if (min !== null) {
    return `$${min.toLocaleString()}+`;
  }
  return `Up to $${max!.toLocaleString()}`;
}

function hasRelevanceData(data: ListOrgJobsResult | undefined): boolean {
  if (!data) return false;
  return data.companies.some((c) =>
    c.jobs.some((j) => j.is_relevant !== null),
  );
}

function JobsListings() {
  const [showAll, setShowAll] = useState<boolean>(false);

  const jobsQuery = useQuery({
    queryKey: ["org-jobs"],
    queryFn: () => proxyPost<ListOrgJobsResult>("list-org-jobs"),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data !== undefined && data.total_jobs === 0 ? 5000 : false;
    },
  });

  const data: ListOrgJobsResult | undefined = jobsQuery.data;
  const loading: boolean = jobsQuery.isLoading;
  const hasRelevance: boolean = hasRelevanceData(data);

  const filteredCompanies = (data?.companies ?? [])
    .map((company) => {
      const jobs: OrgJobItem[] =
        !hasRelevance || showAll
          ? company.jobs
          : company.jobs.filter((j) => j.is_relevant !== false);
      return { ...company, jobs };
    })
    .filter((company) => company.jobs.length > 0);

  const totalShown: number = filteredCompanies.reduce(
    (acc, c) => acc + c.jobs.length,
    0,
  );

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Open jobs</h1>
          <p className="text-xs text-muted-foreground">
            {loading
              ? "Loading…"
              : `${totalShown} of ${data?.total_jobs ?? 0} shown`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasRelevance ? (
            <div className="inline-flex items-center rounded-md border text-xs">
              <button
                type="button"
                className={`rounded-l-md px-3 py-1.5 transition-colors ${
                  !showAll
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted"
                }`}
                onClick={() => setShowAll(false)}
              >
                Relevant ({data?.total_relevant ?? 0})
              </button>
              <button
                type="button"
                className={`rounded-r-md border-l px-3 py-1.5 transition-colors ${
                  showAll
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted"
                }`}
                onClick={() => setShowAll(true)}
              >
                All ({data?.total_jobs ?? 0})
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : jobsQuery.isFetching ? (
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      ) : null}

      {filteredCompanies.length === 0 && !loading ? (
        <p className="text-sm text-muted-foreground">
          No jobs yet. Job discovery runs automatically after setup completes.
        </p>
      ) : (
        filteredCompanies.map((company) => (
          <details key={company.org_id} className="group rounded-lg border">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 [&::-webkit-details-marker]:hidden">
              <div className="flex items-center gap-2">
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/graph?tab=organizations&org=${encodeURIComponent(company.org_id)}`}
                      className="font-medium text-primary hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {company.org_name}
                    </Link>
                    {company.primary_domain ? (
                      <span className="text-xs text-muted-foreground">
                        {company.primary_domain}
                      </span>
                    ) : null}
                  </div>
                  {company.description ? (
                    <p className="line-clamp-2 text-xs text-muted-foreground">
                      {company.description}
                    </p>
                  ) : null}
                </div>
              </div>
              <span className="shrink-0 text-xs text-muted-foreground">
                {company.jobs.length} job{company.jobs.length !== 1 ? "s" : ""}
              </span>
            </summary>
            <div className="space-y-3 border-t px-4 pb-4 pt-3">
              {company.jobs.map((job) => {
                const salary: string | null = formatSalary(
                  job.salary_min,
                  job.salary_max,
                );
                return (
                  <Card key={job.job_id}>
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <CardTitle className="text-base">{job.title}</CardTitle>
                          <CardDescription>
                            {[job.location, job.department, job.remote_status]
                              .filter(Boolean)
                              .join(" · ")}
                          </CardDescription>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {job.relevance_reason ? (
                            <Badge variant="outline" className="text-xs font-normal">
                              {job.relevance_reason}
                            </Badge>
                          ) : null}
                          <Badge variant="secondary">{job.source}</Badge>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {job.description_snippet ? (
                        <p className="text-sm text-muted-foreground">
                          {job.description_snippet}
                        </p>
                      ) : null}
                      {salary ? (
                        <p className="text-sm font-medium">{salary}</p>
                      ) : null}
                      <Button variant="link" className="h-auto p-0" asChild>
                        <a href={job.url} target="_blank" rel="noopener noreferrer">
                          View posting
                          <ExternalLink className="ml-1 size-3.5" />
                        </a>
                      </Button>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </details>
        ))
      )}
    </div>
  );
}

export default function JobsPage() {
  const onboarding = useOnboardingPhase();

  if (onboarding.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!onboarding.graphReady) {
    return (
      <div className="space-y-4">
        <Alert>
          <AlertDescription>
            Complete graph setup first — import phone contacts and LinkedIn
            connections on{" "}
            <Link href="/graph" className="font-medium underline">
              My Graph
            </Link>
            .
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (onboarding.phase === "job-setup") {
    return <JobSetupCards />;
  }

  return <JobsListings />;
}
