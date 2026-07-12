# Sandbox + agent-session interface contract

Type: prototype
Status: resolved
Blocked by: 01

## Question

Pin down the interface the control plane owns — the one-way door that future executors (own fleet, k8s) must conform to. Prose can't settle this; a working prototype on the chosen provider can. Answer by building the thinnest possible end-to-end slice:

1. Create a sandbox from a prebuilt image, materialize env files, run a setup script.
2. Start `opencode serve` inside it; create a session and hand it a task prompt from outside (SDK or `opencode run --attach`).
3. Attach live from a terminal (`opencode attach --session`) and from a browser (web terminal and/or `opencode web`) while the run is in progress.
4. Subscribe to the SSE `/event` stream from outside and derive a minimal run status from it.
5. Tear down; confirm what survives (session transcript? workspace?) and what we must persist ourselves.

Deliverable: the interface definition (verbs, payloads, auth/networking model between control plane ↔ sandbox ↔ browser) plus the throwaway prototype code linked as an asset. This resolves "who controls the agent and how."

## Answer

Resolved on paper — the throwaway prototype was skipped by explicit user decision; the contract was written directly from OpenCode's official docs/source and the Daytona research instead. Full contract: [sandbox-agent-interface.md](../assets/sandbox-agent-interface.md).

The control plane owns an `Executor` interface with five verbs — `create_sandbox(snapshot, env_files, setup_script)`, `launch_agent(prompt, model, credentials, server_password)`, `get_attach_endpoints()`, `stream_events()`, `destroy()` — where only sandbox lifecycle, networking, and PTY are provider-specific; everything session-related is shared OpenCode-HTTP code (`POST /session`, `prompt_async`, SSE `/global/event`). The BYO Anthropic key is injected as env on the `opencode serve` process only (never `auth.json`, never the image), and the server is locked with a per-run `OPENCODE_SERVER_PASSWORD`. Humans attach via Daytona signed preview URLs (browser → `opencode web`/API, with `--cors`), our xterm.js on Daytona's PTY WebSocket (raw shell), or `opencode attach <signed-url> --session <id>` (TUI). Run status derives from SSE events: `session.status busy` → running, `session.idle` + successful structured output → awaiting_review, `session.error`/failed output/setup failure → failed. Everything in the sandbox dies at destroy (OpenCode stores sessions on sandbox-local disk under `~/.local/share/opencode/`), so the control plane harvests the structured result (PR URL + summary), the transcript export, and process logs before deleting. Genuinely prototype-only unknowns are captured as a seven-item "verify during build" list in the asset (SSE regression #26866 endpoint choice, signed-URL auth in browser, attach-through-proxy, idle-event semantics, PTY reconnects, resource fit).

## Comments

Amendment from the domain-model session (ticket 04): the terminal verb is not an immediate `destroy()`. At run end the control plane (1) performs the **session export** — copies the session data (OpenCode ≥1.2 stores everything in one WAL-mode SQLite file, `~/.local/share/opencode/opencode.db`; prefer `opencode export` JSON, or `.backup`/stop-server-first when copying the DB, and note the DB carries secret-bearing `account`/`credential` tables — empty in our env-only-key setup, but scrub on copy) into Foresight-owned storage as the durable record, then (2) stops and **archives** the sandbox instead of destroying it, with an auto-delete retention window (~14 days), enabling best-effort **revival** to continue the session in its full environment. Archive/revive is an optional executor capability — the Daytona binding gets it nearly free (archived filesystem in object storage, ~30 s restore); a future k8s executor may implement it as a volume snapshot or degrade to no-op. The session export is mandatory and provider-agnostic; nothing depends on the archive.
