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

interface LinkedInProfileUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onFileSelect: (file: File) => void;
  isPending: boolean;
  isProcessing: boolean;
  error: string | null;
  isComplete: boolean;
}

export function LinkedInProfileUploadDialog({
  open,
  onOpenChange,
  onFileSelect,
  isPending,
  isProcessing,
  error,
  isComplete,
}: LinkedInProfileUploadDialogProps): React.JSX.Element {
  const isBusy: boolean = isPending || isProcessing;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Set up your profile</DialogTitle>
          <DialogDescription>
            Upload a LinkedIn PDF or resume so we can suggest roles and score how
            well you match each job&apos;s requirements. A resume usually has
            richer detail than a sparse LinkedIn profile.
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
                Profile imported. Your work history is on the Profile page if
                you want to review it.
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="space-y-2 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">Option A — LinkedIn PDF</p>
            <p>1. Go to your LinkedIn profile.</p>
            <p>
              2. Click the rightmost button under your name — it may say
              &quot;Resources&quot; or &quot;…&quot; (three dots).
            </p>
            <p>3. Select &quot;Save to PDF&quot; and download the file.</p>
            <p className="font-medium text-foreground pt-1">Option B — Resume PDF</p>
            <p>Upload any resume PDF. Re-uploading replaces your previous profile.</p>
          </div>

          <FileDropZone
            accept=".pdf,application/pdf"
            onFileSelect={onFileSelect}
            disabled={isBusy}
            busy={isBusy}
            busyMessage={isProcessing ? "Processing PDF…" : "Uploading…"}
            idleMessage="Drag and drop your LinkedIn PDF or resume here"
            idleHint="or click to choose a file"
          />

          {isProcessing ? (
            <p className="text-center text-xs text-muted-foreground">
              Reading your PDF and analyzing your background — this can take up to
              a couple of minutes for a detailed resume. You can keep this open or
              come back later.
            </p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
