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

Test MCP with [MCP Inspector](https://github.com/modelcontextprotocol/inspector) → `http://localhost:8000/mcp`.

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

## MCP authentication (OAuth 2.1 + JWT)

MCP tools (except `connect_source`) require a Bearer access token. Unauthenticated requests receive `401` with a `WWW-Authenticate` header pointing at the protected-resource metadata.

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
- With `OPENAI_API_KEY`: LLM query plans and richer ingest enrichment on top contacts; optional excerpt embeddings for semantic questions.

Example questions: “Who do I know named Chris?”, “What VCs do I know?”, “Email for Chris at AIX”, “Who did I talk to about hiring?” (semantic needs OpenAI + excerpts).

## Commands

| Command | Purpose |
|---------|---------|
| `make dev` | API + MCP on port 8000 (reload) |
| `make migrate` | Alembic upgrade |
| `make test` | Server tests |
| `make docker-up` | Local Postgres + Redis |
