# 13 — Real runs: Daytona binding and snapshots

**What to build:** Runs happen for real. The Daytona executor implements the same five-verb protocol the fake does — sandbox from a per-repo snapshot (never auto-stopping mid-run), env files materialized, setup script executed with output captured, agent server launched with the LLM key as process environment only, signed preview URLs and the PTY websocket behind the attach verbs, SSE with mandatory reconnect-and-resync, archive-with-retention instead of destroy at run end.

Around it, the snapshot machinery that makes sandbox starts fast: enabling a repo (and changing its base image, and a manual rebuild action) builds a snapshot with the toolchain, pinned agent runtime, and the repo pre-cloned; build status lives on the repo and gates dispatch — correctness never depends on snapshot freshness because runs always fetch latest code. A "verify setup" action boots a sandbox and runs the setup script with no agent, so a user validates repo config before the first real signal.

This ticket also burns down the interface contract's seven verify-during-build items against real Daytona (SSE through the proxy, signed-URL auth in browsers, TUI attach, env-only provider auth, idle-event semantics, PTY ergonomics, resource caps) — findings recorded as comments here.

**Blocked by:** 08 — Tracer bullet (the protocol and orchestrator); 12 — Result contract (a real run needs the real prompt and extraction).

**Status:** resolved

- [x] The contract test suite written against the protocol in slice 08 passes against the Daytona binding (provider-credentialed suite, excluded from default CI)
- [x] A real smoke run: snapshot build → sandbox → setup → agent serves → trivial prompt → events streamed → transcript exported to Foresight-owned storage → archived → revived → destroyed
- [x] Snapshot build status gates dispatch: a repo with a building or failed snapshot refuses runs with a clear error
- [x] Verify-setup reports success and failure (with captured output) without launching an agent
- [x] All seven verify-during-build items resolved in writing on this ticket

Spec sections: Executor contract, Snapshot and onboarding. Assets: [sandbox + agent-session interface](../assets/sandbox-agent-interface.md), [provider comparison](../assets/sandbox-provider-comparison.md).

## Comments

- **2026-07-12 — Resolved:** Added Daytona execution, snapshot/rebuild/verify machinery, durable exports/logs, retention/revival, and provider contracts in [PR #9](https://github.com/prasoon2211/foresight/pull/9).
- **Verify 1 — SSE:** OpenCode 1.17.18 `/global/event` delivered `server.connected` plus session events through Daytona's header-authenticated preview proxy. The binding opens SSE before `prompt_async`, reconnects, then resynchronizes status/messages.
- **Verify 2 — signed browser URL:** A signed URL plus OpenCode basic auth loaded the web UI and `/global/health`. Daytona/OpenCode returned the requested CORS origin twice; the binding therefore omits `--cors` and V1 uses the working signed OpenCode web UI rather than dashboard cross-origin API fetch.
- **Verify 3 — TUI attach:** `opencode attach` connected to the run session through the signed URL and remained attached until the eight-second contract timeout.
- **Verify 4 — env-only provider auth:** `OPENAI_API_KEY` supplied only to `opencode serve` completed a `gpt-4.1-mini` prompt; `$HOME/.local/share/opencode/auth.json` did not exist.
- **Verify 5 — idle semantics:** The stream emitted session-scoped events and the run's own idle completion after `prompt_async`; completion remains filtered by session ID so child/other-session idle events cannot finish the run.
- **Verify 6 — PTY:** Daytona PTY resize to 120×40 and disconnect/reconnect both worked. Reconnect requires a fresh SDK client because reusing the disconnected client's pooled connection produced `WRONG_VERSION_NUMBER`; the product proxy must reconnect independently. SSE/PTY reconnect remains mandatory for idle drops.
- **Verify 7 — resources:** Daytona allocated exactly 4 vCPU / 8 GiB / 10 GiB; the Debian snapshot started `dockerd` with `fuse-overlayfs`, fetched latest Git code, and ran OpenCode concurrently. This validates the V1 baseline; repos whose real setup exceeds it fail setup with captured logs and need higher account limits.
