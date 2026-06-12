import { getSession } from "@/lib/session";
import { env } from "@/lib/env";

export async function GET(): Promise<Response> {
  const session = await getSession();
  const token: string | undefined = session.accessToken;

  if (!token) {
    return new Response("Not authenticated", { status: 401 });
  }

  const headers: HeadersInit = {
    Authorization: `Bearer ${token}`,
  };

  const masqueradeAs: string | undefined = session.masqueradeAs;
  if (masqueradeAs !== undefined) {
    headers["X-On-Behalf-Of"] = masqueradeAs;
  }

  const upstream: Response = await fetch(`${env.apiUrl}/api/events/graph`, {
    headers,
  });

  if (!upstream.ok || upstream.body === null) {
    const detail: string = await upstream.text();
    return new Response(detail, { status: upstream.status });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
