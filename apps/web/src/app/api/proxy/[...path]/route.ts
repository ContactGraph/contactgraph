import { NextResponse } from "next/server";

import { ApiError, apiFetch } from "@/lib/api-client";

export async function POST(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  const apiPath: string = path.join("/");

  try {
    const body: unknown = await request.json().catch(() => ({}));
    const result: unknown = await apiFetch<unknown>(apiPath, { body });
    return NextResponse.json(result);
  } catch (error: unknown) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        { error: error.message, detail: error.detail },
        { status: error.status },
      );
    }
    const message: string =
      error instanceof Error ? error.message : "Proxy request failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
