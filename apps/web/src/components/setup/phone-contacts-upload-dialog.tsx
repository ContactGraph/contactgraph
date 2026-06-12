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
  const isSyncing: boolean = isPending || syncState === "syncing" || syncState === "pending";
  const isComplete: boolean = syncState === "complete";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload phone contacts</DialogTitle>
          <DialogDescription>
            Export contacts from your phone, then upload the .vcf or .csv file
            here.
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
            <p>3. Press and hold All Contacts, then tap Export.</p>
            <p>
              4. Save to Files, or AirDrop / Mail the .vcf file to yourself.
            </p>
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

          <div className="space-y-2 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">Export from Android</p>
            <p>1. Open the Contacts app.</p>
            <p>
              2. Tap the menu (⋮) or{" "}
              <span className="text-foreground">Fix &amp; manage</span>.
            </p>
            <p>
              3. Tap{" "}
              <span className="text-foreground">Export to file</span> (or
              Export).
            </p>
            <p>
              4. Choose all accounts and save the .vcf file.
            </p>
            <p>
              5. Transfer the file to your computer (email, Google Drive, or
              USB).
            </p>
            <p>
              Alternatively, visit{" "}
              <a
                href="https://contacts.google.com"
                className="underline"
                target="_blank"
                rel="noreferrer"
              >
                contacts.google.com
              </a>
              , select all, and export as vCard or Google CSV.
            </p>
          </div>

          <FileDropZone
            accept=".vcf,.vcard,.csv,text/vcard,text/csv"
            onFileSelect={onFileSelect}
            busy={isSyncing}
            busyMessage={
              syncState === "syncing"
                ? `Importing… ${contactsResolved} contacts so far`
                : "Uploading…"
            }
            idleMessage="Drag and drop your contacts file here"
            idleHint="or click to choose a .vcf or .csv file"
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
