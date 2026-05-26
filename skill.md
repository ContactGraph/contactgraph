---
name: contactgraph
description: "Search a user's personal contact graph built from Gmail and Google Contacts. Use when the user asks about their network, contacts, relationships, who they know, or wants to connect a data source."
compatibility: "Requires curl, jq, and internet access. Works with any agent that can make HTTP requests."
---

# ContactGraph REST API

Build and query a private contact graph from Gmail and Google Contacts via REST.

- Production: `https://www.contactgraph.ai`
- Local dev: `http://localhost:8000`
- All endpoints: `POST` to `/api/*` with `Content-Type: application/json`

## Authentication

Pass an OAuth 2.1 Bearer token on every `/api` request:

```
Authorization: Bearer <access_token>
```

### Obtain a token (OAuth 2.1 PKCE)

1. Register a client (once):

```bash
curl -s -X POST "$BASE_URL/oauth/register" \
  -H "Content-Type: application/json" \
  -d '{"client_name":"my-agent","redirect_uris":["http://localhost:9999/callback"]}'
```

2. Generate PKCE values:

```bash
CODE_VERIFIER=$(openssl rand -base64 64 | tr -d '=+/' | head -c 128)
CODE_CHALLENGE=$(printf '%s' "$CODE_VERIFIER" | openssl dgst -sha256 -binary | base64 | tr '+/' '-_' | tr -d '=')
STATE=$(openssl rand -hex 16)
```

3. Direct the user to authorize (open in browser):

```
$BASE_URL/oauth/authorize?redirect_uri=http://localhost:9999/callback&code_challenge=$CODE_CHALLENGE&code_challenge_method=S256&state=$STATE&scope=contactsafe:read+contactsafe:write
```

4. Exchange the authorization code:

```bash
curl -s -X POST "$BASE_URL/oauth/token" \
  -d "grant_type=authorization_code&code=$CODE&redirect_uri=http://localhost:9999/callback&code_verifier=$CODE_VERIFIER"
```

5. Refresh when expired:

```bash
curl -s -X POST "$BASE_URL/oauth/token" \
  -d "grant_type=refresh_token&refresh_token=$REFRESH_TOKEN"
```

### Admin impersonation

Add `X-On-Behalf-Of: user@example.com` (or a user UUID) to act on behalf of another user. Requires `contactsafe:admin` scope.

## Quick start

Connect a user's Google account, sync, and query their contacts:

```bash
# 1. Connect Google (returns oauth_url for user to open in browser)
curl -s -X POST "$BASE_URL/api/connect-source" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_type":"google_mail"}'

# 2. Start sync after user completes OAuth
curl -s -X POST "$BASE_URL/api/sync-source" \
  -H "Authorization: Bearer $TOKEN"

# 3. Poll until sync_state is "partial" or "complete" (~30s for partial)
curl -s -X POST "$BASE_URL/api/get-source-status" \
  -H "Authorization: Bearer $TOKEN"

# 4. Sync Google Contacts too (grab source_id from list-sources)
CONTACTS_ID=$(curl -s -X POST "$BASE_URL/api/list-sources" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.sources[] | select(.source_type=="google_contacts") | .source_id')

curl -s -X POST "$BASE_URL/api/sync-source" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"source_id\":\"$CONTACTS_ID\"}"

# 5. Query the graph
curl -s -X POST "$BASE_URL/api/query-network" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"Who do I know at Stripe?"}'
```

## Endpoints

All requests are `POST`. All request bodies are JSON. Omit the body for endpoints with no parameters.

### POST /api/connect-source

Connect a data source. Both `google_mail` and `google_contacts` are auto-created on first Google connect.

- `source_type` (string, default `"google_mail"`) — `"google_mail"` or `"google_contacts"`
- `user_token` (string, optional) — user email to check existing connection

Returns `oauth_url` to open in browser, or `access_token` if already connected. Key fields: `already_connected`, `source_id`, `message`.

### POST /api/list-sources

List connected data sources. No body. Returns `sources` array with `source_id`, `source_type`, `sync_state`, `connection_status`, and contact counts for each.

### POST /api/get-source-status

Check sync progress for a source.

- `source_id` (string, optional) — omit for user's primary source

Returns `sync_state` (`pending` | `syncing` | `partial` | `complete` | `failed`), `connection_status`, contact counts, `email`.

### POST /api/sync-source

Start or restart ingestion. Without `source_id`, syncs all Gmail sources for the user.

- `source_id` (string, optional) — specific source to sync

Returns `scheduled` (bool), `sync_state`, `source_id`, `message`.

### POST /api/query-network

Natural-language search over the contact graph. Wait for `sync_state` to reach `partial` or `complete` first.

- `question` (string, required) — e.g. `"Who do I know at Stripe?"`, `"find VCs"`, `"engineers in SF"`

Returns `matches` (array of contacts with name, emails, org, role, categories, tie strength, match reason) and `second_degree_matches` (contacts visible via trust list — name/org/role only).

### POST /api/describe-graph

High-level graph summary. No body. Returns `total_contacts`, `human_contacts`, `top_categories`, `top_orgs`, `strongest_ties`, `message`.

### POST /api/view-trusted-users

View the trust list. No body. Returns `members`, `outbound_invites`, `inbound_invites`, `max_members` (20).

### POST /api/edit-trusted-users

Manage the trust list (max 20 mutual connections).

- `add` (string[], optional) — email addresses to invite
- `remove` (string[], optional) — email addresses to remove
- `accept` (string[], optional) — invite IDs to accept
- `decline` (string[], optional) — invite IDs to decline
- `set_privacy` (object[], optional) — `[{"person_id": "...", "label": "private"}]`

Returns `added`, `removed`, `accepted`, `declined`, `privacy_updated`, and optional `invite_copy` (suggested text to send to users not yet on ContactGraph).

## Errors

All errors return `{"detail": "..."}`.

- 401 — missing or invalid Bearer token
- 403 — `X-On-Behalf-Of` without admin scope
- 404 — user not found (admin impersonation)
- 422 — invalid request body

## Data sources

- `google_mail` — Gmail metadata (contacts, orgs, tie strength)
- `google_contacts` — Google Contacts (names, phones, orgs)
- `google_calendar` — planned

Both Google sources share one OAuth consent. Connecting either auto-creates both. Multiple Gmail accounts can be linked; all contacts merge into one graph.

## Privacy

- Email bodies are not stored long-term
- Tokens encrypted at rest
- Per-user data isolation; no cross-user access without trust list consent
- Free forever for consumers; data never sold; delete anytime
