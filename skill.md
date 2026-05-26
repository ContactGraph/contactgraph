# ContactGraph REST API

ContactGraph builds a private contact graph from Gmail, Google Contacts, and other data sources. This document describes the REST API for terminal-based agents and scripts.

## Base URL

| Environment | Base URL |
|-------------|----------|
| **Production** | `https://www.contactgraph.ai` |
| Local dev | `http://localhost:8000` |

All REST endpoints are under `/api`. All requests are `POST` with `Content-Type: application/json`.

## Authentication

Every `/api` request requires an OAuth 2.1 Bearer token:

```
Authorization: Bearer <access_token>
```

### Obtaining a token

ContactGraph implements OAuth 2.1 with PKCE. The flow for a terminal agent:

1. **Register a client** (once):
   ```bash
   curl -s -X POST "$BASE_URL/oauth/register" \
     -H "Content-Type: application/json" \
     -d '{"client_name":"my-agent","redirect_uris":["http://localhost:9999/callback"]}'
   ```

2. **Generate PKCE values:**
   ```bash
   CODE_VERIFIER=$(openssl rand -base64 64 | tr -d '=+/' | head -c 128)
   CODE_CHALLENGE=$(printf '%s' "$CODE_VERIFIER" | openssl dgst -sha256 -binary | base64 | tr '+/' '-_' | tr -d '=')
   STATE=$(openssl rand -hex 16)
   ```

3. **Direct the user to authorize** (open in browser):
   ```
   $BASE_URL/oauth/authorize?redirect_uri=http://localhost:9999/callback&code_challenge=$CODE_CHALLENGE&code_challenge_method=S256&state=$STATE&scope=contactsafe:read+contactsafe:write
   ```

4. **Exchange the authorization code:**
   ```bash
   curl -s -X POST "$BASE_URL/oauth/token" \
     -d "grant_type=authorization_code&code=$CODE&redirect_uri=http://localhost:9999/callback&code_verifier=$CODE_VERIFIER"
   ```
   Response contains `access_token`, `refresh_token`, `expires_in`.

5. **Refresh when expired:**
   ```bash
   curl -s -X POST "$BASE_URL/oauth/token" \
     -d "grant_type=refresh_token&refresh_token=$REFRESH_TOKEN"
   ```

### Admin impersonation

Tokens with `contactsafe:admin` scope can act on behalf of another user by adding:

```
X-On-Behalf-Of: user@example.com
```

The header accepts an email address or a user UUID.

## Setup flow

A typical first-time integration:

```bash
# 1. Connect Google (returns oauth_url for the user to open)
curl -s -X POST "$BASE_URL/api/connect-source" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_type":"google_mail"}'

# 2. After user completes OAuth, start sync
curl -s -X POST "$BASE_URL/api/sync-source" \
  -H "Authorization: Bearer $TOKEN"

# 3. Poll until sync_state is "partial" or "complete" (~30s for partial)
curl -s -X POST "$BASE_URL/api/get-source-status" \
  -H "Authorization: Bearer $TOKEN"

# 4. Also sync Google Contacts (get source_id from list-sources first)
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

### POST /api/connect-source

Connect a data source. Both `google_mail` and `google_contacts` are auto-created when a user connects Google.

**Request body** (all fields optional):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source_type` | string | `"google_mail"` | `"google_mail"` or `"google_contacts"` |
| `user_token` | string | null | User email to check an existing connection |

**Response** (`ConnectSourceResult`):

| Field | Type | Description |
|-------|------|-------------|
| `connect_session_id` | UUID | Session identifier |
| `oauth_url` | string | URL for user to open in browser |
| `status` | string | `"pending"`, `"complete"`, etc. |
| `already_connected` | bool | True if this source is already linked |
| `email` | string? | Connected email address |
| `source_id` | UUID? | Source identifier (if already connected) |
| `access_token` | string? | Returned if already connected |
| `refresh_token` | string? | Returned if already connected |
| `message` | string | Human-readable status |

### POST /api/list-sources

List all connected data sources for the authenticated user. No request body.

**Response** (`ListSourcesResult`):

| Field | Type | Description |
|-------|------|-------------|
| `sources` | array | List of `SourceSummary` objects |
| `message` | string | Human-readable status |

Each `SourceSummary`:

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | UUID | Use with other endpoints |
| `source_type` | string | `"google_mail"`, `"google_contacts"` |
| `label` | string | Display name (usually email) |
| `external_account_id` | string | Google account email |
| `connection_status` | string | `"pending_oauth"`, `"connected"` |
| `sync_state` | string | `"pending"`, `"syncing"`, `"partial"`, `"complete"`, `"failed"` |
| `contacts_found` | int | Raw contacts discovered |
| `contacts_resolved` | int | Contacts processed |
| `contacts_pending` | int | Contacts awaiting processing |

### POST /api/get-source-status

Detailed status for a specific source or the user's primary source.

