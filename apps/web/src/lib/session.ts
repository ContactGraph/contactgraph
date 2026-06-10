import { getIronSession, type SessionOptions } from "iron-session";
import { cookies } from "next/headers";

import { env } from "@/lib/env";

export interface SessionData {
  accessToken?: string;
  refreshToken?: string;
  email?: string;
  isLoggedIn: boolean;
  isAdmin?: boolean;
  masqueradeAs?: string;
}

export const defaultSession: SessionData = {
  isLoggedIn: false,
};

function getSessionOptions(): SessionOptions {
  return {
    password: env.sessionSecret,
    cookieName: env.sessionCookieName,
    cookieOptions: {
      secure: process.env.NODE_ENV === "production",
      httpOnly: true,
      sameSite: "lax",
      path: "/",
    },
  };
}

export async function getSession(): Promise<
  Awaited<ReturnType<typeof getIronSession<SessionData>>>
> {
  const cookieStore = await cookies();
  return getIronSession<SessionData>(cookieStore, getSessionOptions());
}
