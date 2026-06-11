"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { GraphSetupCards } from "@/components/setup/graph-setup-cards";
import { GraphSettingsButton } from "@/components/setup/graph-settings-modal";
import { OrganizationsView } from "@/components/views/organizations-view";
import { PeopleView } from "@/components/views/people-view";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import type { ViewTrustedUsersResult } from "@/lib/api-types";
import { useOnboardingPhase } from "@/lib/use-onboarding-phase";
import { proxyPost } from "@/lib/proxy-client";
import { cn } from "@/lib/utils";

type GraphTab = "people" | "organizations";

function parseGraphTab(value: string | null): GraphTab {
  return value === "organizations" ? "organizations" : "people";
}

export default function GraphPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const onboarding = useOnboardingPhase();
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const activeTab: GraphTab = parseGraphTab(searchParams.get("tab"));
  const viewingFilter: string = searchParams.get("viewing") ?? "mine";

  const trustQuery = useQuery({
    queryKey: ["trust-list"],
    queryFn: () => proxyPost<ViewTrustedUsersResult>("view-trusted-users"),
    staleTime: 60 * 1000,
  });

  const availableSharers: string[] = useMemo(() => {
    const members = trustQuery.data?.members ?? [];
    return members
      .map((m) => m.name ?? m.email)
      .sort();
  }, [trustQuery.data?.members]);

  const setActiveTab = (tab: GraphTab): void => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    router.replace(`/graph?${params.toString()}`);
  };

  const setViewingFilter = (value: string): void => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === "mine") {
      params.delete("viewing");
    } else {
      params.set("viewing", value);
    }
    router.replace(`/graph?${params.toString()}`);
  };

  if (onboarding.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (onboarding.phase === "graph-setup") {
    return <GraphSetupCards />;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Graph</h1>
          <p className="text-sm text-muted-foreground">
            Browse people and organizations in your network.
          </p>
        </div>
        <GraphSettingsButton open={settingsOpen} onOpenChange={setSettingsOpen} />
      </div>

      <div className="flex items-center gap-3">
        <div className="inline-flex items-center rounded-md border text-sm h-8 overflow-hidden">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={cn(
              "rounded-none border-0 h-full",
              activeTab === "people" && "bg-muted font-medium",
            )}
            onClick={() => setActiveTab("people")}
          >
            People
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={cn(
              "rounded-none border-0 border-l h-full",
              activeTab === "organizations" && "bg-muted font-medium",
            )}
            onClick={() => setActiveTab("organizations")}
          >
            Organizations
          </Button>
        </div>

        {availableSharers.length > 0 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-8 text-xs">
                {viewingFilter === "all"
                  ? "All contacts"
                  : viewingFilter === "mine"
                    ? "My contacts"
                    : `${viewingFilter}'s contacts`}
                <ChevronDown className="ml-1 size-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuRadioGroup value={viewingFilter} onValueChange={setViewingFilter}>
                <DropdownMenuRadioItem value="mine">My contacts</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="all">All contacts</DropdownMenuRadioItem>
                {availableSharers.map((name) => (
                  <DropdownMenuRadioItem key={name} value={name}>
                    {name}&rsquo;s contacts
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>

      {activeTab === "organizations" ? (
        <OrganizationsView embedded viewingFilter={viewingFilter} />
      ) : (
        <PeopleView embedded viewingFilter={viewingFilter} />
      )}
    </div>
  );
}
