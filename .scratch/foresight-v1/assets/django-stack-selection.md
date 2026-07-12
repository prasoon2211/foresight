# Django stack selection (research, July 2026)

Facts pass for ticket [03-django-stack-research](../issues/03-django-stack-research.md). All claims checked against primary sources (PyPI, GitHub/Codeberg repos, official docs, Django release notes) in July 2026.

## 1. Auth with org support

**Recommendation: django-allauth (headless mode) for identity; own the org/membership schema ourselves.**

| Option | Maintenance (mid-2026) | Org story |
| --- | --- | --- |
| django-allauth | Active — 65.18.0 released 2026-05-29 ([PyPI](https://pypi.org/project/django-allauth/), [release notes](https://docs.allauth.org/en/dev/release-notes/recent.html)) | None built in — identity only. SAML provider config is keyed by an "organization slug" (`/accounts/saml/<organization_slug>/login/`), so per-org SSO maps cleanly onto our own org model ([SAML docs](https://docs.allauth.org/en/latest/socialaccount/providers/saml.html)) |
| django-organizations | Active — 2.7.0 released 2026-07-03, Django 6 support since 2.6.0 (2026-03-08) ([releases](https://github.com/bennylope/django-organizations/releases)) | Ships its own Organization/OrganizationUser/OrganizationOwner concrete models by default; abstract/base classes let you own the tables ([cookbook](https://django-organizations.readthedocs.io/en/latest/cookbook.html)) |

Details:

- allauth covers email/password with mandatory email verification, OpenID Connect / OAuth social login, SAML 2.0, and MFA. Its `allauth.headless` app exposes a JSON API for SPAs (session-cookie "browser" client and token-based "app" client) and can serve an OpenAPI spec; `HEADLESS_ONLY = True` disables the template views ([headless docs](https://docs.allauth.org/en/latest/headless/installation.html), [config](https://docs.allauth.org/en/latest/headless/configuration.html)). That fits a React SPA and keeps the door open for SSO later.
- allauth deliberately does **not** model organizations or memberships — it is the identity layer only. Since Foresight's schema carries org from day one (and org holds encrypted credentials), owning `Organization` / `Membership` models outright is the right call; the models are small and we avoid coupling core schema to a third-party package's migrations.
- django-organizations is alive (a pleasant surprise — it was widely assumed dormant) and its `organizations.base` abstract classes would let us own the tables. But its value-add is invitation flows and template views we don't need for a V1 SPA; not worth the dependency.

## 2. API layer

**Recommendation: django-ninja, with `@hey-api/openapi-ts` for the typed TS client.**

| Option | Maintenance (mid-2026) | OpenAPI story |
| --- | --- | --- |
| django-ninja | Active — 1.6.2 released 2026-03-18, steady release cadence through 2025–26, ~3M downloads/month ([PyPI](https://pypi.org/project/django-ninja/), [releases](https://github.com/vitalik/django-ninja/releases)) | Built in: OpenAPI 3 schema generated from Pydantic v2 type hints, Swagger UI at `/api/docs`, zero extra packages |
| DRF + drf-spectacular | Active — DRF 3.17.1 (2026-03-24, Django 6 support) ([release notes](https://github.com/encode/django-rest-framework/blob/master/docs/community/release-notes.md)); drf-spectacular 0.30.0 (2026-07-06) ([releases](https://github.com/tfranzel/drf-spectacular/releases)) | Good, but a separate package + config; drf-spectacular stays sub-1.0 and warns every release may break schema output ([README](https://github.com/tfranzel/drf-spectacular)) |

Details:

- Both are healthy; this is not a maintenance-risk decision. It's an ergonomics one: ninja's schema is derived from the same Pydantic v2 types used for runtime validation, so the OpenAPI contract can't drift from behavior — exactly what matters when a generated TS client is the primary consumer. Ninja is also async-first, which pairs well with the SSE/streaming endpoints the control plane needs (ninja 1.5 added JSONL & SSE streaming responses — [releases](https://github.com/vitalik/django-ninja/releases)).
- drf-spectacular's sole maintainer worked through a months-long backlog before 0.30.0 ("After working through the backlog for several weeks, we are finally in a comfortable place again" — [0.30.0 notes](https://github.com/tfranzel/drf-spectacular/releases/tag/0.30.0)); fine, but a single-maintainer schema layer is the weakest link of the DRF path.
- TS client generator: `@hey-api/openapi-ts` generates a typed fetch-based SDK plus optional TanStack Query hooks via plugins; it's the current mainstream choice (~1M weekly npm downloads, used by Vercel/PayPal — [repo](https://github.com/hey-api/openapi-ts)). Orval is the batteries-included alternative (React Query hooks + MSW mocks) but produces far more generated code; `openapi-typescript` is types-only. hey-api is the balanced default.

## 3. Background work

**Recommendation: Procrastinate — Postgres-backed, async-native; run orchestration as async tasks in a dedicated worker process.**

| Option | Maintenance (mid-2026) | Fit for long-lived I/O-bound orchestration |
| --- | --- | --- |
| Procrastinate | Active — 3.9.0 released June 2026 ([releases](https://github.com/procrastinate-org/procrastinate/releases)) | Best: async-first (`async def` tasks recommended usage), workers run many concurrent coroutines, Postgres 13+ is the broker ([README](https://github.com/procrastinate-org/procrastinate/)) |
| Celery | Active — 5.6.3 released 2026-03-26 ([PyPI](https://pypi.org/project/celery/)) | Poor: still no official asyncio task support ([discussion #9049](https://github.com/celery/celery/discussions/9049)); prefork pins one OS process per in-flight task, so 30–120 min watchers starve the pool; needs Redis/RabbitMQ |
| Django 6.0 built-in tasks (`django.tasks`) | Landed in Django 6.0 (Dec 2025) | API/contract only: "Django handles task creation and queuing, but does not provide a worker mechanism"; shipped backends are dev/test only ([6.0 release notes](https://docs.djangoproject.com/en/6.0/releases/6.0/)). Reference backend `django-tasks-db` split out Feb 2026, 0.12.0, status Beta, sync `db_worker` ([PyPI](https://pypi.org/project/django-tasks-db/)) |
| Dramatiq | Active — 2.2.0 released 2026-06-17 ([changelog](https://dramatiq.io/changelog.html)) | Middling: has AsyncIO middleware, but concurrency stays capped at worker-thread count (each thread blocks awaiting its async actor — [cookbook](https://dramatiq.io/cookbook.html)); Postgres broker only via third-party `dramatiq-pg` |

Details:

- The defining workload is run orchestration: a process that watches a sandboxed OpenCode agent for 30–120 minutes, almost all of it waiting on I/O. Procrastinate is the only option where that's the *designed-for* shape: define the orchestrator as an `async def` task and one worker process multiplexes many concurrent runs on an event loop. Webhook ingestion and short jobs are ordinary tasks in the same system.
- Postgres-as-broker eliminates Redis/RabbitMQ from the compose file, and job state lives in the same transactional database as run records — you can defer a job in the same transaction that creates the Run row. Django integration is first-class: `procrastinate.contrib.django`, migrations, `manage.py procrastinate worker` ([Django how-to](https://procrastinate.readthedocs.io/en/stable/howto/django/configuration.html)).
- Crash-safety for long runs: workers heartbeat every 10s; a killed worker's in-flight jobs become "stalled" and a periodic task can requeue them ([stalled-jobs how-to](https://procrastinate.readthedocs.io/en/stable/howto/production/retry_stalled_jobs.html)). The orchestrator task must therefore be resumable (re-attach to the sandbox by run ID), which is good discipline anyway.
- SSE relays to the *browser* are HTTP responses, not queue jobs — serve them from Django's ASGI layer (django-ninja supports SSE streaming responses), reading run state/events from Postgres.
- `django.tasks` is worth adopting *as an interface* later once production backends mature (Procrastinate could even sit behind it), but in July 2026 it can't run our workload by itself; `django-tasks-db`'s worker is synchronous and self-labels Beta.

## 4. Secrets encryption at rest

**Recommendation: django-fernet-encrypted-fields, with keys supplied via env vars in compose.**

| Option | Maintenance (mid-2026) | Notes |
| --- | --- | --- |
| django-fernet-encrypted-fields | Active under Jazzband — 0.4.0 released 2026-04-14, tested against Django 6.0 ([changelog](https://github.com/jazzband/django-fernet-encrypted-fields/blob/main/CHANGELOG.md), [PyPI](https://pypi.org/project/django-fernet-encrypted-fields/)) | Fernet (via `cryptography`) encrypted drop-in fields incl. `EncryptedTextField`, `EncryptedCharField`, `EncryptedJSONField` |
| django-cryptography | **Abandoned** — last release 1.1 in April 2022; nixpkgs removed it as "unmaintained upstream" in March 2026 ([PyPI](https://pypi.org/project/django-cryptography/), [nixpkgs commit](https://github.com/NixOS/nixpkgs/commit/c2d9f8bbc36329cecf4a74d8707b87e6b311825d)); only ad-hoc forks (`django-cryptography-5`) exist | Do not use |
| Hand-rolled Fernet field on `cryptography` | `cryptography` itself is healthy | ~40 lines of custom field code; viable fallback, but the library already is exactly this, maintained and tested |

Details:

- Usage is a drop-in field swap: `api_key = EncryptedTextField()` on the Org credentials model; encryption/decryption happens app-side, the key never reaches Postgres ([README](https://github.com/jazzband/django-fernet-encrypted-fields)).
- Key management: the Fernet key is derived from Django's `SECRET_KEY` plus a `SALT_KEY` setting. For docker-compose, inject both as env vars (secret manager later when cloud-hosted). Rotation is supported two ways: make `SALT_KEY` a list (new key first; decryption tried in order), and/or rotate `SECRET_KEY` using Django's standard `SECRET_KEY_FALLBACKS`; re-save rows to re-encrypt under the new key ([README rotation docs](https://github.com/jazzband/django-fernet-encrypted-fields/blob/main/README.md)).
- Caveat to note in design: encryption keys are coupled to `SECRET_KEY`. If we ever want a master key with a lifecycle independent of Django's signing key, we'd switch to a small custom Fernet field with its own `FERNET_MASTER_KEY` env var (using `MultiFernet` for rotation). Not needed for V1.
- Encrypted fields can't be queried/indexed on content — fine here, since API keys and env files are lookup-by-org, never search-by-value.

## Summary of recommendations

1. **Auth**: django-allauth (headless) for identity; hand-rolled first-class `Organization`/`Membership` models.
2. **API**: django-ninja + `@hey-api/openapi-ts` generated TS client.
3. **Background work**: Procrastinate (Postgres broker, async workers) for webhooks + orchestration; SSE to browser via Django ASGI.
4. **Secrets**: django-fernet-encrypted-fields, env-var keys, salt-list rotation.
