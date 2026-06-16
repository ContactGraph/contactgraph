"use client";

import { useEffect, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useNextSteps } from "@/lib/use-next-steps";

export function JobInterestButtons({
  jobId,
  userInterest,
  compact = false,
  onChanged,
}: {
  jobId: string;
  userInterest: "interested" | "dismissed" | null;
  compact?: boolean;
  onChanged?: (interest: "interested" | "dismissed") => void;
}) {
  const { setJobInterest } = useNextSteps();
  const [optimistic, setOptimistic] = useState<"interested" | "dismissed" | null>(null);

  useEffect(() => {
    if (optimistic !== null && userInterest === optimistic) {
      setOptimistic(null);
    }
  }, [userInterest, optimistic]);

  const displayed: "interested" | "dismissed" | null = optimistic ?? userInterest;

  const handleInterest = async (
    interest: "interested" | "dismissed",
  ): Promise<void> => {
    setOptimistic(interest);
    onChanged?.(interest);
    try {
      await setJobInterest({ job_id: jobId, interest });
    } catch {
      setOptimistic(null);
    }
  };

  const iconClass: string = compact ? "size-3.5" : "size-4";
  const buttonClass: string = compact ? "size-7" : "size-8";

  return (
    <div
      className="flex items-center gap-1"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <Button
        type="button"
        variant={displayed === "interested" ? "default" : "outline"}
        size="icon"
        className={cn(buttonClass, "shrink-0")}
        aria-label="Interested in this job"
        onClick={() => void handleInterest("interested")}
      >
        <ThumbsUp className={iconClass} />
      </Button>
      <Button
        type="button"
        variant={displayed === "dismissed" ? "default" : "outline"}
        size="icon"
        className={cn(buttonClass, "shrink-0")}
        aria-label="Not interested in this job"
        onClick={() => void handleInterest("dismissed")}
      >
        <ThumbsDown className={iconClass} />
      </Button>
    </div>
  );
}
