const ADMIN_SCOPE: string = "contactsafe:admin";

interface JwtPayload {
  scope?: string;
  sub?: string;
  exp?: number;
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  const parts: string[] = token.split(".");
  if (parts.length !== 3) {
    return null;
  }

  const payloadSegment: string | undefined = parts[1];
  if (payloadSegment === undefined) {
    return null;
  }

  try {
    const decoded: string = Buffer.from(payloadSegment, "base64url").toString(
      "utf-8",
    );
    const payload: unknown = JSON.parse(decoded);
    if (typeof payload !== "object" || payload === null) {
      return null;
    }
    return payload as JwtPayload;
  } catch {
    return null;
  }
}

export function tokenHasAdminScope(token: string): boolean {
  const payload: JwtPayload | null = decodeJwtPayload(token);
  const scope: string | undefined = payload?.scope;
  if (scope === undefined) {
    return false;
  }
  return scope.split(" ").includes(ADMIN_SCOPE);
}
