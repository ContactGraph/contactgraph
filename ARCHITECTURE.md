# ContactSafe Architecture Overview

## Monorepo layout

- `packages/core`: shared domain types, enums, and query planning schema used by server and MCP surface.
- `packages/server`: FastAPI application, MCP server, OAuth endpoints, ingestion pipeline, and DB layer.
- `migrations`: Alembic migrations defining the PostgreSQL schema evolution.

## Runtime architecture

The runtime is a single FastAPI process that mounts an MCP server application under `/mcp`.

- **HTTP app composition** (`packages/server/src/contactsafe_server/main.py`):
  - Build settings and app context.
  - Initialize DB lifecycle on startup/shutdown.
  - Build `FastMCP`, wrap it in MCP auth middleware, and mount at configured path.
  - Register OAuth routes and well-known discovery endpoints.
  - Expose health check and static skill file endpoint.

- **Configuration boundary** (`packages/server/src/contactsafe_server/config.py`):
  - Typed environment-driven settings.
  - OAuth, OpenAI, Exa, import, and JWT configuration.
  - Canonical MCP resource and transport-security configuration.

## Layering model

### 1) Interface layer

- **MCP tools** (`packages/server/src/contactsafe_server/mcp/server.py`):
  - `connect_source`, `list_sources`, `get_source_status`, `sync_source`, `describe_graph`, `query_network`.
  - Handles authentication fallback behavior and deprecation bridge for `connect_session_id`.
- **OAuth HTTP routes** (`packages/server/src/contactsafe_server/oauth/`):
  - Authorization, token, callback, and OAuth protected-resource metadata.

### 2) Application services

Service classes encapsulate use cases:

- Source lifecycle (`services/source_service.py`)
- OAuth flows (`services/oauth_service.py`, `services/oauth_server_service.py`)
- Query planning (`services/query_planner.py`, with heuristic fallback)
- Query execution (`services/network_query_service.py`)
- Graph summarization (`services/graph_summary_service.py`)
- Ingestion and enrichment (`services/import_service.py`, `services/ingest_enrichment_service.py`, `services/exa_enrichment.py`, etc.)

### 3) Data layer

- SQLAlchemy async models and relationships in `db/models.py`.
- Session factory / engine lifecycle in `db/connection.py`.
- PostgreSQL-specific features: arrays, JSONB, and pgvector embeddings.

## Data model (high level)

Primary entity groups:

- **Identity & auth:** `User`, `OAuthCredential`, `ConnectSession`, `AuthorizationCode`, `RefreshToken`, `OAuthClient`.
- **Source state:** `Source` tracks connection and sync progress.
- **Graph entities:** `Person`, `Org`.
- **Graph edges:** `PersonEdge` (user↔person interaction strength), `PersonPersonEdge` (co-occurrence), `PersonOrgEdge` (employment/affiliation), `OrgEdge`.
- **Supporting signals:** embeddings and interaction excerpts for semantic and contextual querying.

## Ingestion pipeline

`ImportService.run_sync` orchestrates source sync:

1. Validate source + credential.
2. Pull Gmail message references + metadata in batches.
3. Parse participants and accumulate contact statistics.
4. Upsert `Person` rows and tie-strength edges progressively.
5. Build person-person and org edges.
6. Run enrichment/classification and excerpt extraction.
7. Mark sync state complete/failed with error capture.

Progressive commits are used during ingest to persist partial progress.

## Concurrency model

- Sync scheduling uses in-memory lock sets in `import_scheduler.py`.
- Prevents duplicate per-source and per-user sync jobs in a single process.
- Background execution uses `asyncio.create_task` fire-and-forget workers.

## Query architecture

1. Natural-language question arrives via MCP tool.
2. `QueryPlanner` builds a `QueryPlan` using heuristics and optional LLM JSON planning.
3. `NetworkQueryService` compiles SQL filters for names/orgs/categories/roles/relationship types.
4. Optional semantic path is used when plan intent is `semantic_search`.
5. Results mapped to shared `PersonMatch` schemas from `packages/core`.

## Shared contracts

- `packages/core/src/contactsafe_core/schemas.py`: MCP result and DTO contracts.
- `packages/core/src/contactsafe_core/query_plan.py`: plan schema for planner/executor boundary.
- These provide stable interfaces between tool layer and service layer.

