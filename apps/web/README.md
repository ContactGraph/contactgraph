# ContactGraph Web App

Next.js dashboard for ContactGraph. Deploy separately from the Python API server.

## Prerequisites

- Node.js 20+
- pnpm
- ContactGraph API running locally (`make dev` from repo root)

## Setup

```bash
cd apps/web
cp .env.example .env.local
make web-install   # from repo root, or: COREPACK_ENABLE_STRICT=0 pnpm install
```

If `pnpm install` fails with ignored build scripts, run once from `apps/web`:

```bash
COREPACK_ENABLE_STRICT=0 pnpm approve-builds sharp unrs-resolver
```

(`pnpm-workspace.yaml` in this directory records that approval.)

If you see *"configured to use yarn"* because of a parent `package.json`, use
`COREPACK_ENABLE_STRICT=0 pnpm …` or `make web-install` from the repo root.

## Development

From repo root (with API on port 8000):

```bash
make web
```

Or from `apps/web`:

```bash
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment variables

| Variable | Description |
|----------|-------------|
| `CONTACTGRAPH_API_URL` | FastAPI backend URL (default `http://localhost:8000`) |
| `SESSION_SECRET` | 32+ char secret for encrypted session cookie |
| `SESSION_COOKIE_NAME` | Cookie name (default `contactgraph_session`) |

## Regenerate API types

With the backend running:

```bash
pnpm generate:types
```

Types are checked into `src/lib/api-types.ts` and aligned with `packages/core/src/contactsafe_core/schemas.py`.

## Production deploy (Railway)

Create a **separate** Railway service from the Python API. The repo root
`railway.toml` is for the API Dockerfile only; the web app must use its own
config or Railway will try to build the Python image and fail on missing
`migrations/`.

**WWW service settings**

| Setting | Value |
|---------|--------|
| Root directory | `apps/web` |
| Config file path | `/apps/web/railway.toml` (optional; Railpack default works once root `railway.toml` is removed) |
| Builder | Railpack |

**API service:** set config file path to `/railway.api.toml` (the old root
`railway.toml` forced the Python Dockerfile on every service in the project).

**Environment variables**

- `CONTACTGRAPH_API_URL` → e.g. `https://api.contactgraph.ai`
- `SESSION_SECRET` → strong random secret (32+ chars)

Railpack detects pnpm from `pnpm-lock.yaml` and runs `pnpm build` / `pnpm start`.
Optional: `RAILPACK_NODE_VERSION=20` if you want to pin Node.

The web app uses a BFF pattern: JWTs stay in an httpOnly cookie on the Next.js
server; the browser never sees them. No CORS changes are required on the API.

## Architecture

- **Auth:** Google OAuth via existing `connect-source` / `poll-connect` flow; tokens stored in iron-session cookie
- **Data:** Server components call FastAPI directly; client mutations go through `/api/proxy/*`
- **Stack:** Next.js App Router, TanStack Query, Tailwind v4, shadcn-style UI components
