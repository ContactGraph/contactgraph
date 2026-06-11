"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import type { UserProfileResult } from "@/lib/api-types";
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

export function SiteHeader({ email }: { email: string | null }) {
  const pathname: string = usePathname();
  const headerRef = useRef<HTMLElement>(null);
  const onboarding = useOnboardingPhase();

  const profileQuery = useQuery({
    queryKey: ["user-profile"],
    queryFn: () => proxyPost<UserProfileResult>("get-user-profile"),
    enabled: email !== null,
    staleTime: 5 * 60 * 1000,
  });

  const appLinks: readonly NavLink[] = onboarding.showJobsTab
    ? [
        { kind: "internal", href: "/graph", label: "My Graph" },
        { kind: "internal", href: "/jobs", label: "Jobs" },
      ]
    : [{ kind: "internal", href: "/graph", label: "My Graph" }];

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
      <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-4 sm:gap-6">
          <Link
            href={email ? "/graph" : "/"}
            className="text-lg font-bold tracking-tight text-foreground no-underline hover:no-underline hover:opacity-80"
          >
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
                  className={navLinkClass(item.href)}
                >
                  {item.label}
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
        className="flex gap-4 overflow-x-auto border-t border-border px-4 py-2 md:hidden"
        aria-label="Primary navigation"
      >
        {links.map((item) =>
          item.kind === "internal" ? (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "whitespace-nowrap text-sm no-underline hover:underline",
                pathname === item.href
                  ? "font-semibold text-foreground"
                  : "text-muted-foreground",
              )}
            >
              {item.label}
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
