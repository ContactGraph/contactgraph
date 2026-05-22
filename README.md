# ContactSafe

Agent-native personal graph. Phase 1: MCP server + Google OAuth for Gmail/Calendar.

## Quick start
 
```bash
# Install dependencies
uv sync

# Copy env and fill in secrets (Supabase URL, Google OAuth, encryption keys)
cp .env.example .env

# Run migrations against your database
make migrate

# Start API + MCP server
make dev
```

### Database: Supabase (recommended)

1. Create a project at [supabase.com](https://supabase.com/dashboard).
2. **Project Settings → Database** → copy the **URI** under **Connection string**.
3. Choose **Direct connection** (`db.<project-ref>.supabase.co:5432`) for local dev and migrations.
4. Replace `postgresql://` with `postgresql+asyncpg://` in `.env` as `DATABASE_URL`.
5. If the password has special characters (`@`, `#`, etc.), [URL-encode](https://developer.mozilla.org/en-US/docs/Glossary/Percent-encoding) it.
6. Set `DATABASE_SSL=true` (or rely on auto-detect when the host contains `supabase.co`).

```env
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres
DATABASE_SSL=true
```

7. Run schema migration:

```bash
make migrate
```

8. In Supabase **Table Editor**, you should see `users`, `oauth_credentials`, and `sessions`.

**Optional:** enable `vector` later (**Database → Extensions → vector**) for Phase 2 embeddings.

### Database: local Docker Postgres

```bash
make docker-up   # starts Postgres + Redis (profile local-db)
```

Use the default `DATABASE_URL` from `.env.example` (no SSL).

- **Health:** http://localhost:8000/health
- **MCP:** http://localhost:8000/mcp
- **Skill:** http://localhost:8000/skill.md

## Generate secrets

```bash
python -c "from cryptography.fernet import Fernet; print('TOKEN_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
python -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(32))"
```

## Google OAuth setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable Gmail API and Google Calendar API.
3. Create OAuth 2.0 credentials (Web application).
4. Add redirect URI: `http://localhost:8000/oauth/callback`
5. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`.

## MCP tools (Phase 1)

| Tool | Description |
|------|-------------|
| `connect_gmail` | Returns OAuth URL + session ID |
| `get_import_status` | Poll connection status |

Test with [MCP Inspector](https://github.com/modelcontextprotocol/inspector): connect to `http://localhost:8000/mcp`.
