"use client";

import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FileDropZone } from "@/components/ui/file-drop-zone";
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
  const isSyncing: boolean =
    isPending ||
    isProcessing ||
    syncState === "syncing" ||
    syncState === "pending";
  const isComplete: boolean = syncState === "complete" && !isProcessing;
  const isFailed: boolean = syncState === "failed" && !isProcessing;
  const failureMessage: string | null =
    error ?? syncError ?? (isFailed ? "Import failed. Try uploading again." : null);

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
              1. Click your avatar in the top navbar (the{" "}
              <span className="text-foreground">Me</span> menu).
            </p>
            <p>
              2. Click{" "}
              <span className="text-foreground">Settings &amp; Privacy</span>.
            </p>
            <p>
              3. Click the{" "}
              <span className="text-foreground">Data Privacy</span> tab on the
              left.
            </p>
            <p>
              4. Click{" "}
              <span className="text-foreground">Download your Data</span>.
            </p>
            <p>
              5. Select{" "}
              <span className="text-foreground">Download Larger Archive</span>{" "}
              and click{" "}
              <span className="text-foreground">Request archive</span>.
            </p>
            <p>
              6. Wait for the email from LinkedIn (can take up to 24 hours).
            </p>
            <p>
              7. Click the link in the email to download the{" "}
              <span className="text-foreground">.zip</span> file.
            </p>
            <p>
              8. Open the .zip, then find{" "}
              <span className="text-foreground">Connections.csv</span> in the
              extracted folder and upload it here.
            </p>
          </div>

          <FileDropZone
            onFileSelect={onFileSelect}
            busy={isSyncing}
            busyMessage={importStatusMessage(syncState, contactsResolved)}
            idleMessage="Drag and drop your .zip or Connections.csv here"
            idleHint="or click to choose a file"
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
