"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Briefcase, ExternalLink, Loader2 } from "lucide-react";
import Link from "next/link";

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

export default function JobsPage() {
  const [showAll, setShowAll] = useState<boolean>(false);

  const jobsQuery = useQuery({
    queryKey: ["org-jobs"],
    queryFn: () => proxyPost<ListOrgJobsResult>("list-org-jobs"),
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
  const totalHidden: number = (data?.total_jobs ?? 0) - totalShown;

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
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
                className={`px-3 py-1.5 rounded-l-md transition-colors ${
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
                className={`px-3 py-1.5 rounded-r-md border-l transition-colors ${
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
          <Button variant="outline" size="sm" className="h-8 text-xs" asChild>
            <Link href="/setup">Settings</Link>
          </Button>
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

      {data?.message && !loading ? (
        <Alert>
          <AlertDescription>{data.message}</AlertDescription>
        </Alert>
      ) : null}

      {filteredCompanies.length === 0 && !loading ? (
        <p className="text-sm text-muted-foreground">
          No jobs yet. Select target companies in Setup and run job discovery.
        </p>
      ) : (
        filteredCompanies.map((company) => (
          <section key={company.org_id} className="space-y-3">
            <h2 className="flex items-center gap-2 text-lg font-medium">
              <Briefcase className="h-5 w-5" />
              <Link
                href={`/organizations?org=${encodeURIComponent(company.org_id)}`}
                className="text-primary hover:underline"
              >
                {company.org_name}
              </Link>
              {company.primary_domain ? (
                <span className="text-sm font-normal text-muted-foreground">
                  {company.primary_domain}
                </span>
              ) : null}
            </h2>
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
                          {[
                            job.location,
                            job.department,
                            job.remote_status,
                          ]
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
          </section>
        ))
      )}
    </div>
  );
}
