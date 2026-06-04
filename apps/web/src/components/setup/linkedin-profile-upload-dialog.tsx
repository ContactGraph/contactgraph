"use client";

import { Loader2, Upload } from "lucide-react";
import { useCallback, useRef } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

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
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handlePdfUpload = useCallback(
    (file: File | undefined): void => {
      if (file === undefined) {
        return;
      }
      onFileSelect(file);
    },
    [onFileSelect],
  );

  const isBusy: boolean = isPending || isProcessing;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Set up your profile</DialogTitle>
          <DialogDescription>
            Upload your LinkedIn PDF to identify your contacts during enrichment.
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
            <p className="font-medium text-foreground">Export from LinkedIn</p>
            <p>1. Go to your LinkedIn profile.</p>
            <p>2. Click &quot;More&quot; below your headline.</p>
            <p>3. Select &quot;Save to PDF&quot; and download the file.</p>
            <p>4. Upload the PDF below.</p>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            className="hidden"
            onChange={(event) => {
              handlePdfUpload(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
          <Button
            variant="outline"
            className="w-full"
            onClick={() => fileInputRef.current?.click()}
            disabled={isBusy}
          >
            {isBusy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Upload className="size-4" />
            )}
            {isProcessing ? "Processing PDF…" : "Upload LinkedIn PDF"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
