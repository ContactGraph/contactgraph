# Contributing to ContactGraph

Thanks for your interest in contributing! This guide covers how to set up a local environment, run tests, and submit changes.

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (package manager)
- Docker (for local Postgres with pgvector)

## Local setup

```bash
# Install dependencies
uv sync --all-packages --all-extras

# Copy environment template and fill in required values
cp .env.example .env

# Start local Postgres + Redis
make docker-up

# Run migrations
make migrate

# Start the dev server
make dev
```

The server runs at `http://localhost:8000`. See the [README](README.md) for endpoint details.

## Running tests

```bash
make test        # all tests (needs local Postgres)
make lint        # ruff check + format
make typecheck   # pyright
```

CI runs the same checks via GitHub Actions on every pull request.

## Submitting changes

1. Fork the repo and create a feature branch from `main`.
2. Make your changes. Keep commits focused and messages descriptive.
3. Ensure `make test`, `make lint`, and `make typecheck` pass locally.
4. Open a pull request against `main` with a clear description of what changed and why.

## Code style

- We use **ruff** for linting and formatting. Run `make lint` before pushing.
- We use **pyright** in strict mode. All variables — including locals — should have the strongest possible type annotation.
- Avoid comments that merely narrate what the code does. Comment non-obvious intent, trade-offs, or constraints.

## Reporting bugs

Open a [GitHub issue](https://github.com/ContactGraph/contactgraph/issues) with steps to reproduce, expected behavior, and actual behavior.

## Security vulnerabilities

Please **do not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
