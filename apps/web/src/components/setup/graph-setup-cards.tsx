"use client";

import {
  Loader2,
  Plus,
} from "lucide-react";

import { LinkedInConnectionsUploadDialog } from "@/components/setup/linkedin-connections-upload-dialog";
import { PhoneContactsUploadDialog } from "@/components/setup/phone-contacts-upload-dialog";
import { SetupStepStatusIcon } from "@/components/setup/setup-step-status-icon";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useGraphImport } from "@/lib/use-graph-import";
import {
  importProgressLabel,
  isLinkedInImportComplete,
  isPhoneImportComplete,
  isSourceStepInProgress,
} from "@/lib/setup-utils";

interface SetupCardProps {
  title: string;
  description: string;
  complete: boolean;
  inProgress: boolean;
  statusText: string | null;
  primaryLabel: string;
  onPrimary: () => void;
  disabled: boolean;
  progressDetail?: React.ReactNode;
}

function SetupCard({
  title,
  description,
  complete,
  inProgress,
  statusText,
  primaryLabel,
  onPrimary,
  disabled,
  progressDetail,
}: SetupCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="flex gap-3">
          <div className="mt-0.5 shrink-0">
            <SetupStepStatusIcon complete={complete} inProgress={inProgress} />
          </div>
          <div className="space-y-1">
            <CardTitle className="text-base">{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
            {progressDetail}
          </div>
        </div>
        {complete && statusText !== null ? (
          <div className="flex min-w-[6.5rem] flex-col items-end gap-0.5 text-right">
            <p className="text-sm font-medium tabular-nums">{statusText}</p>
            <button
              type="button"
              className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline disabled:opacity-50"
              onClick={onPrimary}
              disabled={disabled}
            >
              re-upload
            </button>
          </div>
        ) : inProgress ? (
          <Button variant="outline" size="sm" disabled>
            <Loader2 className="size-4 animate-spin" />
            Importing…
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={onPrimary} disabled={disabled}>
            <Plus className="size-4" />
            {primaryLabel}
          </Button>
        )}
      </CardHeader>
    </Card>
  );
}

export function GraphSetupCards({ compact = false }: { compact?: boolean }) {
  const graphImport = useGraphImport();
  const {
    sources,
    phoneSource,
    linkedinConnectionsSource,
    phoneDialogOpen,
    setPhoneDialogOpen,
    linkedinConnectionsDialogOpen,
    setLinkedinConnectionsDialogOpen,
    phoneUploadError,
    connectionsUploadError,
    phoneUploadPending,
    linkedinUploadPending,
    phoneProcessing,
    linkedinConnectionsProcessing,
    handlePhoneFileUpload,
    handleLinkedInConnectionsFileUpload,
    handleCancelSync,
  } = graphImport;

  const phoneComplete: boolean = isPhoneImportComplete(sources);
  const linkedinComplete: boolean = isLinkedInImportComplete(sources);
  const phoneInProgress: boolean =
    isSourceStepInProgress("phone_contacts_upload", sources) || phoneProcessing;
  const linkedinInProgress: boolean =
    isSourceStepInProgress("linkedin_connections_upload", sources) ||
    linkedinConnectionsProcessing;

  return (
    <div className={compact ? "space-y-4" : "space-y-6"}>
      {!compact ? (
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">My Graph</h1>
          <p className="text-muted-foreground">
            Import your contacts to build your network graph. You can upload
            phone contacts and LinkedIn connections at the same time.
          </p>
        </div>
      ) : null}

      <div className="space-y-4">
        <SetupCard
          title="Import phone contacts"
          description="Upload phone contacts (.vcf) from iPhone or Android — this is your authoritative network."
          complete={phoneComplete}
          inProgress={phoneInProgress}
          statusText={
            phoneComplete && phoneSource
              ? `${phoneSource.contacts_resolved.toLocaleString()} uploaded`
              : null
          }
          primaryLabel="Upload"
          onPrimary={() => setPhoneDialogOpen(true)}
          disabled={phoneUploadPending || phoneInProgress}
          progressDetail={
            phoneSource &&
            (phoneSource.sync_state === "syncing" ||
              phoneSource.sync_state === "pending") ? (
              <p className="text-xs text-muted-foreground">
                {importProgressLabel(phoneSource)}
                {" · "}
                <button
                  type="button"
                  className="text-destructive hover:underline"
                  onClick={() => handleCancelSync(phoneSource.source_id)}
                >
                  Cancel
                </button>
              </p>
            ) : phoneSource?.sync_state === "failed" ? (
              <p className="text-xs text-destructive">
                {phoneSource.sync_error ??
                  phoneUploadError ??
                  "Import failed — try uploading again"}
              </p>
            ) : phoneUploadError ? (
              <p className="text-xs text-destructive">{phoneUploadError}</p>
            ) : null
          }
        />

        <SetupCard
          title="Import LinkedIn connections"
          description="Upload your LinkedIn Connections.csv — identifies your strong professional ties. New companies are enriched automatically."
          complete={linkedinComplete}
          inProgress={linkedinInProgress}
          statusText={
            linkedinComplete && linkedinConnectionsSource
              ? `${linkedinConnectionsSource.contacts_resolved.toLocaleString()} imported`
              : null
          }
          primaryLabel="Upload"
          onPrimary={() => setLinkedinConnectionsDialogOpen(true)}
          disabled={linkedinUploadPending || linkedinInProgress}
          progressDetail={
            linkedinConnectionsSource &&
            (linkedinConnectionsSource.sync_state === "syncing" ||
              linkedinConnectionsSource.sync_state === "pending") ? (
              <p className="text-xs text-muted-foreground">
                {importProgressLabel(linkedinConnectionsSource)}
                {" · "}
                <button
                  type="button"
                  className="text-destructive hover:underline"
                  onClick={() =>
                    handleCancelSync(linkedinConnectionsSource.source_id)
                  }
                >
                  Cancel
                </button>
              </p>
            ) : linkedinConnectionsSource?.sync_state === "failed" ? (
              <p className="text-xs text-destructive">
                {linkedinConnectionsSource.sync_error ??
                  connectionsUploadError ??
                  "Import failed — try uploading again"}
              </p>
            ) : connectionsUploadError ? (
              <p className="text-xs text-destructive">{connectionsUploadError}</p>
            ) : null
          }
        />
      </div>

      <PhoneContactsUploadDialog
        open={phoneDialogOpen}
        onOpenChange={setPhoneDialogOpen}
        onFileSelect={handlePhoneFileUpload}
        isPending={phoneUploadPending}
        error={phoneUploadError}
        syncState={phoneSource?.sync_state}
        contactsResolved={phoneSource?.contacts_resolved}
      />

      <LinkedInConnectionsUploadDialog
        open={linkedinConnectionsDialogOpen}
        onOpenChange={setLinkedinConnectionsDialogOpen}
        onFileSelect={handleLinkedInConnectionsFileUpload}
        isPending={linkedinUploadPending}
        isProcessing={linkedinConnectionsProcessing}
        error={connectionsUploadError}
        syncState={linkedinConnectionsSource?.sync_state}
        syncError={linkedinConnectionsSource?.sync_error}
        contactsResolved={linkedinConnectionsSource?.contacts_resolved}
      />
    </div>
  );
}
