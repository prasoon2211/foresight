# Django stack selection

Type: research
Status: resolved

## Question

Settle the Django-side stock parts with a quick facts pass (best current options, mid-2026):

1. **Auth with org support** — best-maintained option for email/password + SSO-ready auth with organizations/memberships (django-allauth + django-organizations? something newer?). Org model must be first-class since the schema carries org from day one.
2. **API layer** — DRF vs django-ninja for a TypeScript SPA consumer (typed client generation weighs heavily).
3. **Background work** — Celery vs simpler (e.g. Procrastinate, Django tasks) for: webhook ingestion, run orchestration, long-poll/SSE relays to sandboxes. Note the orchestration processes are long-lived and I/O-bound.
4. **Secrets encryption at rest** — app-layer encryption for API keys and env-file contents (library choice, key management story for a compose deployment).

Deliverable: markdown summary with one recommendation each, linked from this ticket.

## Answer

1. **Auth**: django-allauth (headless mode) for identity; own the `Organization`/`Membership` schema ourselves (allauth has no org model by design; django-organizations is alive but adds little for a SPA).
2. **API**: django-ninja (built-in OpenAPI from Pydantic v2 types) + `@hey-api/openapi-ts` for the typed TS client.
3. **Background work**: Procrastinate — Postgres-backed broker, async-native workers that fit 30–120 min I/O-bound orchestration; Celery still has no asyncio task support, and Django 6.0's built-in tasks framework ships no production worker.
4. **Secrets**: django-fernet-encrypted-fields (Jazzband, Django 6-tested) with env-var `SECRET_KEY`/`SALT_KEY` and salt-list rotation; django-cryptography is abandoned (last release 2022).

Full comparison with citations: [../assets/django-stack-selection.md](../assets/django-stack-selection.md)
