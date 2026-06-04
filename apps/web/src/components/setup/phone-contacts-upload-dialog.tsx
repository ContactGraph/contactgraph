"use client";

import { Loader2, Upload } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { SyncState } from "@/lib/api-types";

interface PhoneContactsUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onFileSelect: (file: File) => void;
  isPending: boolean;
  error: string | null;
  syncState?: SyncState;
  contactsResolved?: number;
}

export function PhoneContactsUploadDialog({
  open,
  onOpenChange,
  onFileSelect,
  isPending,
  error,
  syncState,
  contactsResolved = 0,
}: PhoneContactsUploadDialogProps): React.JSX.Element {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState<boolean>(false);

  const isSyncing: boolean = isPending || syncState === "syncing" || syncState === "pending";
  const isComplete: boolean = syncState === "complete";

  const handleFile = useCallback(
    (file: File | undefined): void => {
      if (file === undefined) {
        return;
      }
      onFileSelect(file);
    },
    [onFileSelect],
  );

  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>): void => {
      event.preventDefault();
      setDragActive(false);
      handleFile(event.dataTransfer.files[0]);
    },
    [handleFile],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload phone contacts</DialogTitle>
          <DialogDescription>
            Export from the Contacts app, then upload the .vcf file here.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          {isComplete ? (
            <Alert>
              <AlertDescription>
                Import complete ({contactsResolved} contacts).
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="space-y-2 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">Export from iPhone</p>
            <p>1. Open the Contacts app (or Phone → Contacts tab).</p>
            <p>2. Tap back button (or Lists) in the top-left.</p>
            <p>
              3. Press and hold All Contacts, then tap Export.
            </p>
            <p>4. Save to Files, or AirDrop / Mail the .vcf file to yourself.</p>
            <p>
              On a computer? Visit{" "}
              <a
                href="https://www.icloud.com/contacts"
                className="underline"
                target="_blank"
                rel="noreferrer"
              >
                icloud.com/contacts
              </a>
              , select all, and export vCard.
            </p>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".vcf,.vcard,.csv,text/vcard,text/csv"
            className="hidden"
            onChange={(event) => {
              handleFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
          <div
            role="button"
            tabIndex={0}
            onDragOver={(event) => {
              event.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => {
              setDragActive(false);
            }}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            className={`flex min-h-32 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center transition-colors ${
              dragActive
                ? "border-foreground bg-muted/50"
                : "border-muted-foreground/40"
            }`}
          >
            {isSyncing ? (
              <>
                <Loader2 className="size-7 animate-spin text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  {syncState === "syncing"
                    ? `Importing… ${contactsResolved} contacts so far`
                    : "Uploading…"}
                </p>
              </>
            ) : (
              <>
                <Upload className="size-7 text-muted-foreground" />
                <p className="text-sm font-medium">
                  Drag and drop your contacts file here
                </p>
                <p className="text-xs text-muted-foreground">
                  or click to choose a .vcf or .csv file
                </p>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
