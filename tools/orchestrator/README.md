# Foresight build orchestrator

Tooling the orchestrator agent uses to launch and babysit one Cursor Cloud worker agent per implementation ticket (`.scratch/foresight-v1/issues/`), following the ticket dependency graph.

Requires `CURSOR_API_KEY` in the environment. Workers run on `gpt-5.6-sol` (reasoning: high) against `github.com/prasoon2211/foresight`.

- `node launch.mjs <NN>` — launch a cloud worker for ticket NN with the standard worker prompt (read AGENTS.md/CONTEXT.md/ticket/spec, follow the in-repo `implement` skill, implement completely, merge own PR, mark ticket resolved).
- `node watch.mjs <NN> [--interval-s 60]` — poll until the worker run is terminal; print its final report, branch, and PR.
- `node status.mjs [NN...]` — one-line status per tracked worker.
- `node resume.mjs <NN> "message"` — send a follow-up to a worker (corrections, "address review", etc.) and wait.
- `node frontier.mjs` — show merged / in-flight / launchable tickets.

`state.json` records ticket → agent ID → PR so orchestration survives interruptions (cloud agent IDs are resumable across processes). `tickets.mjs` mirrors the `Blocked by:` edges from the ticket files.
