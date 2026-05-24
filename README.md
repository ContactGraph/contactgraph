# ContactSafe

Agent-native personal contact graph built from messaging, email, and calendar data. ContactSafe exposes **MCP tools** for connecting sources, syncing, and natural-language search.

**Production:** [https://www.contactsafe.ai](https://www.contactsafe.ai)  
**MCP endpoint:** `https://www.contactsafe.ai/mcp`  
**Agent skill file:** `https://www.contactsafe.ai/skill.md`

Example questions once synced:

- What investors do I know?
- Who do I know at ACME?
- Who do I know who works in RevOps?
- Where does Jim Smith work now?

## Data sources (extensible framework)

ContactSafe is built as an **extensible source framework**. Every connector uses the same MCP workflow (`connect_source` → `sync_source` → `query_network`) and writes into one unified graph (people, orgs, employment edges, relationship strength).

| Source | `source_type` | Status |
|--------|---------------|--------|
| **Gmail** | `google_mail` | **Shipped** — imports email metadata (headers only) into contacts, org links, and tie strength |
| Google Calendar | `google_calendar` | Planned — co-attendance and relationship signals from events |
| Other (LinkedIn, WhatsApp, CRM, …) | TBD | Roadmap |

**Gmail is the first data source, not the architecture.** New sources add importers and OAuth scopes behind the same tools and graph schema — agents and humans do not need new MCP tool names when we ship the next connector.

---

## Quick start for humans

### Claude

1. Claude.ai → **Customize** (top of left sidebar) → **Connectors** → **+** → **Add custom connector**
2. **Name:** `ContactSafe`
3. **Remote MCP server URL:** `https://www.contactsafe.ai/mcp`
4. Leave Client ID / Secret empty (Dynamic Client Registration).
5. Click **Connect** → sign in with Google → return to Claude.
6. Start a **new chat**, enable the ContactSafe connector.
7. Ask the agent to run **`sync_source`**, wait until layout to finish, then try *"What VCs do I know?"* or *"Who do I know at Sticker VC?"*

Claude uses redirect URI `https://claude.ai/api/mcp/auth_callback` — handled automatically.

**Note:** If tools stop working after ~15 minutes, disconnect/reconnect the connector (token refresh). For testing, set `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440` on Railway.

### OpenClaw

TBD.

---

## Quick start for agents

1. Read the skill file: **`https://www.contactsafe.ai/skill.md`**
2. MCP server: **`https://www.contactsafe.ai/mcp`** (Streamable HTTP; trailing slash OK)
3. Authenticate via OAuth 2.1 Bearer token (see **MCP authentication** below). `connect_source` can start Google OAuth without a token; other tools require `Authorization: Bearer …` unless using deprecated `connect_session_id`.
4. Typical flow:
   - `connect_source` (`source_type`: `google_mail`) → user opens `oauth_url` → Google consent
   - `sync_source` → poll `get_source_status` until `sync_state` is `partial` or `complete`
   - `query_network` with e.g. `"Who do I know at Sticker VC?"`

After deploys or schema changes, run **`sync_source` again** to refresh classification, employment edges, and enrichment.

Local development URLs: `http://localhost:8000/mcp`, `http://localhost:8000/skill.md`.

---

## Quick start (developers)

```bash
uv sync --package contactsafe-server --extra dev

cp .env.example .env
# Fill in DATABASE_URL, TOKEN_ENCRYPTION_KEY, SESSION_SECRET, Google OAuth

make migrate
make dev
```

| Endpoint | Local |
|----------|-------|
| Health | http://localhost:8000/health |
| MCP | http://localhost:8000/mcp |
| Skill | http://localhost:8000/skill.md |
| OAuth metadata | http://localhost:8000/.well-known/oauth-authorization-server |

---

## Testing locally

1. `make dev`
2. Health: `curl -s http://localhost:8000/health`
3. MCP without auth (expect **401**):

```bash
curl -i -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
```

4. [MCP Inspector](https://github.com/modelcontextprotocol/inspector) → `http://localhost:8000/mcp` → OAuth or Bearer token
5. Flow: `connect_source` → Google OAuth → `sync_source` → `get_source_status` → `query_network`
6. Tests: `make test`

---

## Testing production

Production runs on **Railway** at **https://www.contactsafe.ai** (`www` CNAME → Railway). Always use this URL for OAuth, MCP, and JWT audience — not the raw Railway hostname.

```bash
curl -s https://www.contactsafe.ai/health
curl -s https://www.contactsafe.ai/.well-known/oauth-protected-resource | jq
curl -s https://www.contactsafe.ai/.well-known/oauth-authorization-server | jq
curl -i -X POST https://www.contactsafe.ai/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
# Expect 401 + WWW-Authenticate
```

After connecting Gmail, run **`sync_source`** once (or again after upgrades), then query e.g. *"What VCs do I know?"*

Railway fallback hostname: `https://contactsafe-production.up.railway.app` — avoid for OAuth/MCP clients.

MCP Inspector production URL: `https://www.contactsafe.ai/mcp`

---

## MCP tools

| Tool | Auth | Description |
|------|------|-------------|
| `connect_source` | Optional | Connect a source. **`google_mail`** is the only implemented `source_type` today. Returns `oauth_url` when browser consent is needed. |
| `list_sources` | Bearer (or deprecated `connect_session_id`) | List connected sources for the user |
| `get_source_status` | Bearer / `source_id` / deprecated session | Connection + sync progress (`pending` \| `syncing` \| `partial` \| `complete` \| `failed`) |
| `sync_source` | Bearer / `source_id` / deprecated session | Import or refresh graph from connected source(s). No browser step. |
| `query_network` | Bearer / `source_id` / deprecated session | Natural-language search over the user's graph |

Legacy `connect_session_id` on tool parameters still works but is **deprecated** — prefer OAuth 2.1 Bearer tokens.

---

## MCP workflow (OAuth 2.1)

1. Discover: `GET /.well-known/oauth-protected-resource` and `GET /.well-known/oauth-authorization-server`
2. Authorize with PKCE: `GET /oauth/authorize?...`
3. User completes Google consent for the requested source (Gmail today)
4. Exchange code: `POST /oauth/token` (`grant_type=authorization_code`, PKCE verifier)
5. Call MCP tools with `Authorization: Bearer <access_token>`
6. `connect_source` → `sync_source` → poll `get_source_status` → `query_network`

Refresh: `POST /oauth/token` with `grant_type=refresh_token`.

Dynamic Client Registration: `POST /oauth/register` (RFC 7591).

---

## Graph model and query engine

Each sync builds a per-user graph:

- **People** — name, email, inferred categories (`vc`, `founder`, …), role/org (denormalized cache)
- **Orgs** — domain, name, flexible `categories` + JSON `attributes` (schools, hospitals, nonprofits, companies, …)
- **Edges** — user↔person (tie strength, human/broadcast/automated flags), person↔org employment, user↔org aggregates, person↔person co-occurrence

**`query_network`** accepts a natural-language `question` and returns `matches` + `applied_plan`.

| Config | Effect |
|--------|--------|
| No `OPENAI_API_KEY` | Heuristic query planner + email-domain/name category tags |
| `EXA_API_KEY` | Web enrichment during sync for top **human** contacts (role, org, VC tags) |
| `OPENAI_API_KEY` | LLM query plans, richer ingest enrichment, semantic excerpt search |

By default, queries **exclude automated senders and newsletters** (`exclude_automated`, `exclude_broadcast`).

Example questions: *"Who do I know named Chris?"*, *"What VCs do I know?"*, *"Who do I know at AIX?"*, *"Who did I talk to about hiring?"* (semantic needs OpenAI + excerpts).

---

## Google OAuth (Gmail source)

1. [Google Cloud Console](https://console.cloud.google.com/) → enable **Gmail API** (Calendar API optional; calendar ingest not shipped yet)
2. OAuth client (Web) → redirect URIs:
   - Local: `http://localhost:8000/oauth/callback`
   - Production: `https://www.contactsafe.ai/oauth/callback`
3. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` in `.env` / Railway

Requested scopes include `gmail.readonly` (used today) and `calendar.readonly` (reserved for the calendar connector).

---

## Deploy on Railway

1. Create a Railway project from this repo (`Dockerfile` + `railway.toml`).
2. Postgres or Supabase `DATABASE_URL`.
3. **Required env vars:**
   - `APP_ENV=production`
   - `BASE_URL=https://www.contactsafe.ai`
   - `GOOGLE_REDIRECT_URI=https://www.contactsafe.ai/oauth/callback`
   - `JWT_SIGNING_KEY` (separate from `SESSION_SECRET`)
   - Optional: `OPENAI_API_KEY`, `EXA_API_KEY` (see `.env.example`)
4. Google Cloud redirect URI must match production callback.
5. CNAME **www.contactsafe.ai** → Railway.
6. Deploy — `alembic upgrade head` runs on container start.

---

## Database

### Supabase (recommended)

1. [supabase.com](https://supabase.com/dashboard) → **Database** → Direct connection URI (port 5432)
2. `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres
DATABASE_SSL=true
```

3. `make migrate` — extensions (`vector`, `pg_trgm`) + OAuth tables + graph schema

### Local Docker Postgres

```bash
make docker-up
```

Default `DATABASE_URL` from `.env.example` (no SSL).

---

## Secrets

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set `TOKEN_ENCRYPTION_KEY`, `SESSION_SECRET`, and optionally `JWT_SIGNING_KEY` (falls back to `SESSION_SECRET` in dev).

---

## Commands

| Command | Purpose |
|---------|---------|
| `make dev` | API + MCP on port 8000 (reload) |
| `make migrate` | Alembic upgrade |
| `make test` | Server tests |
| `make docker-up` | Local Postgres + Redis |
