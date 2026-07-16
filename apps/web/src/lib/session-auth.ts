import type { IronSession } from "iron-session";

import { tokenHasAdminScope } from "@/lib/jwt";
import type { SessionData } from "@/lib/session";

export interface AuthTokens {
  accessToken: string;
  refreshToken?: string;
  email?: string;
}

export function sessionHasAdminAccess(session: SessionData): boolean {
  if (session.isAdmin === true) {
    return true;
  }

  const accessToken: string | undefined = session.accessToken;
  if (accessToken === undefined) {
    return false;
  }

  return tokenHasAdminScope(accessToken);
}

export function applyAuthTokensToSession(
  session: IronSession<SessionData>,
  tokens: AuthTokens,
): void {
  session.accessToken = tokens.accessToken;
  if (typeof tokens.refreshToken === "string" && tokens.refreshToken.length > 0) {
    session.refreshToken = tokens.refreshToken;
  }
  if (tokens.email !== undefined) {
    session.email = tokens.email;
  }
  session.isLoggedIn = true;
  session.isAdmin = tokenHasAdminScope(tokens.accessToken);

  if (!session.isAdmin) {
    session.masqueradeAs = undefined;
  }
}
