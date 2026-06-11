"use client";

import { MasqueradeBanner } from "@/components/masquerade-banner";
import { SiteHeader } from "@/components/site-header";

export function AppShell({
  email,
  masqueradeAs,
  children,
}: {
  email: string;
  masqueradeAs?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-full bg-background">
      {masqueradeAs !== undefined ? (
        <MasqueradeBanner masqueradeAs={masqueradeAs} />
      ) : null}
      <SiteHeader email={masqueradeAs ?? email} />
      <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">{children}</main>
    </div>
  );
}
