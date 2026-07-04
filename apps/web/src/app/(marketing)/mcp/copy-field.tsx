"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function CopyField({
  value,
  ariaLabel,
}: {
  value: string;
  ariaLabel?: string;
}) {
  const [copied, setCopied] = useState<boolean>(false);

  const handleCopy = (): void => {
    void navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-2">
      <code className="min-w-0 flex-1 overflow-x-auto rounded-md border border-border bg-muted px-3 py-2 font-mono text-sm">
        {value}
      </code>
      <Button
        size="sm"
        variant="outline"
        onClick={handleCopy}
        aria-label={ariaLabel ?? "Copy to clipboard"}
      >
        {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}
