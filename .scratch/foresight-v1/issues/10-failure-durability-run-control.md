# 10 — Failure, durability, and run control

**What to build:** Runs stop being happy-path-only. A user watching a doomed run stops it from the API and it lands `failed(canceled)` with the sandbox torn down. A failed run carries a precise reason from the spec's taxonomy (`setup_failed`, `sandbox_died`, `agent_error`, `agent_reported_failed`, `agent_reported_blocked`, `no_result`, `canceled`) so the user knows whether to fix config, re-run, or take the task themselves. Re-running a signal creates a fresh run in a fresh sandbox. An org at its concurrency cap sees new runs wait in `queued` and start automatically when a slot frees. And none of it is corrupted by a worker dying mid-run: stalled jobs are requeued and resume the same run — reattach and resync, never redo.

Also in this slice: the reconciliation sweep. Sandboxes are created with their run ID in provider labels; a periodic job lists all sandboxes at the provider and destroys any whose run is terminal or unknown, closing every leak class including the created-but-not-yet-recorded crash window.

No automatic retries — that's a spec decision, not an omission. Manual re-run is the universal recovery.

**Blocked by:** 08 — Tracer bullet.

**Status:** ready-for-agent

- [ ] One test per failure reason, each just a differently-scripted fake executor (setup script fails, sandbox dies mid-stream, agent session errors, agent reports failed/blocked, idle without result)
- [ ] Durability: kill the orchestrator after sandbox creation and again after agent launch; re-invoke; exactly-once effects (one sandbox, one session, correct terminal state)
- [ ] Stop via the API mid-run → teardown + `failed(canceled)`; re-run via the API → new run, old run untouched, one-active-run index still holds
- [ ] Concurrency cap: with the cap at one, a second run postpones and starts when the first completes
- [ ] Reconciliation: an orphaned sandbox in the fake executor's inventory is destroyed by the sweep

Spec sections: Orchestration and durability, Failure taxonomy and retry semantics, Testing Decisions; user stories 23, 27, 28, 35.
