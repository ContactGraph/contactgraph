"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { GraphSetupCards } from "@/components/setup/graph-setup-cards";
import { GraphSettingsButton } from "@/components/setup/graph-settings-modal";
import { OrganizationsView } from "@/components/views/organizations-view";
import { PeopleView } from "@/components/views/people-view";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useOnboardingPhase } from "@/lib/use-onboarding-phase";
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

  const setActiveTab = (tab: GraphTab): void => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
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
          <h1 className="text-2xl font-semibold tracking-tight">My Graph</h1>
          <p className="text-sm text-muted-foreground">
            Browse people and organizations in your network.
          </p>
        </div>
        <GraphSettingsButton open={settingsOpen} onOpenChange={setSettingsOpen} />
      </div>

      <div className="inline-flex items-center rounded-md border text-sm">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn(
            "rounded-r-none",
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
            "rounded-l-none border-l",
            activeTab === "organizations" && "bg-muted font-medium",
          )}
          onClick={() => setActiveTab("organizations")}
        >
          Organizations
        </Button>
      </div>

      {activeTab === "organizations" ? (
        <OrganizationsView embedded />
      ) : (
        <PeopleView embedded />
      )}
    </div>
  );
}
