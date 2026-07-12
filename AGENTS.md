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
