"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { cn } from "@/lib/utils";

const API_BASE = "https://api.contactgraph.ai";
const GITHUB_REPO_URL = "https://github.com/ContactGraph/contactgraph";

type NavLink =
  | { kind: "internal"; href: string; label: string }
  | { kind: "external"; href: string; label: string };

const appLinks: readonly NavLink[] = [
  { kind: "internal", href: "/people", label: "People" },
  { kind: "internal", href: "/organizations", label: "Organizations" },
  { kind: "internal", href: "/sources", label: "Sources" },
  { kind: "internal", href: "/profile", label: "Profile" },
  { kind: "internal", href: "/target-companies", label: "Targets" },
  { kind: "internal", href: "/trust", label: "Trust List" },
];

const marketingLinks: readonly NavLink[] = [
  { kind: "external", href: `${API_BASE}/skill.md`, label: "Skill" },
  { kind: "external", href: `${API_BASE}/mcp`, label: "MCP" },
  { kind: "external", href: GITHUB_REPO_URL, label: "GitHub" },
  { kind: "internal", href: "/manifesto", label: "Manifesto" },
];

export function SiteHeader({ email }: { email: string | null }) {
  const pathname: string = usePathname();
  const router = useRouter();
  const links: readonly NavLink[] = email ? appLinks : marketingLinks;

  const handleSignOut = async (): Promise<void> => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/");
    router.refresh();
  };

  const navLinkClass = (href: string): string =>
    cn(
      "text-sm no-underline hover:underline",
      pathname === href || pathname.startsWith(`${href}/`)
        ? "font-semibold text-foreground"
        : "text-muted-foreground",
    );

  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-4 sm:gap-6">
          <Link
            href={email ? "/people" : "/"}
            className="text-sm font-semibold no-underline hover:underline"
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
              <span className="max-w-[200px] truncate text-muted-foreground">
                {email}
              </span>
              <button
                type="button"
                onClick={() => void handleSignOut()}
                className="text-muted-foreground no-underline hover:underline"
              >
                Sign out
              </button>
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
