"use client";

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
import type { ListOrgJobsResult } from "@/lib/api-types";
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

export default function JobsPage() {
  const jobsQuery = useQuery({
    queryKey: ["org-jobs"],
    queryFn: () => proxyPost<ListOrgJobsResult>("list-org-jobs"),
  });

  const loading: boolean = jobsQuery.isLoading;

  return (
    <div className="mx-auto max-w-4xl space-y-8 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Open jobs</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Roles discovered at your monitored target companies.
          </p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/setup">Job monitor settings</Link>
        </Button>
      </div>

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : jobsQuery.isFetching ? (
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      ) : null}

      {jobsQuery.data?.message ? (
        <Alert>
          <AlertDescription>{jobsQuery.data.message}</AlertDescription>
        </Alert>
      ) : null}

      {(jobsQuery.data?.companies.length ?? 0) === 0 ? (
        <p className="text-sm text-muted-foreground">
          No jobs yet. Select target companies in Setup and run job discovery.
        </p>
      ) : (
        jobsQuery.data?.companies.map((company) => (
          <section key={company.org_id} className="space-y-3">
            <h2 className="flex items-center gap-2 text-lg font-medium">
              <Briefcase className="h-5 w-5" />
              {company.org_name}
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
                      <Badge variant="secondary">{job.source}</Badge>
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
