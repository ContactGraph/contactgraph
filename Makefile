.PHONY: dev migrate migrate-new sync test lint typecheck docker-up docker-down

sync:
	uv sync

docker-up:
	docker compose up -d

docker-down:
	docker compose down

migrate:
	uv run --package contactsafe-server alembic -c migrations/alembic.ini upgrade head

migrate-new:
	@read -p "Migration message: " msg; \
	uv run --package contactsafe-server alembic -c migrations/alembic.ini revision --autogenerate -m "$$msg"

dev:
	uv run --package contactsafe-server uvicorn contactsafe_server.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run --package contactsafe-server --extra dev pytest packages/server/tests -q

lint:
	uv run ruff check packages
	uv run ruff format --check packages

typecheck:
	uv run pyright
