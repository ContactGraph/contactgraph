import { NextResponse } from "next/server";

import { apiFetchUnauthenticated } from "@/lib/api-client";
import type { ConnectSourceResult } from "@/lib/api-types";
import { getSession } from "@/lib/session";

export async function POST(): Promise<NextResponse> {
  try {
    const session = await getSession();
    const result: ConnectSourceResult =
      await apiFetchUnauthenticated<ConnectSourceResult>("connect-source", {
        body: { source_type: "google_mail" },
      });

    if (
      result.already_connected &&
      result.access_token &&
      result.refresh_token
    ) {
      session.accessToken = result.access_token;
      session.refreshToken = result.refresh_token;
      session.email = result.email ?? session.email ?? "";
      session.isLoggedIn = true;
      await session.save();
    }

    return NextResponse.json(result);
  } catch (error: unknown) {
    const message: string =
      error instanceof Error ? error.message : "Failed to start login";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
