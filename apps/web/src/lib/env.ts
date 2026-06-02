const DEV_SESSION_SECRET: string = "dev-secret-minimum-32-characters!!";

function isNextProductionBuild(): boolean {
  return process.env.NEXT_PHASE === "phase-production-build";
}

function readSessionSecret(): string {
  const value: string | undefined = process.env.SESSION_SECRET;
  if (value && value.length > 0) {
    return value;
  }
  if (process.env.NODE_ENV === "development" || isNextProductionBuild()) {
    return DEV_SESSION_SECRET;
  }
  throw new Error("Missing required environment variable: SESSION_SECRET");
}

export const env = {
  get apiUrl(): string {
    return process.env.CONTACTGRAPH_API_URL ?? "http://localhost:8000";
  },
  get sessionSecret(): string {
    return readSessionSecret();
  },
  get sessionCookieName(): string {
    return process.env.SESSION_COOKIE_NAME ?? "contactgraph_session";
  },
} as const;
