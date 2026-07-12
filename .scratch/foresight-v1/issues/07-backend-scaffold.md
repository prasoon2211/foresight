# 07 — Backend scaffold

**What to build:** The prefactor every slice builds inside: a developer clones the repo, runs one compose command, and gets a healthy Django control plane — web, background worker, Postgres — with a passing test suite and CI. The boring decisions (project layout, job queue, API framework, encrypted fields, test conventions) are made once here so no later ticket relitigates them.

Concretely, after this ticket: `docker compose up` yields web + worker + database; a demo background job proves enqueue-in-transaction and worker execution; a health endpoint renders in the OpenAPI docs; the test harness runs real Postgres and executes Procrastinate jobs in-process, per the spec's Testing Decisions. The six-module layout from the spec (core, executor, surfaces, orchestration, api, frontend placeholder) exists as directories with only core as a Django app.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `docker compose up` gives a healthy web (ASGI), worker (Procrastinate), and Postgres; all configuration via environment variables with a documented `.env.example`
- [ ] Test suite green in CI, including one test that enqueues a job inside a transaction and executes it in-process against real Postgres
- [ ] django-ninja mounted; OpenAPI docs render with a health endpoint
- [ ] Encrypted-field support configured (keys via environment) and covered by a round-trip test
- [ ] Lint/format/type-check tooling wired into CI

Spec sections: Architecture, Stack, Testing Decisions. Asset: [Django stack selection](../assets/django-stack-selection.md).
