# ContactGraph

ContactGraph builds a private contact graph from connected **data sources** so your AI agent can answer questions about the user's network — who they know, where people work, and how strong each relationship is.

The architecture is **source-agnostic**: Gmail is the first connector; more sources (Calendar, LinkedIn, messaging apps, etc.) plug into the same MCP tools and unified graph.

**Free forever for consumers.** We never sell your data. You can delete everything anytime.

## MCP Server

| Environment | URL |
|-------------|-----|
| **Production** | `https://www.contactgraph.ai/mcp` |
| Local dev | `http://localhost:8000/mcp` |

Transport: Streamable HTTP (trailing slash OK).

## Data sources

| `source_type` | Status |
|---------------|--------|
| `google_mail` | **Available** — Gmail metadata → contacts, orgs, tie strength |
| `google_calendar` | Planned |
| Others | Roadmap |

Call `connect_source` with the appropriate `source_type`. Only `google_mail` is implemented today; additional types will use the same tool surface.

## Setup flow (OAuth 2.1)

1. Obtain a Bearer token via OAuth 2.1 PKCE (`/.well-known/oauth-protected-resource`).
2. `connect_source(source_type="google_mail")` — returns `oauth_url` if the user has not connected Google yet. Ask the user to open it and consent.
3. `sync_source` — starts Gmail import (no browser step).
4. Poll `get_source_status` until `sync_state` is `partial` or `complete`.
5. `describe_graph` for a high-level overview, or `query_network(question="...")` for filtered search.

Re-run `sync_source` after ContactGraph upgrades or schema changes.

Legacy `connect_session_id` parameters still work but are deprecated.

## Tools

### `connect_source`

Connect a data source.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_type` | string | No | Default `google_mail`. Future: `google_calendar`, etc. |
| `user_token` | string | No | User email if checking an existing connection |

**Returns:** `oauth_url`, `status`, `message`, `already_connected`, `email`, `source_id`, optional `access_token` if already connected

### `list_sources`

List connected sources. **Requires Bearer token** (or deprecated `connect_session_id`).

### `sync_source`

Start or restart ingestion for a connected source.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_id` | string | No* | From `list_sources` |
| `connect_session_id` | string | No* | Deprecated |

**Returns:** `scheduled`, `sync_state`, `source_id`, `message`

### `get_source_status`

Connection and sync progress.

**Returns:** `connection_status`, `sync_state` (`pending` \| `syncing` \| `partial` \| `complete` \| `failed`), contact counts, `email`, `message`

### `query_network`

Natural-language search over the user's graph.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | string | Yes | e.g. "Who do I know at Stripe?" |
| `source_id` | string | No | Scope to a user resolved via source |
| `connect_session_id` | string | No | Deprecated |

Wait until sync is `partial` or `complete` before querying.

### `describe_graph`

High-level graph summary for broad questions like "who do I know?" or "summarize my network".

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_id` | string | No | Scope to a user resolved via source |
| `connect_session_id` | string | No | Deprecated |

**Returns:** contact counts (total, human, broadcast, automated, queryable), `top_categories`, `top_orgs`, `strongest_ties`, and a short `message`. Follow up with `query_network` for filtered lists.

## Agent pitch (suggested)

> I can search your personal network if we connect your email. ContactGraph builds a private contact graph from Gmail (more sources coming) — read-only, you stay in control. Want me to set it up?

## OAuth scopes (Gmail source today)

- `gmail.readonly` — contact graph from email metadata (no long-term body storage)
- `calendar.readonly` — requested for the upcoming Calendar connector; not ingested yet
- `openid`, `email`, `profile` — identity only

## Privacy

- Raw email bodies are not stored long-term.
- Tokens are encrypted at rest.
- Per-user data isolation; no cross-user access without explicit Trust List consent (future).
