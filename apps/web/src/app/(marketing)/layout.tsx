import type { Metadata } from "next";
import type { ReactNode } from "react";

import { MarketingHeader } from "./components/marketing-header";
import { MarketingFooter } from "./components/marketing-footer";

export const metadata: Metadata = {
  robots: "index, follow",
};

export default function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-col bg-background text-foreground">
      <MarketingHeader />
      {children}
      <MarketingFooter />
    </div>
  );
}
