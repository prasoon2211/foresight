# 08 — Tracer bullet: manual signal → finished run, over the API

**What to build:** The first thing Foresight *does*, end to end: a client POSTs a manual signal to the API, a run is dispatched, an orchestrator job walks it through its state machine against a (fake) sandbox, and the client can poll the run to `awaiting_review` with its structured result filled in. One thin path through schema, dispatch, orchestration, the executor seam, and the API — deliberately narrow so later slices thicken it rather than restructure it.

This slice carries the load-bearing design decisions, so they land right the first time:

- **Schema, minimal columns only.** Org and Repo as minimal rows (fixture-created; no auth, no GitHub, no config editing yet). Signal with intake state (`received → dispatched`, terminal). Run with the state machine below, executor/sandbox/session identifiers, structured result columns, and the **one-active-run-per-signal partial unique index** — database-enforced, not application bookkeeping. Failure reasons, surface state, and retention columns arrive in later slices.

```text
queued ──▶ provisioning ──▶ running ──▶ awaiting_review ──▶ done
   │             │             │               │
   └─────────────┴─────────────┴───────────────┴──▶ failed(reason)
```

- **The Executor protocol** (from the paper-prototype session — this shape is settled) and the scriptable in-memory FakeExecutor implementing it:

```python
class Executor(Protocol):
    def create_sandbox(self, spec: SandboxSpec) -> SandboxHandle: ...
    def launch_agent(self, handle, launch: AgentLaunch) -> AgentSession: ...
    def get_attach_endpoints(self, handle, session) -> AttachEndpoints: ...
    def stream_events(self, handle, session) -> Iterator[AgentEvent]: ...
    def destroy(self, handle) -> None: ...   # idempotent
```

- **Dispatch as a seam, not an entity**: flip signal intake state, create the Run in `queued`, enqueue the orchestrator job — one transaction.
- **The orchestrator's checkpoint discipline** from the spec's Orchestration section: the job carries only a run ID; every learned fact is written to the Run row before proceeding; every step starts with "already done per the row? skip." Happy path only in this slice.
- **API endpoints**: create manual signal (title, body, repo), list signals with derived outcome status, run detail with state and result. Derived status is a pure function, never stored.

**Blocked by:** 07 — Backend scaffold.

**Status:** claimed

- [ ] The spec's canonical test shape passes: create a manual signal via the API → run jobs in-process with the fake executor scripted to succeed → run walked `queued → provisioning → running → awaiting_review` with result columns filled
- [ ] A concurrent second run for the same signal is rejected by the database index, not by application code
- [ ] Signal outcome status derives correctly from intake state and run states (pure-function tests)
- [ ] Demoable: with compose up and a worker running, a curl session creates a signal and polls the run to completion

Spec sections: Domain model, Orchestration and durability, Executor contract, Testing Decisions. Glossary (`CONTEXT.md`) is canonical for names.
