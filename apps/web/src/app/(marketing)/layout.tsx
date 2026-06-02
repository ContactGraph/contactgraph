import type { Metadata } from "next";
import type { ReactNode } from "react";

import { MarketingFooter } from "./components/marketing-footer";
import { SiteHeader } from "@/components/site-header";
import { getSession } from "@/lib/session";

export const metadata: Metadata = {
  robots: "index, follow",
};

export default async function MarketingLayout({
  children,
}: {
  children: ReactNode;
}) {
  const session = await getSession();
  const email: string | null = session.isLoggedIn ? (session.email ?? null) : null;

  return (
    <div className="flex min-h-full flex-col bg-background text-foreground">
      <SiteHeader email={email} />
      {children}
      <MarketingFooter />
    </div>
  );
}