**Request body** (optional):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source_id` | string | null | Specific source UUID; omit for user default |

**Response** (`SourceStatusResult`): Same fields as `SourceSummary` plus `email`, `scopes`, `connect_session_id`.

### POST /api/sync-source

Start or restart ingestion. Without `source_id`, syncs all Gmail sources for the user.

**Request body** (optional):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source_id` | string | null | Specific source to sync; omit for all Gmail sources |

**Response** (`SyncSourceResult`):

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | UUID | Source that was scheduled |
| `scheduled` | bool | Whether sync was accepted |
| `sync_state` | string | Current state after scheduling |
| `email` | string? | Account email |
| `message` | string | Human-readable status |

### POST /api/query-network

Natural-language search over the contact graph. Wait until sync is `partial` or `complete` before querying.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | string | yes | e.g. `"Who do I know at Stripe?"`, `"find VCs"`, `"engineers in SF"` |

**Response** (`QueryNetworkResult`):

| Field | Type | Description |
|-------|------|-------------|
| `question` | string | Echo of the input |
| `matches` | array | `PersonMatch` objects (first-degree contacts) |
| `second_degree_matches` | array | Contacts visible via trust list (name/org/role only) |
| `applied_plan` | object? | The parsed query plan (for debugging) |
| `message` | string | Human-readable summary |

Each `PersonMatch`:

| Field | Type | Description |
|-------|------|-------------|
| `person_id` | UUID | Stable identifier |
| `name` | string | Full name |
| `emails` | string[] | Known email addresses |
| `org_name` | string? | Current organization |
| `current_role` | string? | Job title |
| `inferred_categories` | string[] | e.g. `["vc", "investor"]` |
| `social_profiles` | object | e.g. `{"linkedin": "..."}` |
| `bio_summary` | string? | Short bio |
| `tie_strength_score` | float | 0.0 to 1.0 |
| `match_reason` | string | Why this person matched |

### POST /api/describe-graph

High-level summary of the user's contact graph. No request body.

**Response** (`DescribeGraphResult`):

| Field | Type | Description |
|-------|------|-------------|
| `total_contacts` | int | All contacts |
| `human_contacts` | int | Real people (not mailing lists) |
| `broadcast_contacts` | int | Newsletters, mailing lists |
| `automated_contacts` | int | Automated senders |
| `queryable_contacts` | int | Contacts available for search |
| `top_categories` | array | `[{"category": "vc", "count": 12}, ...]` |
| `top_orgs` | array | `[{"org_name": "Google", "count": 8}, ...]` |
| `strongest_ties` | array | Top `PersonMatch` objects by tie strength |
| `message` | string | Human-readable summary |

### POST /api/view-trusted-users

View the trust list: active members, pending outbound invites, and inbound invites awaiting response. No request body.

**Response** (`ViewTrustedUsersResult`):

| Field | Type | Description |
|-------|------|-------------|
| `members` | array | Active trust list members |
| `outbound_invites` | array | Invites you've sent |
| `inbound_invites` | array | Invites awaiting your response |
| `max_members` | int | Maximum allowed (20) |
| `message` | string | Human-readable status |

### POST /api/edit-trusted-users

Manage the trust list (max 20 mutual connections). Trust list members can see each other's contacts (name, org, role) in query results.

**Request body** (all fields optional):

| Field | Type | Description |
|-------|------|-------------|
| `add` | string[] | Email addresses to invite |
| `remove` | string[] | Email addresses to remove |
| `accept` | string[] | Invite IDs to accept |
| `decline` | string[] | Invite IDs to decline |
| `set_privacy` | object[] | `[{"person_id": "...", "label": "private"}]` to hide contacts |

**Response** (`EditTrustedUsersResult`):

| Field | Type | Description |
|-------|------|-------------|
| `added` | string[] | Successfully invited |
| `removed` | string[] | Successfully removed |
| `accepted` | string[] | Successfully accepted |
| `declined` | string[] | Successfully declined |
| `privacy_updated` | string[] | Contacts whose privacy was changed |
| `invite_copy` | string? | Suggested invite text for users not yet on ContactGraph |
| `message` | string | Human-readable summary |

## Error responses

All errors return JSON with `detail`:

```json
{"detail": "Bearer token required"}
```

| Status | Meaning |
|--------|---------|
| 401 | Missing or invalid Bearer token |
| 403 | `X-On-Behalf-Of` used without admin scope |
| 404 | User not found (admin impersonation) |
| 422 | Invalid request body |

## Data sources

| `source_type` | Status |
|---------------|--------|
| `google_mail` | Available — Gmail metadata (contacts, orgs, tie strength) |
| `google_contacts` | Available — Google Contacts (names, phones, orgs) |
| `google_calendar` | Planned |

Both Google sources share one OAuth consent. Connecting either auto-creates both.

Multiple Gmail accounts can be linked by calling `connect-source` while authenticated — each account gets its own sources; all contacts merge into one graph.

## Privacy

- Raw email bodies are not stored long-term.
- Tokens are encrypted at rest.
- Per-user data isolation; no cross-user access without explicit trust list consent.
- Free forever for consumers. Your data is never sold. Delete everything anytime.
