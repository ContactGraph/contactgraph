# ContactGraph

Your phone contacts are your real professional network — but they're trapped on your phone with no company info, no titles, and no way to search them. ContactGraph fixes that.

1. **Upload phone contacts** — your `.vcf` file becomes your authoritative network in the cloud
2. **Link with LinkedIn** — upload your LinkedIn Connections CSV to match contacts with current company, title, and LinkedIn profile
3. **See your strong professional ties** — people in both your phone and LinkedIn, with accurate employer info, all in one place
4. **Take action** — use your enriched network for job searching, warm intros, fundraising, and recruiting
5. **Connect graphs** — share your ContactGraph with trusted friends to extend your network beyond first degree

The current product focus is **job search**: discover relevant open roles at companies where you have warm connections. Other use cases (fundraising, recruiting, networking) are planned.

**Production:** [https://www.contactgraph.ai](https://www.contactgraph.ai)
**MCP endpoint:** `https://www.contactgraph.ai/mcp`
**Agent skill file:** `https://www.contactgraph.ai/skill.md`

## Quick start for humans

### Claude

1. Claude.ai → **Customize** (top of left sidebar) → **Connectors** → **+** → **Add custom connector**
2. **Name:** `ContactGraph`
3. **Remote MCP server URL:** `https://www.contactgraph.ai/mcp`
4. Leave Client ID / Secret empty (Dynamic Client Registration).
5. Click **Connect** → sign in with Google → return to Claude.
6. Start a **new chat**, enable the ContactGraph connector.
7. Ask the agent to run **`sync_source`**, wait until sync finishes, then try *"What VCs do I know?"* or *"Who do I know at Sticker VC?"*

Claude uses redirect URI `https://claude.ai/api/mcp/auth_callback` — handled automatically.

**Note:** If tools stop working after ~15 minutes, disconnect/reconnect the connector (token refresh). For testing, set `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440` on Railway.

### OpenClaw

[OpenClaw](https://docs.openclaw.ai) is a self-hosted AI agent gateway (WhatsApp, Telegram, Control UI, etc.). ContactGraph is a **remote Streamable HTTP MCP server** at `https://www.contactgraph.ai/mcp` with **OAuth 2.1** (same flow as Claude — dynamic client registration, Google sign-in).

You need two things: **MCP tools** (ContactGraph server + auth) and **agent instructions** (the skill file).

#### 1. Install the ContactGraph skill

OpenClaw loads skills from `~/.openclaw/skills`. Copy the published skill so your agent knows the `connect_source` → `sync_source` → `query_network` workflow:

```bash
mkdir -p ~/.openclaw/skills/contactgraph
curl -s https://www.contactgraph.ai/skill.md -o ~/.openclaw/skills/contactgraph/SKILL.md
```

Alternatively, add `https://www.contactgraph.ai/skill.md` to the agent system prompt.

#### 2. Connect ContactGraph (pick one auth method)

**Option A — OAuth plugin (recommended)**

Native OpenClaw MCP config only supports static `Authorization: Bearer …` headers today; ContactGraph expects a full OAuth flow. The [openclaw-mcp-bridge](https://github.com/fsaint/openclaw-mcp-bridge) plugin handles PKCE, dynamic client registration, and token refresh for you.

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
            "contactgraph": {
              "url": "https://www.contactgraph.ai/mcp",
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

Restart the gateway (`openclaw gateway restart` — plugin changes require a restart). In chat, run **`/mcp auth contactgraph`**. Your browser opens → sign in with Google → return to OpenClaw.

Tools appear namespaced, e.g. `contactgraph__sync_source`, `contactgraph__query_network`. Use `/mcp tools` to verify.

**Option B — Built-in MCP config (manual Bearer token)**

If you already have a ContactGraph access token (from any MCP client that completed OAuth), register the server via CLI. OpenClaw substitutes `${CONTACTGRAPH_MCP_TOKEN}` from your environment at runtime:

```bash
openclaw mcp set contactgraph '{"url":"https://www.contactgraph.ai/mcp","transport":"streamable-http","headers":{"Authorization":"Bearer ${CONTACTGRAPH_MCP_TOKEN}"}}'
export CONTACTGRAPH_MCP_TOKEN="your-access-token"
openclaw mcp list
```

Changes under `mcp.*` hot-apply without a gateway restart. Tokens expire (~15 minutes by default); reconnect or use Option A for automatic refresh. For longer-lived testing tokens, raise `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` on the ContactGraph deployment.

#### 3. Use it

In whatever channel your OpenClaw agent runs on:

> Connect my Gmail through ContactGraph, run sync, then tell me what investors I know.

The agent should call `connect_source` (you open the Google consent URL once if Gmail is not connected yet), then `sync_source`, poll `get_source_status` until sync completes, and answer via `query_network`.

**Docs:** [OpenClaw MCP CLI](https://docs.openclaw.ai/cli/mcp) · [Configuration reference](https://docs.openclaw.ai/gateway/configuration-reference)

### Gemini (CLI agent)

The [Gemini CLI](https://github.com/google-gemini/gemini-cli) is Google's open-source terminal agent. It supports remote **Streamable HTTP** MCP servers with automatic OAuth discovery — ContactGraph uses the same OAuth 2.1 + DCR flow as Claude.

#### 1. Add ContactGraph as an MCP server

**Via CLI** (writes to `~/.gemini/settings.json`):

```bash
gemini mcp add -s user --transport http contactgraph https://www.contactgraph.ai/mcp
```

**Or edit `~/.gemini/settings.json` directly:**

```json
{
  "mcpServers": {
    "contactgraph": {
      "httpUrl": "https://www.contactgraph.ai/mcp"
    }
  }
}
```

OAuth endpoints are discovered from `/.well-known/oauth-protected-resource` — no Client ID or Secret needed.

#### 2. Authenticate

Start the Gemini CLI, then run:

```
/mcp auth contactgraph
```

Your browser opens → sign in with Google (ContactGraph OAuth) → return to the terminal. Tokens are stored in `~/.gemini/mcp-oauth-tokens.json` and refreshed automatically.

Verify with `/mcp` — you should see ContactGraph tools listed (namespaced as `mcp_contactgraph_*`).

**Headless environments:** OAuth requires a local browser and redirect to `http://localhost:7777/oauth/callback`. It will not work over plain SSH without port forwarding.

#### 3. Teach the agent

Paste `https://www.contactgraph.ai/skill.md` into your first message, or save it locally and `@`-reference it:

> Read https://www.contactgraph.ai/skill.md, then connect my Gmail via ContactGraph, sync, and tell me what investors I know.

#### Gemini Enterprise (org admins)

If you use [Gemini Enterprise](https://cloud.google.com/gemini-enterprise) Agent Designer instead of the CLI, add ContactGraph as a **Custom MCP Server** data store in the Google Cloud console ([docs](https://docs.cloud.google.com/gemini/enterprise/docs/connectors/custom-mcp-server/set-up-custom-mcp-server)):

| Field | Value |
|-------|-------|
| MCP Server URL | `https://www.contactgraph.ai/mcp` |
| Authorization URL | `https://www.contactgraph.ai/oauth/authorize` |
| Token URL | `https://www.contactgraph.ai/oauth/token` |
| Scopes | `contactsafe:read contactsafe:write` |

Gemini Enterprise requires a **pre-registered OAuth client** (not DCR). Register one via `POST https://www.contactgraph.ai/oauth/register` with redirect URI `https://vertexaisearch.cloud.google.com/oauth-redirect`, then enter the returned `client_id` (and `client_secret` if applicable) in the data store config. Enable actions on the data store, connect it to your agent, and authorize Gemini Enterprise when prompted.

**Docs:** [Gemini CLI MCP servers](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md)

### ChatGPT (Developer Mode apps)

ChatGPT supports remote MCP servers as **custom apps** via [Developer Mode](https://developers.openai.com/api/docs/guides/developer-mode) (Plus, Pro, Business, Enterprise, and Education on the web). ContactGraph uses Streamable HTTP + OAuth 2.1 with dynamic client registration — same pattern as Claude.

#### 1. Enable Developer Mode

1. Go to [ChatGPT Settings → Apps](https://chatgpt.com/#settings/Connectors)
2. Open **Advanced settings → Developer mode** and turn it **ON**

Business/Enterprise admins may need to enable **Create custom MCP connectors** under workspace permissions first.

#### 2. Create a ContactGraph app

1. In Apps settings, click **Create app** (visible only in Developer Mode)
2. Fill in:
   - **Name:** `ContactGraph`
   - **MCP server URL:** `https://www.contactgraph.ai/mcp`
   - **Authentication:** **OAuth**
   - Leave Client ID / Client Secret empty — ChatGPT registers via DCR automatically
3. Check **I trust this application**
4. Click **Create** → complete the OAuth sign-in (Google) when redirected

The app appears under **Drafts**. Use the app details page to toggle individual tools on/off and **Refresh** after ContactGraph deploys new tools.

ChatGPT redirect URIs (`https://chatgpt.com/connector_platform_oauth_redirect` or per-app `https://chatgpt.com/connector/oauth/{callback_id}`) are registered automatically through DCR.

#### 3. Use it in a chat

1. Start a **new chat**
2. From the **+** menu, choose **Developer mode** and select your ContactGraph app
3. Prompt explicitly so ChatGPT picks the right tools:

> Using ContactGraph only: read https://www.contactgraph.ai/skill.md, connect my Gmail if needed, run sync_source, wait for sync to complete, then tell me what VCs I know.

Write actions (`sync_source`, `connect_source`) require confirmation by default — review each tool call before approving.

**Tips:** Developer Mode does not work in Agent mode (only Deep Research can use custom apps, read-only). For workspace-wide rollout, admins publish the app from **Workspace Settings → Apps → Drafts**.

**Docs:** [ChatGPT Developer mode](https://developers.openai.com/api/docs/guides/developer-mode) · [Apps SDK authentication](https://developers.openai.com/apps-sdk/build/auth)

---

## Quick start for agents

1. Read the skill file: **`https://www.contactgraph.ai/skill.md`**
2. MCP server: **`https://www.contactgraph.ai/mcp`** (Streamable HTTP; trailing slash OK)
3. Authenticate via OAuth 2.1 Bearer token (see **MCP workflow** below).
4. Typical flow:
   - `connect_source` (`source_type`: `google_mail`) → user opens `oauth_url` → Google consent
   - `sync_source` → poll `get_source_status` until `sync_state` is `partial` or `complete`
   - `start_enrichment` → poll `get_enrichment_status` until complete
   - `query_network` with e.g. `"Who do I know at Sticker VC?"`

After deploys or schema changes, run **`sync_source`** then **`start_enrichment`** again to refresh.

Local development URLs: `http://localhost:8000/mcp`, `http://localhost:8000/skill.md`.

---

## Quick start (developers)

```bash
uv sync --package contactsafe-server --extra dev

cp .env.example .env
# Fill in DATABASE_URL, TOKEN_ENCRYPTION_KEY, SESSION_SECRET, Google OAuth

make migrate
make dev       # API + MCP on :8000
make web       # Web app on :3000 (separate terminal)
```

| Endpoint | Local |
|----------|-------|
| Health | http://localhost:8000/health |
| MCP | http://localhost:8000/mcp |
| Skill | http://localhost:8000/skill.md |
| OAuth metadata | http://localhost:8000/.well-known/oauth-authorization-server |
| Web app | http://localhost:3000 |

---

## Data sources

| Source | Type | What it does |
|--------|------|-------------|
| **Phone contacts** | `.vcf` upload | Your authoritative network — names, phone numbers, emails |
| **LinkedIn Connections** | `.csv` upload | Matches contacts by name/email/URL; adds current company, title, and LinkedIn profile link |
| **Gmail** | OAuth | Email metadata (headers only) for tie strength, relationship signals, and additional contact matching. Google Contacts (People API) are also ingested during Gmail sync. |
| **Google Calendar** | OAuth | Calendar event metadata (attendees, titles, times). Created alongside Gmail on OAuth; must be synced separately with explicit `source_id`. |
| **LinkedIn profile** | PDF upload | Your own work history for your profile |

**Phone contacts are your network. Everything else is enrichment.** The People page shows your phone contacts; LinkedIn and Gmail add company, title, and tie strength data to those contacts. A **strong professional tie** is someone who appears in both your phone and your LinkedIn connections.

### External enrichment APIs

| Provider | Env var | What it does |
|----------|---------|-------------|
| **Exa** | `EXA_API_KEY` | Primary web search enrichment — resolves employer, role, social URLs for contacts via `people` + `personal_site` search |
| **Tavily** | `TAVILY_API_KEY` | Web search fallback when Exa returns no hits |
| **Serper** | `SERPER_API_KEY` | Cheap Google SERP fallback when Exa/Tavily miss |
| **TheirStack** | `THEIRSTACK_API_KEY` | Job discovery — finds open roles at companies where you have connections |
| **ScrapingDog** | `SCRAPINGDOG_API_KEY` | Live LinkedIn profile scraping for strong ties — refreshes employer data beyond the CSV |
| **OpenAI** | `OPENAI_API_KEY` | LLM-powered query plans, richer enrichment synthesis, semantic excerpt search |

---

## Web app

The web dashboard lives in `apps/web` (Next.js) and runs as a separate service.

| Page | Path | Description |
|------|------|-------------|
| Setup | `/setup` | Guided onboarding: upload phone contacts, LinkedIn, connect Gmail |
| People | `/people` | Browse and search your contact graph; CSV export |
| Organizations | `/organizations` | Company-level view with industry, size, enrichment; CSV export |
| Graph | `/graph` | Visual network graph |
| Jobs | `/jobs` | Job discovery — open roles at companies where you have connections (TheirStack) |
| Target Companies | `/target-companies` | Curated org lists for focused job search |
| Sharing | `/sharing` | Trust list management — invite friends to share networks |
| Profile | `/profile` | Your work history, social links, account settings, account deletion |

---

## MCP tools

| Tool | Auth | Description |
|------|------|-------------|
| `connect_source` | Optional | Connect a data source (`google_mail`, `google_calendar`). Returns `oauth_url` when browser consent is needed. |
| `upload_source` | Bearer | Upload file content for `phone_contacts_upload`, `linkedin_connections_upload`, or `linkedin_profile_upload` |
| `list_sources` | Bearer | List connected sources for the user |
| `get_source_status` | Bearer | Connection + sync progress (`pending` \| `syncing` \| `partial` \| `complete` \| `failed`) |
| `sync_source` | Bearer | Import or refresh graph from connected source(s). Without `source_id`, syncs all Gmail sources. |
| `start_enrichment` | Bearer | Kick off background enrichment (web search, employer resolution, role extraction) |
| `get_enrichment_status` | Bearer | Poll enrichment progress |
| `query_network` | Bearer | Natural-language search over the user's graph. Returns `matches` and `second_degree_matches`. |
| `describe_graph` | Bearer | High-level graph summary (contact count, org count, enrichment status) |
| `view_trusted_users` | Bearer | View trust list members, inbound/outbound invites |
| `edit_trusted_users` | Bearer | Add/remove trust list members, accept/decline invites, set privacy labels |
| `dedup_persons` | Bearer | Merge duplicate person records by name |

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
5. Flow: `connect_source` → Google OAuth → `sync_source` → `start_enrichment` → `get_source_status` / `get_enrichment_status` → `query_network`
6. Tests: `make test`

---

## Testing production

Production runs on **Railway** at **https://www.contactgraph.ai** (`www` CNAME → Railway). Always use this URL for OAuth, MCP, and JWT audience — not the raw Railway hostname.

```bash
curl -s https://www.contactgraph.ai/health
curl -s https://www.contactgraph.ai/.well-known/oauth-protected-resource | jq
curl -s https://www.contactgraph.ai/.well-known/oauth-authorization-server | jq
curl -i -X POST https://www.contactgraph.ai/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
# Expect 401 + WWW-Authenticate
```

After connecting Gmail, run **`sync_source`** then **`start_enrichment`** once (or again after upgrades), then query e.g. *"What VCs do I know?"*

Railway fallback hostname: `https://contactgraph-production.up.railway.app` — avoid for OAuth/MCP clients.

MCP Inspector production URL: `https://www.contactgraph.ai/mcp`

---

## MCP workflow (OAuth 2.1)

1. Discover: `GET /.well-known/oauth-protected-resource` and `GET /.well-known/oauth-authorization-server`
2. Authorize with PKCE: `GET /oauth/authorize?...`
3. User completes Google sign-in (grants Gmail, Contacts, and Calendar scopes)
4. Exchange code: `POST /oauth/token` (`grant_type=authorization_code`, PKCE verifier)
5. Call MCP tools with `Authorization: Bearer <access_token>`
6. `connect_source` → `sync_source` → `start_enrichment` → poll status → `query_network`

Refresh: `POST /oauth/token` with `grant_type=refresh_token`.

Dynamic Client Registration: `POST /oauth/register` (RFC 7591).

---

## Graph model and query engine

The schema uses a **three-layer entity-claim graph**:

1. **Entities (global)** — `persons` and `orgs` tables with derived/cached columns. Deduplicated via `person_aliases` and `org_aliases` (email, LinkedIn URL, GitHub URL, domain).
2. **Claims (global, with provenance)** — append-only assertions: `employment_claims`, `relationship_claims`, `person_attribute_claims`, `org_attribute_claims`. Each claim records who contributed it, from what source, when, and at what confidence. Re-syncing upserts in place (idempotent on unique keys).
3. **User observations (per-user)** — `user_person_observations`, `user_relationship_observations`, `user_org_observations` — per-user rollups of email volume, tie strength, and classification flags.

Derived columns on `persons` (current org, role, categories, social profiles, bio) are **recomputed from claims** at the end of each enrichment run.

**Enrichment** uses a queue-based strategy pipeline (`start_enrichment` / `get_enrichment_status`). Strategies include heuristic classification, email-signature parsing, web search (Exa/Tavily/Serper), ScrapingDog LinkedIn scraping, and LLM synthesis. Contacts enriched within `WEB_ENRICHMENT_TTL_DAYS` (default 30) are skipped, making repeat enrichment near-free for API costs.

**`query_network`** accepts a natural-language `question` and returns `matches` (including `also_known_as` aliases), `second_degree_matches` (from trust list connections), and `applied_plan`.

| Config | Effect |
|--------|--------|
| No `OPENAI_API_KEY` | Heuristic query planner + email-domain/name category tags |
| `EXA_API_KEY` | Web search enrichment — employer, role, social URLs for top contacts |
| `TAVILY_API_KEY` | Web search fallback when Exa returns no hits |
| `SERPER_API_KEY` | Cheap Google SERP fallback when Exa/Tavily miss |
| `OPENAI_API_KEY` | LLM query plans, richer enrichment synthesis, semantic excerpt search |
| `THEIRSTACK_API_KEY` | Job discovery — open roles at companies in your network |
| `SCRAPINGDOG_API_KEY` | Live LinkedIn profile scraping for strong ties |

By default, queries **exclude automated senders and newsletters** (`exclude_automated`, `exclude_broadcast`).

Example questions: *"Who do I know named Chris?"*, *"What VCs do I know?"*, *"Who do I know at AIX?"*, *"Who did I talk to about hiring?"* (semantic needs OpenAI + excerpts).

---

## Network sharing

Users can share their professional network with trusted friends via **trust lists**. Sharing is mutual — both sides can browse each other's contacts (names and roles only; emails, phone numbers, and notes are never shared).

- **Invite flow:** enter a friend's email → get a copyable invite message → they sign up (or accept if already on the platform)
- **Second-degree results:** `query_network` returns `second_degree_matches` from trust list members' networks
- **Privacy labels:** per-contact visibility controls (public name+role, or hidden entirely)
- **MCP tools:** `view_trusted_users`, `edit_trusted_users`
- **Web:** `/sharing` page

---

## Job discovery

ContactGraph monitors open roles at companies where you have connections, powered by **TheirStack**.

- **Automatic discovery:** after phone + LinkedIn imports complete, org enrichment runs automatically; job discovery follows for orgs in your target lists
- **Target companies:** curate org lists on the `/target-companies` page to focus discovery
- **Job relevance:** LLM-based filtering scores roles against your work history and preferences (title, location, seniority)
- **Web:** `/jobs` page with inline contact lists showing who you know at each company

---

## Security, privacy, and account deletion

### Data handling

- **OAuth tokens** (Google) are encrypted at rest with Fernet symmetric encryption (`TOKEN_ENCRYPTION_KEY`)
- **JWT Bearer tokens** authenticate all MCP and API requests; signed with `JWT_SIGNING_KEY`
- **Session secrets** protect web app sessions (`SESSION_SECRET`)
- **Email content is never stored** — only message metadata (From, To, Cc, Date headers) for tie strength signals
- **Database** uses Supabase (managed Postgres) with SSL in production (`DATABASE_SSL=true`)

### Privacy model

- Each user's **observations** (tie strength, notes, email counts) are private — other users cannot see them
- **Global entities** (person names, orgs) and **claims** (employment, attributes) are shared across users for deduplication, but queried only through each user's own observation edges
- **Trust list sharing** exposes only names and roles — never emails, phone numbers, or notes
- Per-contact **privacy labels** let users hide specific contacts from shared views

### Account deletion

Users can delete their account from the **Profile** page or via `POST /api/delete-user-account`. Deletion is **immediate** and cascades:

- All user-scoped data is deleted: observations, interaction excerpts, sources, OAuth credentials, trust list memberships, org lists, job preferences, enrichment runs
- Global `persons` and `orgs` entities survive if other users still observe them
- Claims contributed by the deleted user persist with anonymized provenance (`contributor_user_id → NULL`)
- Sessions are orphaned (`user_id → NULL`)

### Data export

- **People** and **Organizations** views support **CSV export** from the web app
- All data originates from user-provided files (VCF, CSV, PDF) and OAuth APIs — users retain their original exports

---

## Google OAuth (Gmail, Contacts, and Calendar)

1. [Google Cloud Console](https://console.cloud.google.com/) → enable **Gmail API**, **People API**, and **Calendar API**
2. OAuth client (Web) → redirect URIs:
   - Local: `http://localhost:8000/oauth/callback`
   - Production: `https://www.contactgraph.ai/oauth/callback`
3. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` in `.env` / Railway

Requested scopes: `openid`, `email`, `profile`, `gmail.readonly` (Gmail source), `contacts.readonly` (Google Contacts, ingested during Gmail sync), `calendar.readonly` (Calendar source).

---

## Deploy on Railway

Two services from this repo:

| Service | Root directory | Config file | Builder |
|---------|----------------|-------------|---------|
| API | `/` (default) | `/railway.api.toml` | Dockerfile |
| WWW | `apps/web` | `/apps/web/railway.toml` | Railpack |

Do **not** use a root `railway.toml` — Railway applies it to every service and
will force the API Dockerfile on the web app.

### API

1. Create a Railway service from this repo (`Dockerfile` + `railway.api.toml`).
2. Postgres or Supabase `DATABASE_URL`.
3. **Required env vars:**
   - `APP_ENV=production`
   - `DATABASE_URL` (Postgres connection string)
   - `TOKEN_ENCRYPTION_KEY` (Fernet key for OAuth token encryption)
   - `SESSION_SECRET`
   - `BASE_URL=https://www.contactgraph.ai`
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI=https://www.contactgraph.ai/oauth/callback`
   - `JWT_SIGNING_KEY` (separate from `SESSION_SECRET`)
4. **Optional env vars** (see `.env.example`):
   - `OPENAI_API_KEY`, `EXA_API_KEY`, `TAVILY_API_KEY`, `SERPER_API_KEY`
   - `THEIRSTACK_API_KEY`, `SCRAPINGDOG_API_KEY`
   - `WEB_BASE_URL` (web app origin, for upload redirect URLs)
   - `ADMIN_EMAILS` (comma-separated, enables admin impersonation)
   - `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default 15)
5. Google Cloud redirect URI must match production callback.
6. CNAME **www.contactgraph.ai** → Railway.
7. **Before deploying** schema changes, run migrations manually against production:

```bash
DATABASE_URL='postgresql+asyncpg://...' DATABASE_SSL=true make migrate
```

8. Deploy — the container starts uvicorn only; it does **not** run Alembic automatically.

### WWW

1. Railway builds from `apps/web` using Railpack.
2. **Required env vars:**
   - `CONTACTGRAPH_API_URL` (e.g. `https://www.contactgraph.ai` — the API origin)
   - `SESSION_SECRET`

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
| `make web` | Next.js web app on port 3000 |
| `make migrate` | Alembic upgrade head |
| `make migrate-new` | Generate new Alembic migration |
| `make test` | Server tests |
| `make coverage` | Tests with coverage report |
| `make lint` | Ruff check + format |
| `make typecheck` | Pyright |
| `make docker-up` | Local Postgres |
| `make docker-down` | Stop local containers |
| `make sync` | `uv sync` |
| `make web-install` | `pnpm install` for web app |
