# ContactSafe

Agent-native personal graph from Gmail (read-only). MCP tools for connect, sync, and natural-language contact search.

## Quick start

```bash
uv sync --package contactsafe-server --extra dev

cp .env.example .env
# Fill in DATABASE_URL, TOKEN_ENCRYPTION_KEY, SESSION_SECRET, Google OAuth

make migrate
make dev
```

- **Health:** http://localhost:8000/health  
- **MCP:** http://localhost:8000/mcp (trailing slash OK)  
- **Skill:** http://localhost:8000/skill.md  

## Testing locally

1. Start the server: `make dev`
2. Health check:

```bash
curl -s http://localhost:8000/health
```

3. MCP requires auth (expect **401** without a token):

```bash
curl -i -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
```

4. OAuth metadata:

```bash
curl -s http://localhost:8000/.well-known/oauth-authorization-server | jq
```

5. **MCP Inspector** ([github.com/modelcontextprotocol/inspector](https://github.com/modelcontextprotocol/inspector)) → URL `http://localhost:8000/mcp` → complete OAuth or paste a Bearer token from the token exchange.

6. Typical flow in Inspector or curl:
   - `connect_source` → open `oauth_url` in browser → Google consent
   - `sync_source` → poll `get_source_status` until sync completes
   - `query_network` with e.g. `"Who do I know at Sticker VC?"`

7. Run tests: `make test`

## Testing production (`https://www.contactsafe.ai`)

Production is deployed on Railway with custom domain **https://www.contactsafe.ai** (GoDaddy `www` CNAME → Railway).

```bash
curl -s https://www.contactsafe.ai/health
curl -s https://www.contactsafe.ai/.well-known/oauth-protected-resource | jq
curl -s https://www.contactsafe.ai/.well-known/oauth-authorization-server | jq
curl -i -X POST https://www.contactsafe.ai/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
# Expect 401 + WWW-Authenticate with resource_metadata
```

After connecting Gmail in Claude, run **`sync_source`** once (or again after schema changes), then try queries like *"Who do I know at Sticker VC?"* or *"What VCs do I know?"*.

Railway direct URL (fallback): `https://contactsafe-production.up.railway.app` — use **www.contactsafe.ai** for OAuth and MCP clients so redirect URIs and JWT audience stay consistent.

## MCP Inspector (local or production)

Test MCP with [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

- Local: `http://localhost:8000/mcp`
- Production: `https://www.contactsafe.ai/mcp`

## Database

### Supabase (recommended)

1. Create a project at [supabase.com](https://supabase.com/dashboard).
2. **Project Settings → Database** → copy the **URI** (use **Direct connection**, port 5432).
3. Set in `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres
DATABASE_SSL=true
```

URL-encode special characters in the password. On macOS, if SSL fails locally, add `DATABASE_SSL_VERIFY=false`.

4. `make migrate` — creates tables plus `vector` / `pg_trgm` extensions (migration `004`) and OAuth server tables (migration `005`).

### Local Docker Postgres

```bash
make docker-up
```

Use the default `DATABASE_URL` from `.env.example` (no SSL).

## Secrets

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set `TOKEN_ENCRYPTION_KEY` and `SESSION_SECRET` in `.env`.

Set `TOKEN_ENCRYPTION_KEY`, `SESSION_SECRET`, and optionally `JWT_SIGNING_KEY` in `.env`. If `JWT_SIGNING_KEY` is unset, `SESSION_SECRET` is used for MCP JWT signing in development.

## Deploy on Railway

1. Create a Railway project from this repo (uses `Dockerfile` + `railway.toml`).
2. Add **Postgres** or set `DATABASE_URL` to Supabase.
3. Set environment variables (see `.env.example`). **Required for production:**
   - `APP_ENV=production`
   - `BASE_URL=https://www.contactsafe.ai` (must match public URL exactly)
   - `GOOGLE_REDIRECT_URI=https://www.contactsafe.ai/oauth/callback`
   - `JWT_SIGNING_KEY` (separate from `SESSION_SECRET`)
4. Add the same redirect URI in [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
5. Point **www.contactsafe.ai** (GoDaddy CNAME) at your Railway service.
6. Deploy — migrations run automatically on container start.

Verify:

```bash
curl -s https://www.contactsafe.ai/health
curl -s https://www.contactsafe.ai/.well-known/oauth-authorization-server | jq
curl -i -X POST https://www.contactsafe.ai/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
# Expect 401 + WWW-Authenticate with resource_metadata
```

## Claude custom connector

1. Deploy to Railway with `BASE_URL=https://www.contactsafe.ai` (HTTPS required).
2. Claude.ai → **Settings → Connectors → Add custom connector**
3. **URL:** `https://www.contactsafe.ai/mcp`
4. Leave Client ID / Secret empty (uses Dynamic Client Registration).
5. Click **Connect** → Google sign-in → return to Claude.
6. Start a **new chat**, enable the ContactSafe connector.
7. Ask the agent to **`sync_source`** (first time or after updates), wait for sync to finish, then query e.g. *"Who do I know at Sticker VC?"* or *"List my connected sources"*.

Claude uses redirect URI `https://claude.ai/api/mcp/auth_callback` — handled automatically via DCR.

Google OAuth redirect URI for production: `https://www.contactsafe.ai/oauth/callback`

**Note:** Claude.ai may not refresh tokens reliably after expiry (~15 min default). Disconnect/reconnect if tools stop working, or set `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440` for testing.

## MCP authentication (OAuth 2.1 + JWT)

MCP tools require a Bearer access token. Unauthenticated MCP requests receive **401** with a `WWW-Authenticate` header pointing at the protected-resource metadata.

Dynamic Client Registration: `POST /oauth/register` (RFC 7591). Advertised in `/.well-known/oauth-authorization-server` as `registration_endpoint`.

1. Discover auth server: `GET /.well-known/oauth-protected-resource` and `GET /.well-known/oauth-authorization-server`
2. Authorize with PKCE: `GET /oauth/authorize?redirect_uri=...&code_challenge=...&code_challenge_method=S256&state=...`
3. Complete Google consent (ContactSafe redirects back with an authorization `code`)
4. Exchange code: `POST /oauth/token` with `grant_type=authorization_code`, `code`, `redirect_uri`, `code_verifier`
5. Call MCP tools with `Authorization: Bearer <access_token>`

Refresh tokens: `POST /oauth/token` with `grant_type=refresh_token` and `refresh_token`.

Legacy `connect_session_id` parameters still work but are deprecated.

## Google OAuth

1. [Google Cloud Console](https://console.cloud.google.com/) → enable **Gmail API** and **Google Calendar API**.
2. OAuth client (Web) → redirect URI: `http://localhost:8000/oauth/callback`
3. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` in `.env`.

## MCP workflow

### OAuth 2.1 (recommended)

1. Complete OAuth 2.1 PKCE flow (see **MCP authentication** above) to obtain `access_token`
2. Call MCP tools with `Authorization: Bearer <access_token>`
3. **`connect_source`** if Gmail is not connected yet
4. **`sync_source`** — (re)builds the graph; poll **`get_source_status`** until `sync_state` is `partial` or `complete`
5. **`query_network`** (`question`)

### Legacy (deprecated)

1. **`connect_source`** (`source_type`: `google_mail`) → `oauth_url` + `connect_session_id`
2. User completes OAuth in browser
3. **`get_source_status`** (`connect_session_id`) until `status` is `connected`
4. **`list_sources`** → copy `source_id`
5. **`sync_source`** / **`query_network`** with `connect_session_id` or `source_id`

After code or schema changes, run **`sync_source` again** so contacts get `inferred_categories`, org links, and edge flags.

## MCP tools

| Tool | Description |
|------|-------------|
| `connect_source` | Start OAuth for `google_mail` (no Bearer token required) |
| `list_sources` | List sources for authenticated user |
| `sync_source` | Import / refresh Gmail metadata graph |
| `get_source_status` | Connection + sync progress |
| `query_network` | NL search (planner → SQL + optional vectors) |

## Query engine

- **`query_network`** accepts a natural-language `question`; response includes `matches` and `applied_plan`.
- Without `OPENAI_API_KEY`: heuristic planner + category tags from email domains/names and **Gmail snippets** (e.g. outbound “pitch my startup” → likely `vc`).
- With `EXA_API_KEY`: web search enrichment on top contacts during sync (role, org, investor/VC tags from LinkedIn and public profiles).
- With `OPENAI_API_KEY`: LLM query plans and richer ingest enrichment on top contacts; optional excerpt embeddings for semantic questions.

Example questions: “Who do I know named Chris?”, “What VCs do I know?”, “Email for Chris at AIX”, “Who did I talk to about hiring?” (semantic needs OpenAI + excerpts).

## Commands

| Command | Purpose |
|---------|---------|
| `make dev` | API + MCP on port 8000 (reload) |
| `make migrate` | Alembic upgrade |
| `make test` | Server tests |
| `make docker-up` | Local Postgres + Redis |
