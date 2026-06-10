"use client";

import { Settings2 } from "lucide-react";

import { GraphSetupCards } from "@/components/setup/graph-setup-cards";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

interface GraphSettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function GraphSettingsButton({
  open,
  onOpenChange,
}: GraphSettingsModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Settings2 className="size-4" />
          Graph Settings
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Graph Settings</DialogTitle>
          <DialogDescription>
            Re-upload contacts or add new imports to refresh your network.
          </DialogDescription>
        </DialogHeader>
        <GraphSetupCards compact />
      </DialogContent>
    </Dialog>
  );
}
