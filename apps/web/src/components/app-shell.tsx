"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Building2, Database, LogOut, Shield, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems: ReadonlyArray<{
  href: string;
  label: string;
  icon: typeof Users;
}> = [
  { href: "/people", label: "People", icon: Users },
  { href: "/organizations", label: "Organizations", icon: Building2 },
  { href: "/sources", label: "Sources", icon: Database },
  { href: "/trust", label: "Trust List", icon: Shield },
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
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-6">
            <Link href="/people" className="font-semibold tracking-tight">
              ContactGraph
            </Link>
            <nav className="hidden items-center gap-1 md:flex">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive: boolean =
                  pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    )}
                  >
                    <Icon className="size-4" />
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
              <LogOut className="size-4" />
              Sign out
            </Button>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto border-t px-4 py-2 md:hidden">
          {navItems.map((item) => {
            const isActive: boolean = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium",
                  isActive
                    ? "bg-accent text-accent-foreground"
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
