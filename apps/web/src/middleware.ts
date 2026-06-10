import { getIronSession } from "iron-session";
import { type NextRequest, NextResponse } from "next/server";

import type { SessionData } from "@/lib/session";

function getSessionOptions(): {
  password: string;
  cookieName: string;
  cookieOptions: {
    secure: boolean;
    httpOnly: boolean;
    sameSite: "lax";
    path: string;
  };
} {
  const password: string =
    process.env.SESSION_SECRET ?? "dev-secret-minimum-32-characters!!";
  const cookieName: string =
    process.env.SESSION_COOKIE_NAME ?? "contactgraph_session";
  return {
    password,
    cookieName,
    cookieOptions: {
      secure: process.env.NODE_ENV === "production",
      httpOnly: true,
      sameSite: "lax",
      path: "/",
    },
  };
}

export async function middleware(request: NextRequest): Promise<NextResponse> {
  const url: URL = new URL(request.url);
  const masqueradeTarget: string | null = url.searchParams.get("masquerade");

  if (masqueradeTarget === null) {
    return NextResponse.next();
  }

  const readSession = await getIronSession<SessionData>(
    request.cookies,
    getSessionOptions(),
  );

  if (!readSession.isLoggedIn || !readSession.isAdmin) {
    return NextResponse.redirect(buildCleanUrl(url), 303);
  }

  const response: NextResponse = NextResponse.redirect(
    buildCleanUrl(url),
    303,
  );

  const writeSession = await getIronSession<SessionData>(
    response.cookies,
    getSessionOptions(),
  );

  Object.assign(writeSession, { ...readSession, masqueradeAs: masqueradeTarget.trim() });
  await writeSession.save();

  return response;
}

function buildCleanUrl(url: URL): URL {
  const clean: URL = new URL(url);
  clean.searchParams.delete("masquerade");
  return clean;
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
