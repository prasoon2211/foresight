# AGENTS.md

General rules for how code should be developed in this repo.

## Taling with the User
- Be extremely concise. Sacrifice grammar for the sake of concision.

## Testing

- Prefer testable flows exercised directly via the test suite; do not test UI features.
- Design every library/module so its behavior is testable at the module boundary.
- If a feature needs UI interaction, structure it so the behavior is still testable directly from a test framework.
- Treat the UI as thin wiring over tested modules: if the UI breaks, it's a wiring bug, not a fundamental one.

## Code quality and architecture

- For genuinely non-novel, well-understood problems, don't ask — just write clean, high-quality, well-architected code.
- Prefer deep modules: locality of related features, a simple but powerful interface, testable at the boundary.
- Reject shallow modules: no indirection or extra helper functions "just for the sake of it" unless absolutely required.
- Code is for humans to inspect and understand; reduce complexity by organizing into independent, deep modules that each do one type of thing.

## Decisions

- Easy-to-change decisions: use your best judgment and move on.
- Hard-to-change (one-way) decisions not covered by specs/tickets: still form a best judgment; if one option is a clear winner, go with it. Escalate to the user only when it's genuinely unclear.

## Style

- In React, avoid `useEffect` as much as possible — it makes code hard to understand.
- Prefer pure functions, or functions with as few side effects as you can manage; this keeps code easy to reason about and prevents bugs.

## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage labels are used as-is (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Cursor Cloud specific instructions

- This repo is currently **documentation/specs only** — there is no application code, tests, build, or lint tooling. It holds Markdown (domain glossary `CONTEXT.md`, agent skills under `.agents/skills/`, and the Foresight V1 spec/tickets under `.scratch/foresight-v1/`) plus `skills-lock.json`.
- There are **no dependencies to install** and **no service to run** yet. The startup update script is intentionally a no-op; do not add install/build/run steps until real manifests exist.
- `skills-lock.json` is an agent-skills lockfile (tracks Markdown skills vendored from `mattpocock/skills`), not a package-manager lockfile — don't feed it to npm/pip/etc.
- Planned product (**Foresight**, an autonomous coding-agent control plane) is unbuilt: Django (ASGI) + django-ninja API, PostgreSQL, Procrastinate workers, React/Vite SPA, deployed via `docker compose`. The first implementation step is ticket `.scratch/foresight-v1/issues/07-backend-scaffold.md`, which will introduce the manifests, lint/test/build commands, and services. Once that lands, update the update script and this section accordingly.
