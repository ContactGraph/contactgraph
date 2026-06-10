"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

export function MasqueradeUrlHandler() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const handledRef = useRef<boolean>(false);

  useEffect(() => {
    const target: string | null = searchParams.get("masquerade");
    if (target === null || handledRef.current) {
      return;
    }

    handledRef.current = true;

    void (async (): Promise<void> => {
      const response: Response = await fetch("/api/auth/masquerade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "start", target }),
      });

      const params = new URLSearchParams(searchParams.toString());
      params.delete("masquerade");
      const queryString: string = params.toString();
      const cleanPath: string = queryString
        ? `${pathname}?${queryString}`
        : pathname;

      if (response.ok) {
        window.location.replace(cleanPath);
        return;
      }

      window.location.replace(cleanPath);
    })();
  }, [pathname, searchParams]);

  return null;
}
