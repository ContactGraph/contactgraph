"use client";

import { Loader2, Upload } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface FileDropZoneProps {
  accept?: string;
  onFileSelect: (file: File) => void;
  disabled?: boolean;
  busy?: boolean;
  busyMessage?: string;
  idleMessage?: string;
  idleHint?: string;
  className?: string;
}

export function FileDropZone({
  accept,
  onFileSelect,
  disabled = false,
  busy = false,
  busyMessage = "Uploading…",
  idleMessage = "Drag and drop your file here",
  idleHint = "or click to choose a file",
  className,
}: FileDropZoneProps): React.JSX.Element {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState<boolean>(false);

  const handleFile = useCallback(
    (file: File | undefined): void => {
      if (file === undefined || disabled || busy) {
        return;
      }
      onFileSelect(file);
    },
    [onFileSelect, disabled, busy],
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
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
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
          if (!disabled && !busy) {
            setDragActive(true);
          }
        }}
        onDragLeave={() => {
          setDragActive(false);
        }}
        onDrop={onDrop}
        onClick={() => {
          if (!disabled && !busy) {
            fileInputRef.current?.click();
          }
        }}
        onKeyDown={(event) => {
          if (
            (event.key === "Enter" || event.key === " ") &&
            !disabled &&
            !busy
          ) {
            event.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        className={cn(
          "flex min-h-32 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center transition-colors",
          dragActive
            ? "border-foreground bg-muted/50"
            : "border-muted-foreground/40",
          (disabled || busy) && "cursor-not-allowed opacity-60",
          className,
        )}
      >
        {busy ? (
          <>
            <Loader2 className="size-7 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">{busyMessage}</p>
          </>
        ) : (
          <>
            <Upload className="size-7 text-muted-foreground" />
            <p className="text-sm font-medium">{idleMessage}</p>
            <p className="text-xs text-muted-foreground">{idleHint}</p>
          </>
        )}
      </div>
    </>
  );
}
