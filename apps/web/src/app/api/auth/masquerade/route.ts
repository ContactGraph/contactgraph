import { NextResponse } from "next/server";

import { getSession } from "@/lib/session";
import { sessionHasAdminAccess } from "@/lib/session-auth";

type MasqueradeAction = "start" | "stop";

interface MasqueradeRequestBody {
  action: MasqueradeAction;
  target?: string;
}

function parseRequestBody(body: unknown): MasqueradeRequestBody | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }

  const action: unknown = Reflect.get(body, "action");
  if (action !== "start" && action !== "stop") {
    return null;
  }

  const target: unknown = Reflect.get(body, "target");
  if (action === "start") {
    if (typeof target !== "string" || target.trim().length === 0) {
      return null;
    }
    return { action, target: target.trim() };
  }

  return { action };
}

export async function POST(request: Request): Promise<NextResponse> {
  const session = await getSession();

  if (!session.isLoggedIn || session.accessToken === undefined) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const parsed: MasqueradeRequestBody | null = parseRequestBody(body);
  if (parsed === null) {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  if (parsed.action === "stop") {
    delete (session as unknown as Record<string, unknown>).masqueradeAs;
    await session.save();
    return NextResponse.json({ ok: true, masqueradeAs: null });
  }

  if (!sessionHasAdminAccess(session)) {
    return NextResponse.json(
      { error: "Masquerade requires admin access" },
      { status: 403 },
    );
  }

  session.masqueradeAs = parsed.target;
  await session.save();
  return NextResponse.json({ ok: true, masqueradeAs: parsed.target });
}
