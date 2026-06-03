import { NextResponse } from "next/server";

import { env } from "@/lib/env";
import type { PollConnectResult } from "@/lib/api-types";
import { getSession } from "@/lib/session";

export async function GET(request: Request): Promise<NextResponse> {
  const url: URL = new URL(request.url);
  const sessionId: string | null = url.searchParams.get("sid");
  const pollSecret: string | null = url.searchParams.get("poll_secret");

  if (!sessionId) {
    return NextResponse.json(
      { error: "Missing connect session id" },
      { status: 400 },
    );
  }
  if (!pollSecret) {
    return NextResponse.json(
      { error: "Missing poll secret" },
      { status: 400 },
    );
  }

  try {
    const response: Response = await fetch(
      `${env.apiUrl}/api/poll-connect/${sessionId}`,
      {
        method: "POST",
        headers: { "X-Poll-Secret": pollSecret },
      },
    );

    if (!response.ok) {
      const detail: string = await response.text();
      return NextResponse.json({ error: detail }, { status: response.status });
    }

    const result: PollConnectResult =
      (await response.json()) as PollConnectResult;

    if (
      result.status === "connected" &&
      result.access_token &&
      result.refresh_token
    ) {
      const session = await getSession();
      session.accessToken = result.access_token;
      session.refreshToken = result.refresh_token;
      session.email = result.email ?? "";
      session.isLoggedIn = true;
      await session.save();
    }

    return NextResponse.json(result);
  } catch (error: unknown) {
    const message: string =
      error instanceof Error ? error.message : "Poll failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
