import type { Metadata } from "next";
import type { ReactNode } from "react";

import { MarketingHeader } from "./components/marketing-header";
import { MarketingFooter } from "./components/marketing-footer";
import "./marketing.css";

export const metadata: Metadata = {
  robots: "index, follow",
};

export default function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className="marketing-page">
      <MarketingHeader />
      {children}
      <MarketingFooter />
    </div>
  );
}
