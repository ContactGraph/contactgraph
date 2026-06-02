const DEV_SESSION_SECRET: string = "dev-secret-minimum-32-characters!!";

function requireProductionEnv(name: string, value: string | undefined): string {
  if (value && value.length > 0) {
    return value;
  }
  if (process.env.NODE_ENV === "development") {
    return DEV_SESSION_SECRET;
  }
  throw new Error(`Missing required environment variable: ${name}`);
}

export const env = {
  apiUrl: process.env.CONTACTGRAPH_API_URL ?? "http://localhost:8000",
  sessionSecret: requireProductionEnv(
    "SESSION_SECRET",
    process.env.SESSION_SECRET,
  ),
  sessionCookieName: process.env.SESSION_COOKIE_NAME ?? "contactgraph_session",
} as const;
