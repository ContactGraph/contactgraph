"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight, Copy, Loader2, MessageSquare } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { NextStepContactCandidate, NextStepItem } from "@/lib/api-types";
import { cn } from "@/lib/utils";
import { useNextSteps } from "@/lib/use-next-steps";

function normalizePhoneForSms(phone: string): string {
  return phone.replace(/[^\d+]/g, "");
}

function buildSmsHref(phone: string, body: string): string {
  const normalized: string = normalizePhoneForSms(phone);
  const encodedBody: string = encodeURIComponent(body);
  return `sms:${normalized}?&body=${encodedBody}`;
}

function OutreachTaskDetails({
  task,
  message,
  onMessageChange,
}: {
  task: NextStepItem;
  message: string;
  onMessageChange: (value: string) => void;
}) {
  const isBridge: boolean = task.payload.outreach_type === "bridge";
  const contacts: NextStepContactCandidate[] = task.payload.contacts;
  const bridgeName: string | null = task.payload.bridge_name;
  const bridgePhone: string | null = task.payload.bridge_phone;
  const targetName: string | null = task.payload.target_contact_name;
  const composePhone: string | null = isBridge ? bridgePhone : contacts[0]?.phone ?? null;

  const handleCopy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(message);
      toast.success("Copied to clipboard");
    } catch {
      toast.error("Could not copy message");
    }
  };

  const handleCompose = (): void => {
    if (composePhone === null || composePhone === undefined) {
      void handleCopy();
      toast.message("No phone number on file — message copied instead");
      return;
    }
    window.location.href = buildSmsHref(composePhone, message);
  };

  return (
    <div className="space-y-4 border-t border-border pt-4">
      {isBridge && bridgeName !== null && targetName !== null ? (
        <p className="text-sm text-muted-foreground">
          Ask{" "}
          <span className="font-medium text-foreground">{bridgeName}</span> to
          introduce you to{" "}
          <span className="font-medium text-foreground">{targetName}</span>
          {task.payload.org_name ? ` at ${task.payload.org_name}` : null}.
          {bridgePhone ? ` · ${bridgePhone}` : " · no phone"}
        </p>
      ) : null}

      {contacts.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {isBridge ? "People at this company" : "Suggested contacts"}
          </p>
          <ul className="space-y-1">
            {contacts.map((contact) => (
              <li
                key={contact.person_id}
                className="text-sm text-muted-foreground"
              >
                <span className="font-medium text-foreground">
                  {contact.display_name}
                </span>
                {contact.current_role ? ` · ${contact.current_role}` : null}
                {!isBridge && contact.phone ? ` · ${contact.phone}` : null}
                {!isBridge && !contact.phone ? " · no phone" : null}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          No contacts at this company in your graph yet.
        </p>
      )}

      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Proposed message
        </p>
        <textarea
          value={message}
          onChange={(event) => onMessageChange(event.target.value)}
          rows={4}
          className="w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm"
        />
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => void handleCopy()}>
            <Copy className="size-4" />
            Copy
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={handleCompose}>
            <MessageSquare className="size-4" />
            Start composing
          </Button>
          {task.payload.job_url ? (
            <Button type="button" variant="ghost" size="sm" asChild>
              <a href={task.payload.job_url} target="_blank" rel="noopener noreferrer">
                View job posting
              </a>
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function TaskCard({
  task,
  expanded,
  onToggle,
  onDone,
  onSkip,
  busy,
}: {
  task: NextStepItem;
  expanded: boolean;
  onToggle: () => void;
  onDone: () => void;
  onSkip: () => void;
  busy: boolean;
}) {
  const defaultMessage: string = task.payload.proposed_message ?? "";
  const [message, setMessage] = useState<string>(defaultMessage);
  const isOutreach: boolean = task.kind === "job_outreach";

  return (
    <Card>
      <CardHeader className="gap-3 pb-3">
        <div className="flex items-start justify-between gap-3">
          <button
            type="button"
            className="flex min-w-0 flex-1 items-start gap-2 text-left"
            onClick={onToggle}
          >
            <ChevronRight
              className={cn(
                "mt-1 size-4 shrink-0 text-muted-foreground transition-transform",
                expanded ? "rotate-90" : "",
              )}
            />
            <div className="min-w-0 space-y-1">
              <CardTitle className="text-base leading-snug">{task.title}</CardTitle>
              {task.detail ? (
                <CardDescription>{task.detail}</CardDescription>
              ) : null}
            </div>
          </button>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              type="button"
              size="sm"
              disabled={busy}
              onClick={onDone}
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : "Done"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={onSkip}
            >
              Skip
            </Button>
          </div>
        </div>
      </CardHeader>
      {expanded ? (
        <CardContent className="pt-0">
          {isOutreach ? (
            <OutreachTaskDetails
              task={task}
              message={message}
              onMessageChange={setMessage}
            />
          ) : (
            <div className="space-y-3 border-t border-border pt-4">
              {task.payload.unreviewed_job_count !== null ? (
                <p className="text-sm text-muted-foreground">
                  {task.payload.unreviewed_job_count} job
                  {task.payload.unreviewed_job_count === 1 ? "" : "s"} still need
                  your review.
                </p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {task.payload.action_links.map((link) => (
                  <Button key={link.href} variant="outline" size="sm" asChild>
                    <Link href={link.href}>{link.label}</Link>
                  </Button>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      ) : null}
    </Card>
  );
}

export default function HomePage() {
  const {
    data,
    isLoading,
    updateTaskStatus,
    isUpdatingTask,
  } = useNextSteps();
  const [expandedKeys, setExpandedKeys] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const [pendingKey, setPendingKey] = useState<string | null>(null);

  const tasks: NextStepItem[] = data?.tasks ?? [];

  const toggleExpanded = (dedupKey: string): void => {
    setExpandedKeys((current) => {
      const next = new Set(current);
      if (next.has(dedupKey)) {
        next.delete(dedupKey);
      } else {
        next.add(dedupKey);
      }
      return next;
    });
  };

  const handleStatus = async (
    dedupKey: string,
    status: "done" | "skipped",
  ): Promise<void> => {
    setPendingKey(dedupKey);
    try {
      await updateTaskStatus({ dedup_key: dedupKey, status });
    } finally {
      setPendingKey(null);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Next steps</h1>
        <p className="text-sm text-muted-foreground">
          Recommended actions to make progress on your job search.
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : tasks.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">All caught up</CardTitle>
            <CardDescription>
              {data?.message ?? "No open tasks right now."}
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <TaskCard
              key={task.dedup_key}
              task={task}
              expanded={expandedKeys.has(task.dedup_key)}
              onToggle={() => toggleExpanded(task.dedup_key)}
              onDone={() => void handleStatus(task.dedup_key, "done")}
              onSkip={() => void handleStatus(task.dedup_key, "skipped")}
              busy={isUpdatingTask && pendingKey === task.dedup_key}
            />
          ))}
        </div>
      )}
    </div>
  );
}
