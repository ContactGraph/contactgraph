"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ListSourcesResult, SyncSourceResult } from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";

interface UploadPageProps {
  params: Promise<{ sourceId: string }>;
}

export default function PhoneContactsUploadPage({
  params,
}: UploadPageProps): React.JSX.Element {
  const router = useRouter();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [sourceId, setSourceId] = useState<string>("");
  const [dragActive, setDragActive] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  useEffect(() => {
    void params.then((resolved) => {
      setSourceId(resolved.sourceId);
    });
  }, [params]);

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => proxyPost<ListSourcesResult>("list-sources"),
    enabled: sourceId.length > 0,
    refetchInterval: (query) => {
      const data: ListSourcesResult | undefined = query.state.data;
      const syncing: boolean =
        data?.sources.some(
          (source) =>
            source.source_id === sourceId && source.sync_state === "syncing",
        ) ?? false;
      return syncing ? 4000 : false;
    },
  });

  const source = sourcesQuery.data?.sources.find(
    (entry) => entry.source_id === sourceId,
  );

  const uploadMutation = useMutation({
    mutationFn: async (file: File): Promise<SyncSourceResult> => {
      const formData: FormData = new FormData();
      formData.append("file", file);
      formData.append("source_id", sourceId);

      const response: Response = await fetch("/api/upload-contacts", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const payload: unknown = await response.json().catch(() => null);
        const message: string =
          typeof payload === "object" &&
          payload !== null &&
          "error" in payload &&
          typeof payload.error === "string"
            ? payload.error
            : `Upload failed (${response.status})`;
        throw new Error(message);
      }

      return (await response.json()) as SyncSourceResult;
    },
    onSuccess: async (result: SyncSourceResult) => {
      setUploadError(null);
      setUploadMessage(result.message);
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
    onError: (error: Error) => {
      setUploadError(error.message);
    },
  });

  useEffect(() => {
    if (source?.sync_state === "complete") {
      const timer: ReturnType<typeof setTimeout> = setTimeout(() => {
        router.push("/sources");
      }, 2500);
      return () => {
        clearTimeout(timer);
      };
    }
    return undefined;
  }, [router, source?.sync_state]);

  const handleFile = useCallback(
    (file: File | undefined): void => {
      if (file === undefined || sourceId.length === 0) {
        return;
      }
      setUploadError(null);
      setUploadMessage(null);
      uploadMutation.mutate(file);
    },
    [sourceId, uploadMutation],
  );

  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>): void => {
      event.preventDefault();
      setDragActive(false);
      const file: File | undefined = event.dataTransfer.files[0];
      handleFile(file);
    },
    [handleFile],
  );

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Upload phone contacts
        </h1>
        <p className="text-muted-foreground">
          Import a vCard (.vcf) or CSV export from your iPhone or Android device.
        </p>
      </div>

      {uploadError ? (
        <Alert variant="destructive">
          <AlertDescription>{uploadError}</AlertDescription>
        </Alert>
      ) : null}
      {uploadMessage ? (
        <Alert>
          <AlertDescription>{uploadMessage}</AlertDescription>
        </Alert>
      ) : null}
      {source?.sync_state === "complete" ? (
        <Alert>
          <AlertDescription>
            Import complete ({source.contacts_resolved} contacts). Returning to
            sources…
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Export from iPhone</CardTitle>
          <CardDescription>
            Follow these steps, then upload the file below.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>1. Open the Contacts app (or Phone → Contacts tab).</p>
          <p>2. Tap Lists (or back button) in the top-left.</p>
          <p>
            3. Press and hold All Contacts (or All iCloud), then tap Export.
          </p>
          <p>4. Save to Files, or AirDrop / Mail the .vcf file to yourself.</p>
          <p>
            On a computer instead? Visit{" "}
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Upload file</CardTitle>
          <CardDescription>Accepts .vcf, .vcard, or .csv files.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
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
            className={`flex min-h-40 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-8 text-center transition-colors ${
              dragActive ? "border-foreground bg-muted/50" : "border-muted-foreground/40"
            }`}
          >
            {uploadMutation.isPending || source?.sync_state === "syncing" ? (
              <>
                <Loader2 className="size-8 animate-spin text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  {source?.sync_state === "syncing"
                    ? `Importing… ${source.contacts_resolved} contacts so far`
                    : "Uploading…"}
                </p>
              </>
            ) : (
              <>
                <Upload className="size-8 text-muted-foreground" />
                <p className="text-sm font-medium">
                  Drag and drop your contacts file here
                </p>
                <p className="text-xs text-muted-foreground">
                  or click to choose a file
                </p>
              </>
            )}
          </div>
          <Button variant="outline" onClick={() => router.push("/sources")}>
            Back to sources
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
