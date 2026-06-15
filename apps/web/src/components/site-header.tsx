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
const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";

type NavLink =
  | { kind: "internal"; href: string; label: string }
  | { kind: "external"; href: string; label: string };

const marketingLinks: readonly NavLink[] = [
  { kind: "external", href: `${API_BASE}/skill.md`, label: "Skill" },
  { kind: "external", href: `${API_BASE}/mcp`, label: "MCP" },
  { kind: "external", href: GITHUB_REPO_URL, label: "GitHub" },
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
  const onboarding = useOnboardingPhase();

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
        { kind: "internal", href: "/graph", label: "Graph" },
        { kind: "internal", href: "/jobs", label: "Jobs" },
        { kind: "internal", href: "/sharing", label: "Sharing" },
        ...(isAdmin ? [{ kind: "internal" as const, href: "/admin", label: "Admin" }] : []),
      ]
    : [
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
          {email ? (
            <>
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
            </>
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
