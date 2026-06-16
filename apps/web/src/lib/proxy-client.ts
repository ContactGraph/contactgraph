"use client";

let redirecting: boolean = false;

async function proxyPost<T>(path: string, body?: unknown): Promise<T> {
  const response: Response = await fetch(`/api/proxy/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const message: string =
      typeof payload === "object" &&
      payload !== null &&
      "error" in payload &&
      typeof payload.error === "string"
        ? payload.error
        : `Request failed (${response.status})`;

    if (response.status === 401 && !redirecting) {
      redirecting = true;
      window.location.href = "/login";
    }

    throw new Error(message);
  }

  return (await response.json()) as T;
}

export { proxyPost };
