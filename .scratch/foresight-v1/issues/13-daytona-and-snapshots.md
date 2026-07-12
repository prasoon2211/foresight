# 13 — Real runs: Daytona binding and snapshots

**What to build:** Runs happen for real. The Daytona executor implements the same five-verb protocol the fake does — sandbox from a per-repo snapshot (never auto-stopping mid-run), env files materialized, setup script executed with output captured, agent server launched with the LLM key as process environment only, signed preview URLs and the PTY websocket behind the attach verbs, SSE with mandatory reconnect-and-resync, archive-with-retention instead of destroy at run end.

Around it, the snapshot machinery that makes sandbox starts fast: enabling a repo (and changing its base image, and a manual rebuild action) builds a snapshot with the toolchain, pinned agent runtime, and the repo pre-cloned; build status lives on the repo and gates dispatch — correctness never depends on snapshot freshness because runs always fetch latest code. A "verify setup" action boots a sandbox and runs the setup script with no agent, so a user validates repo config before the first real signal.

This ticket also burns down the interface contract's seven verify-during-build items against real Daytona (SSE through the proxy, signed-URL auth in browsers, TUI attach, env-only provider auth, idle-event semantics, PTY ergonomics, resource caps) — findings recorded as comments here.

**Blocked by:** 08 — Tracer bullet (the protocol and orchestrator); 12 — Result contract (a real run needs the real prompt and extraction).

**Status:** ready-for-agent

- [ ] The contract test suite written against the protocol in slice 08 passes against the Daytona binding (provider-credentialed suite, excluded from default CI)
- [ ] A real smoke run: snapshot build → sandbox → setup → agent serves → trivial prompt → events streamed → transcript exported to Foresight-owned storage → archived → revived → destroyed
- [ ] Snapshot build status gates dispatch: a repo with a building or failed snapshot refuses runs with a clear error
- [ ] Verify-setup reports success and failure (with captured output) without launching an agent
- [ ] All seven verify-during-build items resolved in writing on this ticket

Spec sections: Executor contract, Snapshot and onboarding. Assets: [sandbox + agent-session interface](../assets/sandbox-agent-interface.md), [provider comparison](../assets/sandbox-provider-comparison.md).
