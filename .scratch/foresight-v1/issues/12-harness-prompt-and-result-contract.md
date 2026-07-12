# 12 — Harness prompt and result contract

**What to build:** The two pure ends of a run, completed to spec. At launch, the agent receives a prompt rendered from the repo's harness prompt — Foresight's default ships as a versioned artifact, each repo stores its own editable copy at enable time — by plain substitution of exactly six variables (signal title, signal body, origin URL, repo full name, default branch, generated branch name). At completion, the run's structured result (status, PR URL, summary, confidence) is extracted through the full precedence chain: last `foresight-result` fenced block in the final assistant message → result file read from the sandbox → GitHub PR-existence salvage from the run's branch (work happened, only reporting failed — mark for review) → synthesized failure.

After this ticket, a run's result card is trustworthy even when the agent's reporting isn't: malformed JSON, missing blocks, and silent-but-successful runs all resolve to the right outcome.

**Blocked by:** 08 — Tracer bullet (wire-up points in the orchestrator); 11 — GitHub surface (PR salvage needs the GitHub client).

**Status:** resolved

- [x] Rendering tests: all six variables substituted, signal body wrapped injection-resistantly, manual and GitHub-origin signals both render, branch names unique per run with a predictable prefix
- [x] Extraction precedence over transcript fixtures: happy block; malformed JSON falls through to the file; both missing falls through to PR salvage against the fake GitHub client; everything missing synthesizes a failure with confidence zero
- [x] Result payloads schema-validated; repos created before and after a default-prompt update keep their own copies (default never mutates existing repos)
- [x] End-to-end: a fake run whose scripted transcript ends in a result block lands with the right result columns

Spec sections: Harness prompt and result contract. Asset: [default harness prompt](../assets/default-harness-prompt.md).

## Comments

2026-07-12 — Shipped versioned prompt rendering and resilient structured-result resolution in [PR #8](https://github.com/prasoon2211/foresight/pull/8).
