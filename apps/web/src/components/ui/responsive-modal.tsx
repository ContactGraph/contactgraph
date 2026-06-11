"use client";

import * as React from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";

const DESKTOP_MEDIA_QUERY = "(min-width: 640px)";

function useIsDesktop(): boolean {
  return useMediaQuery(DESKTOP_MEDIA_QUERY);
}

interface ResponsiveModalProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
}

export function ResponsiveModal({
  open,
  onOpenChange,
  children,
}: ResponsiveModalProps) {
  const isDesktop = useIsDesktop();

  if (isDesktop) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        {children}
      </Dialog>
    );
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {children}
    </Sheet>
  );
}

export function ResponsiveModalTrigger({
  ...props
}: React.ComponentProps<typeof DialogTrigger>) {
  const isDesktop = useIsDesktop();

  if (isDesktop) {
    return <DialogTrigger {...props} />;
  }

  return <SheetTrigger {...props} />;
}

export function ResponsiveModalContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DialogContent>) {
  const isDesktop = useIsDesktop();

  if (isDesktop) {
    return (
      <DialogContent
        className={cn("max-h-[85vh] overflow-y-auto sm:max-w-lg", className)}
        {...props}
      >
        {children}
      </DialogContent>
    );
  }

  return (
    <SheetContent
      side="bottom"
      className={cn("max-h-[90vh] overflow-y-auto", className)}
      {...props}
    >
      {children}
    </SheetContent>
  );
}

export function ResponsiveModalHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const isDesktop = useIsDesktop();

  if (isDesktop) {
    return <DialogHeader className={className} {...props} />;
  }

  return (
    <div
      className={cn("flex flex-col space-y-1.5 border-b pb-4", className)}
      {...props}
    />
  );
}

export function ResponsiveModalTitle({
  className,
  ...props
}: React.ComponentProps<typeof DialogTitle>) {
  const isDesktop = useIsDesktop();

  if (isDesktop) {
    return <DialogTitle className={className} {...props} />;
  }

  return <SheetTitle className={className} {...props} />;
}

export function ResponsiveModalDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogDescription>) {
  const isDesktop = useIsDesktop();

  if (isDesktop) {
    return <DialogDescription className={className} {...props} />;
  }

  return <SheetDescription className={className} {...props} />;
}
