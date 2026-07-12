# Foresight

Django control plane for the Foresight autonomous software factory.

## Run locally

```bash
docker compose up
```

The command builds the image, migrates Postgres, then starts:

- API and OpenAPI docs: <http://localhost:8000/api/docs>
- health endpoint: <http://localhost:8000/api/health>
- an async Procrastinate worker
- Postgres, shared by Django and Procrastinate

Compose has development-only defaults so a clean clone starts immediately. Copy
`.env.example` to `.env` to override them. Use independently generated secrets
and a strong database password outside local development.

## Test and check

With the compose database running:

```bash
docker compose run --rm web pytest
uv run ruff format --check .
uv run ruff check .
uv run mypy .
```

The tests use real Postgres and execute queued Procrastinate jobs in-process.
