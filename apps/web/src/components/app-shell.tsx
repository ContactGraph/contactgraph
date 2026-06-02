"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems: ReadonlyArray<{
  href: string;
  label: string;
}> = [
  { href: "/people", label: "People" },
  { href: "/organizations", label: "Organizations" },
  { href: "/sources", label: "Sources" },
  { href: "/trust", label: "Trust List" },
];

export function AppShell({
  email,
  children,
}: {
  email: string;
  children: React.ReactNode;
}) {
  const pathname: string = usePathname();
  const router = useRouter();

  const handleSignOut = async (): Promise<void> => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  };

  return (
    <div className="min-h-full bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-center gap-4 sm:gap-6">
            <Link
              href="/people"
              className="text-sm font-semibold no-underline hover:underline"
            >
              ContactGraph
            </Link>
            <nav className="hidden items-center gap-4 md:flex">
              {navItems.map((item) => {
                const isActive: boolean =
                  pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "text-sm no-underline hover:underline",
                      isActive
                        ? "font-semibold text-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden max-w-[200px] truncate text-sm text-muted-foreground sm:inline">
              {email}
            </span>
            <Button variant="outline" size="sm" onClick={() => void handleSignOut()}>
              Sign out
            </Button>
          </div>
        </div>
        <nav className="flex gap-4 overflow-x-auto border-t border-border px-4 py-2 md:hidden">
          {navItems.map((item) => {
            const isActive: boolean = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "whitespace-nowrap text-sm no-underline hover:underline",
                  isActive
                    ? "font-semibold text-foreground"
                    : "text-muted-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </header>
      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">{children}</main>
    </div>
  );
}
