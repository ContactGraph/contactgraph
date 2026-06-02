import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function MarketingMain({
  children,
  wide = false,
}: {
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <main
      className={cn(
        "flex-1 px-5 py-7",
        wide ? "max-w-3xl" : "max-w-2xl",
      )}
    >
      {children}
    </main>
  );
}

export function MarketingProse({ children }: { children: ReactNode }) {
  return (
    <article
      className={cn(
        "max-w-prose text-sm leading-relaxed",
        "[&_h1]:mb-5 [&_h1]:text-sm [&_h1]:font-semibold",
        "[&_h2]:mb-3 [&_h2]:mt-7 [&_h2]:text-sm [&_h2]:font-semibold",
        "[&_p]:mb-4 [&_li]:mb-2",
        "[&_ol]:mb-4 [&_ol]:list-decimal [&_ol]:pl-5",
        "[&_ul]:mb-4 [&_ul]:list-disc [&_ul]:pl-5",
        "[&_hr]:my-7 [&_hr]:border-border",
      )}
    >
      {children}
    </article>
  );
}
