"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "contactsafe:job-bookmarks";

function getSnapshot(): ReadonlySet<string> {
  try {
    const raw: string | null = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed as string[]);
  } catch {
    return new Set();
  }
}

let cachedSet: ReadonlySet<string> = new Set();
const listeners = new Set<() => void>();

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

function emitChange(): void {
  cachedSet = getSnapshot();
  for (const cb of listeners) cb();
}

function getStoreSnapshot(): ReadonlySet<string> {
  return cachedSet;
}

function getServerSnapshot(): ReadonlySet<string> {
  return new Set();
}

if (typeof window !== "undefined") {
  cachedSet = getSnapshot();
  window.addEventListener("storage", (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) emitChange();
  });
}

export function useJobBookmarks(): {
  bookmarks: ReadonlySet<string>;
  toggle: (jobId: string) => void;
  isBookmarked: (jobId: string) => boolean;
} {
  const bookmarks = useSyncExternalStore(
    subscribe,
    getStoreSnapshot,
    getServerSnapshot,
  );

  const toggle = useCallback((jobId: string): void => {
    const current = getSnapshot();
    const next = new Set(current);
    if (next.has(jobId)) {
      next.delete(jobId);
    } else {
      next.add(jobId);
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]));
    emitChange();
  }, []);

  const isBookmarked = useCallback(
    (jobId: string): boolean => bookmarks.has(jobId),
    [bookmarks],
  );

  return { bookmarks, toggle, isBookmarked };
}
