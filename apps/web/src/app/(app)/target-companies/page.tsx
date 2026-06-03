"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2, Loader2, Users } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  SecondDegreeTargetCompaniesResult,
  TargetCompaniesResult,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";

function trustLabel(score: number): string {
  return `${Math.round(score * 100)}% trust`;
}

export default function TargetCompaniesPage() {
  const firstDegreeQuery = useQuery({
    queryKey: ["target-companies"],
    queryFn: () => proxyPost<TargetCompaniesResult>("/get-target-companies", {}),
  });

  const secondDegreeQuery = useQuery({
    queryKey: ["second-degree-target-companies"],
    queryFn: () =>
      proxyPost<SecondDegreeTargetCompaniesResult>(
        "/get-second-degree-target-companies",
        {},
      ),
  });

  const loading: boolean =
    firstDegreeQuery.isLoading || secondDegreeQuery.isLoading;

  return (
    <div className="mx-auto max-w-4xl space-y-8 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Target companies
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Companies where you have high-trust connections who currently work
          there — useful for trusted outreach during a job search.
        </p>
      </div>

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : (
        <>
          {(firstDegreeQuery.data?.message ||
            secondDegreeQuery.data?.message) && (
            <Alert>
              <AlertDescription>
                {firstDegreeQuery.data?.message}
                {secondDegreeQuery.data?.message &&
                secondDegreeQuery.data.companies.length > 0
                  ? ` ${secondDegreeQuery.data.message}`
                  : null}
              </AlertDescription>
            </Alert>
          )}

          <section className="space-y-4">
            <h2 className="flex items-center gap-2 text-lg font-medium">
              <Building2 className="h-5 w-5" />
              Your network
            </h2>
            {(firstDegreeQuery.data?.companies.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground">
                No high-trust companies yet. Import phone contacts and enrich
                your graph to discover where your close connections work today.
              </p>
            ) : (
              firstDegreeQuery.data?.companies.map((company) => (
                <Card key={company.org_id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <CardTitle className="text-base">
                          {company.org_name}
                        </CardTitle>
                        <CardDescription>
                          {company.insiders.length} high-trust connection
                          {company.insiders.length === 1 ? "" : "s"}
                        </CardDescription>
                      </div>
                      <Badge variant="secondary">
                        {trustLabel(company.best_trust_score)}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {company.insiders.map((insider) => (
                      <div
                        key={insider.person_id}
                        className="flex items-center justify-between text-sm"
                      >
                        <div>
                          <span className="font-medium">
                            {insider.person_name}
                          </span>
                          {insider.person_role ? (
                            <span className="text-muted-foreground">
                              {" "}
                              · {insider.person_role}
                            </span>
                          ) : null}
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {trustLabel(insider.trust_score)}
                          {insider.relationship_kind
                            ? ` · ${insider.relationship_kind.replace("_", " ")}`
                            : ""}
                        </span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ))
            )}
          </section>

          <section className="space-y-4">
            <h2 className="flex items-center gap-2 text-lg font-medium">
              <Users className="h-5 w-5" />
              Via trusted friends
            </h2>
            {secondDegreeQuery.isFetching ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : null}
            {(secondDegreeQuery.data?.companies.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground">
                Invite close friends to ContactGraph on your Trust List to see
                second-degree companies and who can make the intro.
              </p>
            ) : (
              secondDegreeQuery.data?.companies.map((company) => (
                <Card key={`2nd-${company.org_id}`}>
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <CardTitle className="text-base">
                          {company.org_name}
                        </CardTitle>
                        <CardDescription>Second-degree reach</CardDescription>
                      </div>
                      <Badge variant="outline">
                        {trustLabel(company.best_trust_score)}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {company.insiders.map((insider) => (
                      <div
                        key={`${insider.person_id}-${insider.bridge_user_id}`}
                        className="text-sm"
                      >
                        <span className="font-medium">{insider.person_name}</span>
                        {insider.person_role ? (
                          <span className="text-muted-foreground">
                            {" "}
                            · {insider.person_role}
                          </span>
                        ) : null}
                        <div className="text-xs text-muted-foreground">
                          Ask {insider.bridge_name} for an intro ·{" "}
                          {trustLabel(insider.trust_score)}
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ))
            )}
          </section>
        </>
      )}
    </div>
  );
}
