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

Pass a Bearer token on every `/api` request (except `connect-source` and `poll-connect`):

```
Authorization: Bearer <access_token>
```

### Get a token (3 steps)

No client registration, PKCE, or callback server needed.

1. Start a connection (no auth required):

```bash
RESP=$(curl -s -X POST "$BASE_URL/api/connect-source" \
  -H "Content-Type: application/json" \
  -d '{"source_type":"google_mail"}')
SESSION_ID=$(echo "$RESP" | jq -r '.connect_session_id')
OAUTH_URL=$(echo "$RESP" | jq -r '.oauth_url')
```

2. Ask the user to open `$OAUTH_URL` in their browser and complete Google sign-in.

3. Poll until you receive tokens:

```bash
while true; do
  POLL=$(curl -s -X POST "$BASE_URL/api/poll-connect/$SESSION_ID")
  STATUS=$(echo "$POLL" | jq -r '.status')
  if [ "$STATUS" = "connected" ]; then
    TOKEN=$(echo "$POLL" | jq -r '.access_token')
    REFRESH=$(echo "$POLL" | jq -r '.refresh_token')
    break
  fi
  sleep 4
done
```

Tokens are dispensed **once** per session. Store `access_token` and `refresh_token`. Refresh when expired:

```bash
curl -s -X POST "$BASE_URL/oauth/token" \
  -d "grant_type=refresh_token&refresh_token=$REFRESH"
```

### Admin impersonation

Add `X-On-Behalf-Of: user@example.com` (or a user UUID) to act on behalf of another user. Requires `contactsafe:admin` scope.

## Quick start

Connect a user's Google account, sync, and query their contacts:

```bash
# 1. Connect and authenticate (see "Get a token" above)
# After completing OAuth, you have $TOKEN

# 2. Start sync
curl -s -X POST "$BASE_URL/api/sync-source" \
  -H "Authorization: Bearer $TOKEN"

# 3. Poll until sync_state is "partial" or "complete" (~30s for partial)
curl -s -X POST "$BASE_URL/api/get-source-status" \
  -H "Authorization: Bearer $TOKEN"

# 4. Sync Google Contacts too
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

Connect a data source. **No auth required** (for first-time users). Both `google_mail` and `google_contacts` are auto-created on first Google connect.

- `source_type` (string, default `"google_mail"`) — `"google_mail"` or `"google_contacts"`
- `user_token` (string, optional) — user email to check existing connection

Returns `connect_session_id`, `oauth_url` to open in browser, or `access_token` if already connected. Key fields: `already_connected`, `source_id`, `message`.

### POST /api/poll-connect/{connect_session_id}

Poll for OAuth completion and receive tokens. **No auth required.** Use the `connect_session_id` from `connect-source`.

Returns `status` (`pending` | `connected` | `failed`), `message`. When `connected`: includes `access_token`, `refresh_token`, `email`. Tokens are dispensed once per session.

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
