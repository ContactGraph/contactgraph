# ContactSafe

Agent-native personal graph. Phase 1: MCP server + Google OAuth for Gmail/Calendar.

## Quick start

```bash
# Install dependencies
uv sync

# Start Postgres (and Redis for future workers)
docker compose up -d

# Copy env and fill in Google OAuth + encryption keys
cp .env.example .env

# Run migrations
make migrate

# Start API + MCP server
make dev
```

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
