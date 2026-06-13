"use client";

import { useEffect, useState } from "react";

export interface RotatingStatusTextProps {
  messages: readonly string[];
  intervalMs?: number;
  className?: string;
}

const DEFAULT_INTERVAL_MS: number = 3000;

function usePrefersReducedMotion(): boolean {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState<boolean>(false);

  useEffect(() => {
    const mediaQuery: MediaQueryList = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    );
    const updatePreference = (): void => {
      setPrefersReducedMotion(mediaQuery.matches);
    };
    updatePreference();
    mediaQuery.addEventListener("change", updatePreference);
    return () => {
      mediaQuery.removeEventListener("change", updatePreference);
    };
  }, []);

  return prefersReducedMotion;
}

export function RotatingStatusText({
  messages,
  intervalMs = DEFAULT_INTERVAL_MS,
  className,
}: RotatingStatusTextProps): React.JSX.Element | null {
  const prefersReducedMotion: boolean = usePrefersReducedMotion();
  const [index, setIndex] = useState<number>(0);
  const [visible, setVisible] = useState<boolean>(true);

  const safeMessages: readonly string[] =
    messages.length > 0 ? messages : [""];
  const currentMessage: string = safeMessages[index % safeMessages.length] ?? "";

  useEffect(() => {
    setIndex(0);
    setVisible(true);
  }, [messages]);

  useEffect(() => {
    if (prefersReducedMotion || safeMessages.length <= 1) {
      return;
    }

    const intervalId: ReturnType<typeof setInterval> = setInterval(() => {
      setVisible(false);
      window.setTimeout(() => {
        setIndex((currentIndex) => (currentIndex + 1) % safeMessages.length);
        setVisible(true);
      }, 200);
    }, intervalMs);

    return () => {
      clearInterval(intervalId);
    };
  }, [intervalMs, prefersReducedMotion, safeMessages]);

  if (currentMessage === "") {
    return null;
  }

  return (
    <span
      className={`inline-block transition-opacity duration-200 ${visible ? "opacity-100" : "opacity-0"} ${className ?? ""}`}
      aria-live="polite"
    >
      {currentMessage}
    </span>
  );
}
