import { env } from "@/lib/env";
import { decodeJwtPayload } from "@/lib/jwt";
import type { OAuthTokenResponse } from "@/lib/api-types";
import { applyAuthTokensToSession } from "@/lib/session-auth";
import { getSession } from "@/lib/session";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const TOKEN_EXPIRY_BUFFER_S: number = 60;

function isTokenExpired(token: string): boolean {
  const payload = decodeJwtPayload(token);
  if (payload === null || payload.exp === undefined) {
    return false;
  }
  return payload.exp - TOKEN_EXPIRY_BUFFER_S < Date.now() / 1000;
}

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise !== null) {
    return refreshPromise;
  }

  refreshPromise = doRefresh();
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

async function doRefresh(): Promise<string | null> {
  const session = await getSession();
  const refreshToken: string | undefined = session.refreshToken;

  if (!refreshToken) {
    session.isLoggedIn = false;
    await session.save();
    return null;
  }

  const body: URLSearchParams = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: refreshToken,
  });

  let response: Response;
  try {
    response = await fetch(`${env.apiUrl}/oauth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch {
    return null;
  }

  if (!response.ok) {
    if (response.status >= 400 && response.status < 500) {
      session.isLoggedIn = false;
      await session.save();
    }
    return null;
  }

  const data: OAuthTokenResponse = (await response.json()) as OAuthTokenResponse;
  applyAuthTokensToSession(session, {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
  });
  await session.save();
  return data.access_token;
}

async function parseErrorResponse(response: Response): Promise<string> {
  try {
    const payload: unknown = await response.json();
    if (
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
    ) {
      return payload.detail;
    }
    return JSON.stringify(payload);
  } catch {
    return response.statusText;
  }
}

export async function apiFetch<T>(
  path: string,
  options: {
    body?: unknown;
    method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
    accessToken?: string;
  } = {},
): Promise<T> {
  const session = await getSession();
  let token: string | undefined = options.accessToken ?? session.accessToken;

  if (!token) {
    throw new ApiError(401, "Not authenticated");
  }

  if (!options.accessToken && isTokenExpired(token)) {
    const newToken: string | null = await refreshAccessToken();
    if (newToken !== null) {
      token = newToken;
    }
  }

  const execute = async (bearerToken: string): Promise<Response> => {
    const headers: HeadersInit = {
      Authorization: `Bearer ${bearerToken}`,
    };

    const masqueradeAs: string | undefined = session.masqueradeAs;
    if (masqueradeAs !== undefined) {
      headers["X-On-Behalf-Of"] = masqueradeAs;
    }

    let requestBody: string | undefined;
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      requestBody = JSON.stringify(options.body);
    }

    return fetch(`${env.apiUrl}/api/${path}`, {
      method: options.method ?? "POST",
      headers,
      body: requestBody,
    });
  };

  let response: Response = await execute(token);

  if (response.status === 401 && !options.accessToken) {
    const newToken: string | null = await refreshAccessToken();
    if (newToken !== null) {
      response = await execute(newToken);
    }
  }

  if (!response.ok) {
    const detail: string = await parseErrorResponse(response);
    throw new ApiError(response.status, detail, detail);
  }

  return (await response.json()) as T;
}

export async function apiFetchUnauthenticated<T>(
  path: string,
  options: { body?: unknown; method?: "GET" | "POST" } = {},
): Promise<T> {
  const headers: HeadersInit = {};
  let requestBody: string | undefined;

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    requestBody = JSON.stringify(options.body);
  }

  const response: Response = await fetch(`${env.apiUrl}/api/${path}`, {
    method: options.method ?? "POST",
    headers,
    body: requestBody,
  });

  if (!response.ok) {
    const detail: string = await parseErrorResponse(response);
    throw new ApiError(response.status, detail, detail);
  }

  return (await response.json()) as T;
}
