"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ConnectSourceResult, PollConnectResult } from "@/lib/api-types";

type LoginState = "idle" | "opening" | "polling" | "error";

export function LoginForm() {
  const router = useRouter();
  const popupRef = useRef<Window | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [state, setState] = useState<LoginState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const clearPollTimer = useCallback((): void => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearPollTimer();
      popupRef.current?.close();
    };
  }, [clearPollTimer]);

  const pollConnect = useCallback(
    async (sessionId: string, pollSecret: string): Promise<void> => {
      const response: Response = await fetch(
        `/api/auth/poll?sid=${encodeURIComponent(sessionId)}&poll_secret=${encodeURIComponent(pollSecret)}`,
      );
      if (!response.ok) {
        const payload: unknown = await response.json().catch(() => null);
        const message: string =
          typeof payload === "object" &&
          payload !== null &&
          "error" in payload &&
          typeof payload.error === "string"
            ? payload.error
            : "Failed to check OAuth status";
        throw new Error(message);
      }

      const result: PollConnectResult =
        (await response.json()) as PollConnectResult;
      setStatusMessage(result.message);

      if (result.status === "connected") {
        clearPollTimer();
        popupRef.current?.close();
        router.push("/graph");
        router.refresh();
        return;
      }

      if (result.status === "failed") {
        clearPollTimer();
        popupRef.current?.close();
        setState("error");
        setError(result.message);
      }
    },
    [clearPollTimer, router],
  );

  const handleSignIn = async (): Promise<void> => {
    setState("opening");
    setError(null);
    setStatusMessage(null);

    try {
      const response: Response = await fetch("/api/auth/login", {
        method: "POST",
      });
      if (!response.ok) {
        const payload: unknown = await response.json().catch(() => null);
        const message: string =
          typeof payload === "object" &&
          payload !== null &&
          "error" in payload &&
          typeof payload.error === "string"
            ? payload.error
            : "Failed to start sign in";
        throw new Error(message);
      }

      const result: ConnectSourceResult =
        (await response.json()) as ConnectSourceResult;

      if (
        result.already_connected &&
        result.access_token &&
        result.refresh_token
      ) {
        router.push("/graph");
        router.refresh();
        return;
      }

      const popup: Window | null = window.open(
        result.oauth_url,
        "contactgraph-oauth",
        "width=520,height=720",
      );

      if (!popup) {
        throw new Error(
          "Popup blocked. Allow popups for this site and try again.",
        );
      }

      popupRef.current = popup;
      setState("polling");
      setStatusMessage("Complete Google sign-in in the popup window…");

      const pollSecret: string | null = result.poll_secret;
      if (!pollSecret) {
        throw new Error("Server did not return a poll secret. Try signing in again.");
      }

      await pollConnect(result.connect_session_id, pollSecret);
      pollTimerRef.current = setInterval(() => {
        void pollConnect(result.connect_session_id, pollSecret).catch((pollError: unknown) => {
          clearPollTimer();
          setState("error");
          setError(
            pollError instanceof Error
              ? pollError.message
              : "OAuth polling failed",
          );
        });
      }, 4000);
    } catch (signInError: unknown) {
      setState("error");
      setError(
        signInError instanceof Error
          ? signInError.message
          : "Sign in failed",
      );
    }
  };

  return (
    <Card className="w-full border-border">
      <CardHeader className="p-5 pb-3">
        <CardTitle className="text-sm font-semibold">Sign in</CardTitle>
        <CardDescription className="text-sm">
          Connect your Google account to get started.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 p-5 pt-0">
        {error ? (
          <Alert variant="destructive">
            <AlertTitle>Sign in failed</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        {statusMessage && state !== "error" ? (
          <Alert>
            <AlertDescription>{statusMessage}</AlertDescription>
          </Alert>
        ) : null}
        <Button
          className="w-full"
          onClick={() => void handleSignIn()}
          disabled={state === "opening" || state === "polling"}
        >
          {state === "polling"
            ? "Waiting for Google…"
            : state === "opening"
              ? "Starting…"
              : "Sign in with Google"}
        </Button>
      </CardContent>
    </Card>
  );
}
