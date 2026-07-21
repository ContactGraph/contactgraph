.PHONY: dev migrate migrate-new sync test coverage lint typecheck docker-up docker-down web web-install worker

sync:
	uv sync

docker-up:
	docker compose --profile local-db up -d

docker-down:
	docker compose down

migrate:
	uv run --package contactsafe-server python -m alembic -c migrations/alembic.ini upgrade head

migrate-new:
	@read -p "Migration message: " msg; \
	uv run --package contactsafe-server python -m alembic -c migrations/alembic.ini revision --autogenerate -m "$$msg"

dev:
	uv run --package contactsafe-server python -m uvicorn contactsafe_server.main:app --reload \
		--reload-dir packages/server --reload-dir packages/core \
		--host 0.0.0.0 --port 8000

worker:
	uv run --package contactsafe-server arq contactsafe_server.worker.WorkerSettings

web-install:
	cd apps/web && COREPACK_ENABLE_STRICT=0 pnpm install

web:
	cd apps/web && COREPACK_ENABLE_STRICT=0 pnpm dev

test:
	uv run --package contactsafe-server --extra dev pytest packages/server/tests -q

coverage:
	uv run --package contactsafe-server --extra dev pytest packages/server/tests --cov --cov-report=term-missing --cov-report=html:htmlcov -q

lint:
	uv run ruff check packages
	uv run ruff format --check packages

typecheck:
	uv run pyright
