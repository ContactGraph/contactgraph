"use client";

import { useQuery } from "@tanstack/react-query";

import { PipelineDonut } from "@/components/admin/pipeline-donut";
import type {
  AdminUserItem,
  AdminUsersResult,
  PipelineStatus,
  WorkerStatusResult,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";

const PIPELINE_LABELS: Record<string, string> = {
  org_enrichment: "Org enrichment",
  job_discovery: "Job discovery",
  job_scoring: "Job scoring",
};

function formatRelativeTime(iso: string | null): string {
  if (iso === null) {
    return "Never";
  }
  const date: Date = new Date(iso);
  const diffMs: number = Date.now() - date.getTime();
  const diffMinutes: number = Math.floor(diffMs / 60000);
  if (diffMinutes < 1) {
    return "Just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const diffHours: number = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays: number = Math.floor(diffHours / 24);
  if (diffDays < 7) {
    return `${diffDays}d ago`;
  }
  return date.toLocaleDateString();
}

function PipelineCard({ pipeline }: { pipeline: PipelineStatus }) {
  const label: string = PIPELINE_LABELS[pipeline.name] ?? pipeline.name;
  const processed: number = pipeline.items_processed ?? 0;
  const total: number = pipeline.items_total ?? 0;

  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <PipelineDonut
        label={label}
        processed={processed}
        total={total}
        failed={pipeline.failed_24h}
      />
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <div>
          <dt className="text-muted-foreground">Queued</dt>
          <dd className="font-medium">{pipeline.queued}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Active</dt>
          <dd className="font-medium">{pipeline.active}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Completed (24h)</dt>
          <dd className="font-medium">{pipeline.completed_24h}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Failed (24h)</dt>
          <dd className="font-medium">{pipeline.failed_24h}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-muted-foreground">Last run</dt>
          <dd className="font-medium">
            {formatRelativeTime(pipeline.last_run_at)}
            {pipeline.last_run_duration_ms !== null
              ? ` (${Math.round(pipeline.last_run_duration_ms / 1000)}s)`
              : null}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function Badge({ active, label }: { active: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        active
          ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
          : "bg-muted text-muted-foreground"
      }`}
    >
      {label}
    </span>
  );
}

function UsersTable({ users }: { users: AdminUserItem[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/50 text-left text-xs font-medium text-muted-foreground">
            <th className="px-4 py-2">User</th>
            <th className="px-4 py-2">Sources</th>
            <th className="px-4 py-2 text-right">People</th>
            <th className="px-4 py-2 text-right">Orgs</th>
            <th className="px-4 py-2">First seen</th>
            <th className="px-4 py-2">Last seen</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.user_id} className="border-b border-border last:border-0">
              <td className="px-4 py-2">
                <div className="font-medium">{user.display_name ?? user.email}</div>
                {user.display_name ? (
                  <div className="text-xs text-muted-foreground">{user.email}</div>
                ) : null}
              </td>
              <td className="px-4 py-2">
                <div className="flex gap-1.5">
                  <Badge active={user.has_vcf} label="VCF" />
                  <Badge active={user.has_linkedin} label="LinkedIn" />
                </div>
              </td>
              <td className="px-4 py-2 text-right tabular-nums">
                {user.person_count.toLocaleString()}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">
                {user.org_count.toLocaleString()}
              </td>
              <td className="px-4 py-2 text-muted-foreground">
                {formatRelativeTime(user.first_seen_at)}
              </td>
              <td className="px-4 py-2 text-muted-foreground">
                {formatRelativeTime(user.last_seen_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AdminDashboard() {
  const statusQuery = useQuery({
    queryKey: ["admin-worker-status"],
    queryFn: () => proxyPost<WorkerStatusResult>("admin/worker-status"),
    refetchInterval: 5000,
  });

  const usersQuery = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => proxyPost<AdminUsersResult>("admin/users"),
    refetchInterval: 30000,
  });

  const status: WorkerStatusResult | undefined = statusQuery.data;
  const usersData: AdminUsersResult | undefined = usersQuery.data;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
        <p className="text-sm text-muted-foreground">
          Background worker status for org enrichment, job discovery, and scoring.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4 text-sm">
        <div className="flex items-center gap-2">
          <span
            className={`size-2.5 rounded-full ${status?.worker_connected ? "bg-emerald-500" : "bg-destructive"}`}
          />
          Worker {status?.worker_connected ? "connected" : "offline"}
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`size-2.5 rounded-full ${status?.redis_connected ? "bg-emerald-500" : "bg-destructive"}`}
          />
          Redis {status?.redis_connected ? "connected" : "offline"}
        </div>
        {status?.message ? (
          <span className="text-muted-foreground">{status.message}</span>
        ) : null}
      </div>

      {statusQuery.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading worker status…</p>
      ) : null}
      {statusQuery.isError ? (
        <p className="text-sm text-destructive">
          {statusQuery.error instanceof Error
            ? statusQuery.error.message
            : "Failed to load worker status"}
        </p>
      ) : null}

      {status ? (
        <div className="grid gap-4 md:grid-cols-3">
          {status.pipelines.map((pipeline) => (
            <PipelineCard key={pipeline.name} pipeline={pipeline} />
          ))}
        </div>
      ) : null}

      <div className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Users</h2>
        {usersQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading users…</p>
        ) : null}
        {usersQuery.isError ? (
          <p className="text-sm text-destructive">Failed to load users</p>
        ) : null}
        {usersData && usersData.users.length > 0 ? (
          <UsersTable users={usersData.users} />
        ) : null}
        {usersData && usersData.users.length === 0 ? (
          <p className="text-sm text-muted-foreground">No users found.</p>
        ) : null}
      </div>
    </div>
  );
}
