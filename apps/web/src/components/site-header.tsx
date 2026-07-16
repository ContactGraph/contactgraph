"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import type { UserProfileResult, ViewTrustedUsersResult } from "@/lib/api-types";
import { useOnboardingPhase } from "@/lib/use-onboarding-phase";
import { proxyPost } from "@/lib/proxy-client";
import { cn } from "@/lib/utils";

const API_BASE = "https://api.contactgraph.ai";
const GITHUB_OWNER = "ContactGraph";
const GITHUB_REPO = "contactgraph";
const GITHUB_REPO_URL = `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}`;

function formatStarCount(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}k`;
  return count.toString();
}

function GitHubStarBadge(): React.ReactElement {
  const starQuery = useQuery<number>({
    queryKey: ["github-stars", GITHUB_OWNER, GITHUB_REPO],
    queryFn: async (): Promise<number> => {
      const res: Response = await fetch(
        `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}`,
        { headers: { Accept: "application/vnd.github.v3+json" } },
      );
      if (!res.ok) throw new Error(`GitHub API ${res.status}`);
      const data: { stargazers_count: number } = await res.json();
      return data.stargazers_count;
    },
    staleTime: 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
    retry: 1,
  });

  return (
    <a
      href={GITHUB_REPO_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-sm text-muted-foreground no-underline transition-colors hover:bg-muted hover:text-foreground"
      aria-label={`Star ${GITHUB_OWNER}/${GITHUB_REPO} on GitHub`}
    >
      <svg
        viewBox="0 0 16 16"
        fill="currentColor"
        className="size-4"
        aria-hidden="true"
      >
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
      </svg>
      {starQuery.data !== undefined ? (
        <span className="flex items-center gap-1">
          <svg
            viewBox="0 0 16 16"
            fill="currentColor"
            className="size-3.5 text-yellow-500"
            aria-hidden="true"
          >
            <path d="M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z" />
          </svg>
          <span>{formatStarCount(starQuery.data)}</span>
        </span>
      ) : null}
    </a>
  );
}

type NavLink =
  | { kind: "internal"; href: string; label: string }
  | { kind: "external"; href: string; label: string };

const marketingLinks: readonly NavLink[] = [
  { kind: "internal", href: "/mcp", label: "MCP" },
  { kind: "external", href: `${API_BASE}/skill.md`, label: "Skill" },
  { kind: "internal", href: "/blog", label: "Blog" },
  { kind: "internal", href: "/manifesto", label: "Manifesto" },
];

export function SiteHeader({
  email,
  isAdmin = false,
}: {
  email: string | null;
  isAdmin?: boolean;
}) {
  const pathname: string = usePathname();
  const headerRef = useRef<HTMLElement>(null);
  const onboarding = useOnboardingPhase({ enabled: email !== null });

  const profileQuery = useQuery({
    queryKey: ["user-profile"],
    queryFn: () => proxyPost<UserProfileResult>("get-user-profile"),
    enabled: email !== null,
    staleTime: 5 * 60 * 1000,
  });

  const trustQuery = useQuery({
    queryKey: ["trust-list"],
    queryFn: () => proxyPost<ViewTrustedUsersResult>("view-trusted-users"),
    enabled: email !== null,
    staleTime: 60 * 1000,
  });

  const pendingInviteCount: number = trustQuery.data?.inbound_invites.length ?? 0;

  const appLinks: readonly NavLink[] = onboarding.showJobsTab
    ? [
        { kind: "internal", href: "/home", label: "Home" },
        { kind: "internal", href: "/graph", label: "Graph" },
        { kind: "internal", href: "/jobs", label: "Jobs" },
        { kind: "internal", href: "/sharing", label: "Sharing" },
        ...(isAdmin ? [{ kind: "internal" as const, href: "/admin", label: "Admin" }] : []),
      ]
    : [
        { kind: "internal", href: "/home", label: "Home" },
        { kind: "internal", href: "/graph", label: "Graph" },
        { kind: "internal", href: "/sharing", label: "Sharing" },
        ...(isAdmin ? [{ kind: "internal" as const, href: "/admin", label: "Admin" }] : []),
      ];

  const links: readonly NavLink[] = email ? appLinks : marketingLinks;

  const displayName: string =
    profileQuery.data?.display_name ??
    profileQuery.data?.google_profile_name ??
    email ??
    "";

  const profilePicture: string | null =
    profileQuery.data?.google_profile_picture ?? null;

  const initials: string = displayName
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]!.toUpperCase())
    .join("");

  useEffect(() => {
    const header: HTMLElement | null = headerRef.current;
    if (header === null) {
      return;
    }

    const updateHeight = (): void => {
      document.documentElement.style.setProperty(
        "--site-header-height",
        `${header.offsetHeight}px`,
      );
    };

    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(header);
    return () => {
      observer.disconnect();
    };
  }, []);

  const navLinkClass = (href: string): string =>
    cn(
      "text-sm no-underline hover:underline",
      pathname === href || pathname.startsWith(`${href}/`)
        ? "font-semibold text-foreground"
        : "text-muted-foreground",
    );

  return (
    <header
      ref={headerRef}
      className="sticky top-0 z-40 border-b border-border bg-background"
    >
      <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4 px-4 py-2 sm:px-6 sm:py-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-4 sm:gap-6">
          <Link
            href="/"
            className="flex items-center gap-2 text-lg font-bold tracking-tight text-foreground no-underline hover:no-underline hover:opacity-80"
          >
            <img
              src="/logomark.svg"
              alt=""
              className="size-7 dark:invert"
              aria-hidden="true"
            />
            ContactGraph
          </Link>
          <nav
            className="hidden items-center gap-4 md:flex"
            aria-label="Primary navigation"
          >
            {links.map((item) =>
              item.kind === "internal" ? (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(navLinkClass(item.href), "relative")}
                >
                  {item.label}
                  {item.href === "/sharing" && pendingInviteCount > 0 ? (
                    <span className="absolute -right-2.5 -top-1.5 flex size-4 items-center justify-center rounded-full bg-primary text-[10px] font-medium text-primary-foreground">
                      {pendingInviteCount}
                    </span>
                  ) : null}
                </Link>
              ) : (
                <a
                  key={item.href}
                  href={item.href}
                  className="text-sm text-muted-foreground no-underline hover:underline"
                >
                  {item.label}
                </a>
              ),
            )}
          </nav>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-sm">
          <GitHubStarBadge />
          {email ? (
            <Link
              href="/profile"
              className="flex items-center rounded-full no-underline hover:opacity-80"
              title={displayName}
            >
              {profilePicture !== null ? (
                <img
                  src={profilePicture}
                  alt={displayName}
                  className="size-7 rounded-full object-cover"
                  referrerPolicy="no-referrer"
                />
              ) : (
                <span className="flex size-7 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground">
                  {initials}
                </span>
              )}
            </Link>
          ) : (
            <Link href="/login" className="no-underline hover:underline">
              Sign In
            </Link>
          )}
        </div>
      </div>
      <nav
        className="flex gap-4 overflow-x-auto border-t border-border px-4 py-1.5 md:hidden"
        aria-label="Primary navigation"
      >
        {links.map((item) =>
          item.kind === "internal" ? (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "relative whitespace-nowrap text-sm no-underline hover:underline",
                pathname === item.href
                  ? "font-semibold text-foreground"
                  : "text-muted-foreground",
              )}
            >
              {item.label}
              {item.href === "/sharing" && pendingInviteCount > 0 ? (
                <span className="absolute -right-2.5 -top-1.5 flex size-4 items-center justify-center rounded-full bg-primary text-[10px] font-medium text-primary-foreground">
                  {pendingInviteCount}
                </span>
              ) : null}
            </Link>
          ) : (
            <a
              key={item.href}
              href={item.href}
              className="whitespace-nowrap text-sm text-muted-foreground no-underline hover:underline"
            >
              {item.label}
            </a>
          ),
        )}
      </nav>
    </header>
  );
}
