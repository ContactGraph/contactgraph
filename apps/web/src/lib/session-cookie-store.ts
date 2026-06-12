import type { NextRequest, NextResponse } from "next/server";

type CookiePair = { name: string; value: string };

/** Adapt Next.js request cookies for iron-session (Next 16 RequestCookies type mismatch). */
export function cookieStoreFromRequest(request: NextRequest): {
  get(name: string): CookiePair | undefined;
  set(name: string, value: string, cookie?: Record<string, unknown>): void;
} {
  return {
    get(name: string): CookiePair | undefined {
      const cookie = request.cookies.get(name);
      if (cookie === undefined) {
        return undefined;
      }
      return { name: cookie.name, value: cookie.value };
    },
    set(name: string, value: string): void {
      request.cookies.set(name, value);
    },
  };
}

/** Adapt Next.js response cookies for iron-session. */
export function cookieStoreFromResponse(response: NextResponse): {
  get(name: string): CookiePair | undefined;
  set(name: string, value: string, cookie?: Record<string, unknown>): void;
} {
  return {
    get(name: string): CookiePair | undefined {
      const cookie = response.cookies.get(name);
      if (cookie === undefined) {
        return undefined;
      }
      return { name: cookie.name, value: cookie.value };
    },
    set(name: string, value: string, cookie?: Record<string, unknown>): void {
      response.cookies.set(name, value, cookie);
    },
  };
}
