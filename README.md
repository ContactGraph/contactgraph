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
7. Ask the agent to run **`sync_source`**, wait until sync finishes, then try *"What VCs do I know?"* or *"Who do I know at Sticker VC?"*

Claude uses redirect URI `https://claude.ai/api/mcp/auth_callback` — handled automatically.

**Note:** If tools stop working after ~15 minutes, disconnect/reconnect the connector (token refresh). For testing, set `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440` on Railway.

### OpenClaw

[OpenClaw](https://docs.openclaw.ai) is a self-hosted AI agent gateway (WhatsApp, Telegram, Control UI, etc.). ContactSafe is a **remote Streamable HTTP MCP server** at `https://www.contactsafe.ai/mcp` with **OAuth 2.1** (same flow as Claude — dynamic client registration, Google sign-in).

You need two things: **MCP tools** (ContactSafe server + auth) and **agent instructions** (the skill file).

#### 1. Install the ContactSafe skill

OpenClaw loads skills from `~/.openclaw/skills`. Copy the published skill so your agent knows the `connect_source` → `sync_source` → `query_network` workflow:

```bash
mkdir -p ~/.openclaw/skills/contactsafe
curl -s https://www.contactsafe.ai/skill.md -o ~/.openclaw/skills/contactsafe/SKILL.md
```

Alternatively, add `https://www.contactsafe.ai/skill.md` to the agent system prompt.

#### 2. Connect ContactSafe (pick one auth method)

**Option A — OAuth plugin (recommended)**

Native OpenClaw MCP config only supports static `Authorization: Bearer …` headers today; ContactSafe expects a full OAuth flow. The [openclaw-mcp-bridge](https://github.com/fsaint/openclaw-mcp-bridge) plugin handles PKCE, dynamic client registration, and token refresh for you.

```bash
npm install openclaw-mcp-bridge
```

Add to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "plugin-mcp-client": {
        "enabled": true,
        "config": {
          "servers": {
            "contactsafe": {
              "url": "https://www.contactsafe.ai/mcp",
              "auth": {
                "scopes": ["contactsafe:read", "contactsafe:write"]
              }
            }
          }
        }
      }
    }
  }
}
```

Restart the gateway (`openclaw gateway restart` — plugin changes require a restart). In chat, run **`/mcp auth contactsafe`**. Your browser opens → sign in with Google → return to OpenClaw.

Tools appear namespaced, e.g. `contactsafe__sync_source`, `contactsafe__query_network`. Use `/mcp tools` to verify.

**Option B — Built-in MCP config (manual Bearer token)**

If you already have a ContactSafe access token (from any MCP client that completed OAuth), register the server via CLI. OpenClaw substitutes `${CONTACTSAFE_MCP_TOKEN}` from your environment at runtime:

```bash
openclaw mcp set contactsafe '{"url":"https://www.contactsafe.ai/mcp","transport":"streamable-http","headers":{"Authorization":"Bearer ${CONTACTSAFE_MCP_TOKEN}"}}'
export CONTACTSAFE_MCP_TOKEN="your-access-token"
openclaw mcp list
```

Changes under `mcp.*` hot-apply without a gateway restart. Tokens expire (~15 minutes by default); reconnect or use Option A for automatic refresh. For longer-lived testing tokens, raise `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` on the ContactSafe deployment.

#### 3. Use it

In whatever channel your OpenClaw agent runs on:

> Connect my Gmail through ContactSafe, run sync, then tell me what investors I know.

The agent should call `connect_source` (you open the Google consent URL once if Gmail is not connected yet), then `sync_source`, poll `get_source_status` until sync completes, and answer via `query_network`.

**Docs:** [OpenClaw MCP CLI](https://docs.openclaw.ai/cli/mcp) · [Configuration reference](https://docs.openclaw.ai/gateway/configuration-reference)

### Gemini (CLI agent)

The [Gemini CLI](https://github.com/google-gemini/gemini-cli) is Google's open-source terminal agent. It supports remote **Streamable HTTP** MCP servers with automatic OAuth discovery — ContactSafe uses the same OAuth 2.1 + DCR flow as Claude.

#### 1. Add ContactSafe as an MCP server

**Via CLI** (writes to `~/.gemini/settings.json`):

```bash
gemini mcp add -s user --transport http contactsafe https://www.contactsafe.ai/mcp
```

**Or edit `~/.gemini/settings.json` directly:**

```json
{
  "mcpServers": {
    "contactsafe": {
      "httpUrl": "https://www.contactsafe.ai/mcp"
    }
  }
}
```

OAuth endpoints are discovered from `/.well-known/oauth-protected-resource` — no Client ID or Secret needed.

#### 2. Authenticate

Start the Gemini CLI, then run:

```
/mcp auth contactsafe
```

Your browser opens → sign in with Google (ContactSafe OAuth) → return to the terminal. Tokens are stored in `~/.gemini/mcp-oauth-tokens.json` and refreshed automatically.

Verify with `/mcp` — you should see ContactSafe tools listed (namespaced as `mcp_contactsafe_*`).

**Headless environments:** OAuth requires a local browser and redirect to `http://localhost:7777/oauth/callback`. It will not work over plain SSH without port forwarding.

