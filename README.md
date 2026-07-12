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

## Manual signal tracer

With `docker compose up` running, load the minimal org and repo fixture once:

```bash
docker compose exec web python manage.py loaddata demo
```

Create a manual signal, then poll the returned run ID:

```bash
curl --fail-with-body -X POST http://localhost:8000/api/signals \
  -H 'Content-Type: application/json' \
  -d '{"repo_id":1,"title":"Fix the widget","body":"The widget is broken."}'

curl --fail-with-body http://localhost:8000/api/runs/1
```

The worker advances the run from `queued` through `provisioning` and `running` to
`awaiting_review`, with a deterministic structured result supplied by the fake executor.
