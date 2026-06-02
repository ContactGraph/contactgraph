import { getIronSession, type SessionOptions } from "iron-session";
import { cookies } from "next/headers";

import { env } from "@/lib/env";

export interface SessionData {
  accessToken?: string;
  refreshToken?: string;
  email?: string;
  isLoggedIn: boolean;
}

export const defaultSession: SessionData = {
  isLoggedIn: false,
};

export const sessionOptions: SessionOptions = {
  password: env.sessionSecret,
  cookieName: env.sessionCookieName,
  cookieOptions: {
    secure: process.env.NODE_ENV === "production",
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  },
};

export async function getSession(): Promise<
  Awaited<ReturnType<typeof getIronSession<SessionData>>>
> {
  const cookieStore = await cookies();
  return getIronSession<SessionData>(cookieStore, sessionOptions);
}