#### 3. Teach the agent

Paste `https://www.contactsafe.ai/skill.md` into your first message, or save it locally and `@`-reference it:

> Read https://www.contactsafe.ai/skill.md, then connect my Gmail via ContactSafe, sync, and tell me what investors I know.

#### Gemini Enterprise (org admins)

If you use [Gemini Enterprise](https://cloud.google.com/gemini-enterprise) Agent Designer instead of the CLI, add ContactSafe as a **Custom MCP Server** data store in the Google Cloud console ([docs](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/custom-mcp-server/set-up-custom-mcp-server)):

| Field | Value |
|-------|-------|
| MCP Server URL | `https://www.contactsafe.ai/mcp` |
| Authorization URL | `https://www.contactsafe.ai/oauth/authorize` |
| Token URL | `https://www.contactsafe.ai/oauth/token` |
| Scopes | `contactsafe:read contactsafe:write` |

Gemini Enterprise requires a **pre-registered OAuth client** (not DCR). Register one via `POST https://www.contactsafe.ai/oauth/register` with redirect URI `https://vertexaisearch.cloud.google.com/oauth-redirect`, then enter the returned `client_id` (and `client_secret` if applicable) in the data store config. Enable actions on the data store, connect it to your agent, and authorize Gemini Enterprise when prompted.

**Docs:** [Gemini CLI MCP servers](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md)

### ChatGPT (Developer Mode apps)

ChatGPT supports remote MCP servers as **custom apps** via [Developer Mode](https://developers.openai.com/api/docs/guides/developer-mode) (Plus, Pro, Business, Enterprise, and Education on the web). ContactSafe uses Streamable HTTP + OAuth 2.1 with dynamic client registration — same pattern as Claude.

#### 1. Enable Developer Mode

1. Go to [ChatGPT Settings → Apps](https://chatgpt.com/#settings/Connectors)
2. Open **Advanced settings → Developer mode** and turn it **ON**

Business/Enterprise admins may need to enable **Create custom MCP connectors** under workspace permissions first.

#### 2. Create a ContactSafe app

1. In Apps settings, click **Create app** (visible only in Developer Mode)
2. Fill in:
   - **Name:** `ContactSafe`
   - **MCP server URL:** `https://www.contactsafe.ai/mcp`
   - **Authentication:** **OAuth**
   - Leave Client ID / Client Secret empty — ChatGPT registers via DCR automatically
3. Check **I trust this application**
4. Click **Create** → complete the OAuth sign-in (Google) when redirected

The app appears under **Drafts**. Use the app details page to toggle individual tools on/off and **Refresh** after ContactSafe deploys new tools.

ChatGPT redirect URIs (`https://chatgpt.com/connector_platform_oauth_redirect` or per-app `https://chatgpt.com/connector/oauth/{callback_id}`) are registered automatically through DCR.

#### 3. Use it in a chat

1. Start a **new chat**
2. From the **+** menu, choose **Developer mode** and select your ContactSafe app
3. Prompt explicitly so ChatGPT picks the right tools:

> Using ContactSafe only: read https://www.contactsafe.ai/skill.md, connect my Gmail if needed, run sync_source, wait for sync to complete, then tell me what VCs I know.

Write actions (`sync_source`, `connect_source`) require confirmation by default — review each tool call before approving.

**Tips:** Developer Mode does not work in Agent mode (only Deep Research can use custom apps, read-only). For workspace-wide rollout, admins publish the app from **Workspace Settings → Apps → Drafts**.

**Docs:** [ChatGPT Developer mode](https://developers.openai.com/api/docs/guides/developer-mode) · [Apps SDK authentication](https://developers.openai.com/apps-sdk/build/auth)

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
