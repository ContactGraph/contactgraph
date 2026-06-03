import { NextResponse } from "next/server";

import { env } from "@/lib/env";
import { getSession } from "@/lib/session";
import type { SyncSourceResult } from "@/lib/api-types";

export async function POST(request: Request): Promise<NextResponse> {
  const session = await getSession();
  const accessToken: string | undefined = session.accessToken;

  if (!session.isLoggedIn || !accessToken) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const formData: FormData = await request.formData();
  const file: FormDataEntryValue | null = formData.get("file");
  const sourceId: FormDataEntryValue | null = formData.get("source_id");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "Missing file" }, { status: 400 });
  }
  if (typeof sourceId !== "string" || sourceId.length === 0) {
    return NextResponse.json({ error: "Missing source_id" }, { status: 400 });
  }

  const upstream: FormData = new FormData();
  upstream.append("file", file, file.name);
  upstream.append("source_id", sourceId);

  try {
    const response: Response = await fetch(`${env.apiUrl}/api/upload-contacts`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      body: upstream,
    });

    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => null);
      const detail: string =
        typeof payload === "object" &&
        payload !== null &&
        "detail" in payload &&
        typeof payload.detail === "string"
          ? payload.detail
          : `Upload failed (${response.status})`;
      return NextResponse.json({ error: detail }, { status: response.status });
    }

    const result: SyncSourceResult = (await response.json()) as SyncSourceResult;
    return NextResponse.json(result);
  } catch (error: unknown) {
    const message: string =
      error instanceof Error ? error.message : "Upload request failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
