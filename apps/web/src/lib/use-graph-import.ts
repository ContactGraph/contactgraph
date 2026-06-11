"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { resolveLinkedInConnectionsUpload } from "@/lib/linkedin-connections-upload";
import type {
  ListSourcesResult,
  SourceSummary,
  SourceType,
  UploadSourceResult,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";
import { sourceForType } from "@/lib/setup-utils";

export interface GraphImportState {
  sources: SourceSummary[];
  sourcesLoading: boolean;
  phoneSource: SourceSummary | undefined;
  linkedinConnectionsSource: SourceSummary | undefined;
  phoneDialogOpen: boolean;
  setPhoneDialogOpen: (open: boolean) => void;
  linkedinConnectionsDialogOpen: boolean;
  setLinkedinConnectionsDialogOpen: (open: boolean) => void;
  phoneUploadError: string | null;
  connectionsUploadError: string | null;
  phoneUploadPending: boolean;
  linkedinUploadPending: boolean;
  phoneProcessing: boolean;
  linkedinConnectionsProcessing: boolean;
  handlePhoneFileUpload: (file: File) => void;
  handleLinkedInConnectionsFileUpload: (file: File) => Promise<void>;
  handleCancelSync: (sourceId: string) => void;
}

function useUploadSourceMutation(
  queryClient: ReturnType<typeof useQueryClient>,
  onPhoneSuccess: () => void,
  onLinkedInSuccess: () => void,
  onPhoneError: (message: string) => void,
  onLinkedInError: (message: string) => void,
) {
  return useMutation({
    mutationFn: (payload: {
      source_type: SourceType;
      filename: string;
      content: string;
    }) => proxyPost<UploadSourceResult>("upload-source", payload),
    onSuccess: async (_result, variables) => {
      if (variables.source_type === "phone_contacts_upload") {
        onPhoneSuccess();
      } else if (variables.source_type === "linkedin_connections_upload") {
        onLinkedInSuccess();
      }
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      await queryClient.invalidateQueries({ queryKey: ["network-status"] });
      await queryClient.invalidateQueries({ queryKey: ["org-enrichment-status"] });
    },
    onError: (error: Error, variables) => {
      if (variables.source_type === "phone_contacts_upload") {
        onPhoneError(error.message);
      } else if (variables.source_type === "linkedin_connections_upload") {
        onLinkedInError(error.message);
      }
    },
  });
}

export function useGraphImport(): GraphImportState {
  const queryClient = useQueryClient();
  const [phoneUploadError, setPhoneUploadError] = useState<string | null>(null);
  const [connectionsUploadError, setConnectionsUploadError] =
    useState<string | null>(null);
  const [phoneDialogOpen, setPhoneDialogOpen] = useState<boolean>(false);
  const [linkedinConnectionsDialogOpen, setLinkedinConnectionsDialogOpen] =
    useState<boolean>(false);
  const [phoneProcessing, setPhoneProcessing] = useState<boolean>(false);
  const [linkedinConnectionsProcessing, setLinkedinConnectionsProcessing] =
    useState<boolean>(false);
  const [phoneUploadPending, setPhoneUploadPending] = useState<boolean>(false);
  const [linkedinUploadPending, setLinkedinUploadPending] =
    useState<boolean>(false);

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => proxyPost<ListSourcesResult>("list-sources"),
    refetchInterval: (query) => {
      const data: ListSourcesResult | undefined = query.state.data;
      const syncing: boolean =
        data?.sources.some((source) => source.sync_state === "syncing") ??
        false;
      const pending: boolean =
        data?.sources.some((source) => source.sync_state === "pending") ??
        false;
      return syncing || pending || phoneProcessing || linkedinConnectionsProcessing
        ? 4000
        : false;
    },
  });

  const phoneUploadMutation = useUploadSourceMutation(
    queryClient,
    () => {
      setPhoneUploadError(null);
      setPhoneDialogOpen(false);
      setPhoneProcessing(true);
    },
    () => {},
    setPhoneUploadError,
    () => {},
  );

  const linkedinUploadMutation = useUploadSourceMutation(
    queryClient,
    () => {},
    () => {
      setConnectionsUploadError(null);
      setLinkedinConnectionsProcessing(true);
      setLinkedinConnectionsDialogOpen(false);
    },
    () => {},
    setConnectionsUploadError,
  );

  const sources: SourceSummary[] = sourcesQuery.data?.sources ?? [];
  const phoneSource: SourceSummary | undefined = sourceForType(
    sources,
    "phone_contacts_upload",
  );
  const linkedinConnectionsSource: SourceSummary | undefined = sourceForType(
    sources,
    "linkedin_connections_upload",
  );

  useEffect(() => {
    if (!phoneProcessing) {
      return;
    }
    if (phoneSource === undefined) {
      return;
    }
    if (
      phoneSource.sync_state === "complete" ||
      phoneSource.sync_state === "failed"
    ) {
      setPhoneProcessing(false);
      if (phoneSource.sync_state === "failed") {
        setPhoneUploadError(
          phoneSource.sync_error ?? "Import failed. Try uploading again.",
        );
      }
    }
  }, [phoneProcessing, phoneSource]);

  useEffect(() => {
    if (!linkedinConnectionsProcessing) {
      return;
    }
    if (linkedinConnectionsSource === undefined) {
      return;
    }
    if (
      linkedinConnectionsSource.sync_state === "complete" ||
      linkedinConnectionsSource.sync_state === "failed"
    ) {
      setLinkedinConnectionsProcessing(false);
      if (linkedinConnectionsSource.sync_state === "failed") {
        setConnectionsUploadError(
          linkedinConnectionsSource.sync_error ??
            "Import failed. Try uploading again.",
        );
      } else {
        void queryClient.invalidateQueries({ queryKey: ["organizations"] });
      }
    }
  }, [linkedinConnectionsProcessing, linkedinConnectionsSource, queryClient]);

  const uploadForType = useCallback(
    async (sourceType: SourceType, file: File): Promise<void> => {
      const content: string = await file.text();
      const payload = {
        source_type: sourceType,
        filename: file.name,
        content,
      };
      if (sourceType === "phone_contacts_upload") {
        setPhoneUploadPending(true);
        try {
          await phoneUploadMutation.mutateAsync(payload);
        } finally {
          setPhoneUploadPending(false);
        }
      } else {
        setLinkedinUploadPending(true);
        try {
          await linkedinUploadMutation.mutateAsync(payload);
        } finally {
          setLinkedinUploadPending(false);
        }
      }
    },
    [phoneUploadMutation, linkedinUploadMutation],
  );

  const handlePhoneFileUpload = useCallback(
    (file: File): void => {
      void uploadForType("phone_contacts_upload", file);
    },
    [uploadForType],
  );

  const handleLinkedInConnectionsFileUpload = useCallback(
    async (file: File): Promise<void> => {
      try {
        const resolved: File = await resolveLinkedInConnectionsUpload(file);
        await uploadForType("linkedin_connections_upload", resolved);
      } catch (error: unknown) {
        const message: string =
          error instanceof Error ? error.message : "Failed to read upload file";
        setConnectionsUploadError(message);
      }
    },
    [uploadForType],
  );

  const handleCancelSync = useCallback(
    (sourceId: string): void => {
      void proxyPost("cancel-sync", { source_id: sourceId }).then(() => {
        void sourcesQuery.refetch();
      });
    },
    [sourcesQuery],
  );

  return {
    sources,
    sourcesLoading: sourcesQuery.isLoading,
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
  };
}
