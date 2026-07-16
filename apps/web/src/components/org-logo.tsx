"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";

const DEFAULT_SIZE: number = 16;

function normalizeDomain(domain: string): string {
  const trimmed: string = domain.trim();
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
    try {
      return new URL(trimmed).hostname.replace(/^www\./, "");
    } catch {
      return trimmed.replace(/^www\./, "");
    }
  }
  return trimmed.replace(/^www\./, "");
}

function orgInitial(name: string): string {
  const trimmed: string = name.trim();
  if (trimmed.length === 0) {
    return "?";
  }
  return trimmed.charAt(0).toUpperCase();
}

function faviconUrl(domain: string, size: number): string {
  const normalized: string = normalizeDomain(domain);
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(normalized)}&sz=${size}`;
}

export interface OrgLogoProps {
  domain: string | null;
  name: string;
  size?: number;
  className?: string;
}

export function OrgLogo({
  domain,
  name,
  size = DEFAULT_SIZE,
  className,
}: OrgLogoProps) {
  const [imageFailed, setImageFailed] = useState<boolean>(false);
  const normalizedDomain: string | null =
    domain !== null && domain.trim() !== "" ? normalizeDomain(domain) : null;
  const showImage: boolean = normalizedDomain !== null && !imageFailed;

  if (showImage && normalizedDomain !== null) {
    return (
      <img
        src={faviconUrl(normalizedDomain, size)}
        alt=""
        width={size}
        height={size}
        className={cn("shrink-0 rounded-sm object-contain", className)}
        referrerPolicy="no-referrer"
        onError={() => setImageFailed(true)}
      />
    );
  }

  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded-sm bg-muted text-[10px] font-medium text-muted-foreground",
        className,
      )}
      style={{ width: size, height: size }}
      aria-hidden
    >
      {orgInitial(name)}
    </span>
  );
}
