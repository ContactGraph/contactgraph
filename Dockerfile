FROM python:3.12-slim-bookworm

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/core/src packages/core/src
COPY packages/server/pyproject.toml packages/server/pyproject.toml
COPY packages/server/src packages/server/src
COPY skill.md manifesto.md ./
COPY migrations migrations

RUN uv sync --package contactsafe-server --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["sh", "-c", "uv run --package contactsafe-server uvicorn contactsafe_server.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
