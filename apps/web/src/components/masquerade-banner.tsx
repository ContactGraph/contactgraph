"use client";

import { AlertTriangle } from "lucide-react";
import { useState } from "react";

export function MasqueradeBanner({ masqueradeAs }: { masqueradeAs: string }) {
  const [isExiting, setIsExiting] = useState<boolean>(false);

  const handleExit = async (): Promise<void> => {
    setIsExiting(true);
    try {
      const response: Response = await fetch("/api/auth/masquerade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "stop" }),
      });

      if (!response.ok) {
        setIsExiting(false);
        return;
      }

      window.location.reload();
    } catch {
      setIsExiting(false);
    }
  };

  return (
    <div className="border-b border-amber-300 bg-amber-100 px-4 py-2 text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
      <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />
          <span className="truncate">
            Viewing as <strong>{masqueradeAs}</strong>
          </span>
        </div>
        <button
          type="button"
          onClick={() => {
            void handleExit();
          }}
          disabled={isExiting}
          className="shrink-0 rounded-md border border-amber-400 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-950 hover:bg-amber-200 disabled:opacity-50 dark:border-amber-600 dark:bg-amber-900 dark:text-amber-50 dark:hover:bg-amber-800"
        >
          {isExiting ? "Exiting..." : "Exit"}
        </button>
      </div>
    </div>
  );
}
