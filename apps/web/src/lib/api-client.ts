import { env } from "@/lib/env";
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

let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
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

async function doRefresh(): Promise<boolean> {
  const session = await getSession();
  const refreshToken: string | undefined = session.refreshToken;

  if (!refreshToken) {
    return false;
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
    return false;
  }

  if (!response.ok) {
    return false;
  }

  const data: OAuthTokenResponse = (await response.json()) as OAuthTokenResponse;
  applyAuthTokensToSession(session, {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
  });
  await session.save();
  return true;
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
    const refreshed: boolean = await refreshAccessToken();
    if (refreshed) {
      const updatedSession = await getSession();
      token = updatedSession.accessToken;
      if (token) {
        response = await execute(token);
      }
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
