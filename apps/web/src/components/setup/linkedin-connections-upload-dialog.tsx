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

interface LinkedInConnectionsUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onFileSelect: (file: File) => void;
  isPending: boolean;
  isProcessing: boolean;
  error: string | null;
  syncState?: SyncState;
  syncError?: string | null;
  contactsResolved?: number;
}

function importStatusMessage(
  syncState: SyncState | undefined,
  contactsResolved: number,
): string {
  if (syncState === "syncing" || syncState === "pending") {
    if (contactsResolved > 0) {
      return `Importing… ${contactsResolved} connections so far`;
    }
    return "Importing… large exports can take several minutes";
  }
  return "Uploading…";
}

export function LinkedInConnectionsUploadDialog({
  open,
  onOpenChange,
  onFileSelect,
  isPending,
  isProcessing,
  error,
  syncState,
  syncError = null,
  contactsResolved = 0,
}: LinkedInConnectionsUploadDialogProps): React.JSX.Element {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState<boolean>(false);

  const isSyncing: boolean =
    isPending ||
    isProcessing ||
    syncState === "syncing" ||
    syncState === "pending";
  const isComplete: boolean = syncState === "complete" && !isProcessing;
  const isFailed: boolean = syncState === "failed" && !isProcessing;
  const failureMessage: string | null =
    error ?? syncError ?? (isFailed ? "Import failed. Try uploading again." : null);

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
          <DialogTitle>Upload LinkedIn connections</DialogTitle>
          <DialogDescription>
            Request your data from LinkedIn, then upload the .zip or
            Connections.csv here.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {failureMessage ? (
            <Alert variant="destructive">
              <AlertDescription>{failureMessage}</AlertDescription>
            </Alert>
          ) : null}
          {isComplete ? (
            <Alert>
              <AlertDescription>
                Import complete ({contactsResolved.toLocaleString()} connections).
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="space-y-2 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">Export from LinkedIn</p>
            <p>
              1. Go to LinkedIn → Settings &amp; Privacy → Data privacy →{" "}
              <span className="text-foreground">Get a copy of your data</span>.
            </p>
            <p>
              2. Choose <span className="text-foreground">Connections</span>{" "}
              (or request the larger archive that includes connections).
            </p>
            <p>3. Submit the request. LinkedIn usually emails you within 24 hours when your download is ready.</p>
            <p>
              4. Open the email from LinkedIn and download the{" "}
              <span className="text-foreground">.zip</span> file from the link.
            </p>
            <p>
              5. Upload the{" "}
              <span className="text-foreground">.zip</span> from Downloads, or
              open the unzipped folder and select{" "}
              <span className="text-foreground">Connections.csv</span>.
            </p>
          </div>

          <input
            ref={fileInputRef}
            type="file"
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
                  {importStatusMessage(syncState, contactsResolved)}
                </p>
              </>
            ) : (
              <>
                <Upload className="size-7 text-muted-foreground" />
                <p className="text-sm font-medium">
                  Drag and drop your .zip or Connections.csv here
                </p>
                <p className="text-xs text-muted-foreground">
                  or click to choose a file
                </p>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
