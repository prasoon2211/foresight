# Sandbox + agent-session interface contract

Resolves [issue 02](../issues/02-sandbox-agent-interface-prototype.md). July 2026.

**Note on method:** the ticket called for a throwaway prototype; the user explicitly decided to skip it and resolve this on paper instead. Claims below are verified against OpenCode's official docs and generated SDK types, and against the [sandbox provider comparison](./sandbox-provider-comparison.md) (Daytona docs). Anything that genuinely needs a running system is listed in [Verify during build](#verify-during-build), not guessed at.

Provider decision (issue 01): **Daytona**. This document defines the interface the control plane owns — the one-way door — and shows Daytona as its first implementation. A future executor (own k8s fleet) implements the same interface.

---

## The one-way door

The control plane owns one abstraction: the **Executor**. Everything provider-specific lives behind it. Two layers, one seam:

- **Provider layer** (varies per executor): sandbox lifecycle, file materialization, process execution, network exposure, PTY. This is the part Daytona/k8s must each implement.
- **Agent-session layer** (identical across executors): talking to `opencode serve` over HTTP. Once the provider layer yields a reachable base URL + credentials, session creation, prompting, and event streaming are plain OpenCode HTTP calls ([server docs](https://opencode.ai/docs/server/)) — shared code, not reimplemented per provider.

The Executor interface below is the outer contract; verbs 2–4 are implemented once in shared code on top of the provider primitives, and only verb 1, the networking primitives, and verb 5 are truly per-provider.

## 1. Interface verbs and payloads

```python
class Executor(Protocol):
    """One instance per run. All state the control plane needs to reconnect
    (sandbox id, session id, URLs) is persisted on the Run row, not held in memory."""

    def create_sandbox(self, spec: SandboxSpec) -> SandboxHandle: ...
    def launch_agent(self, handle: SandboxHandle, launch: AgentLaunch) -> AgentSession: ...
    def get_attach_endpoints(self, handle: SandboxHandle, session: AgentSession) -> AttachEndpoints: ...
    def stream_events(self, handle: SandboxHandle, session: AgentSession) -> Iterator[AgentEvent]: ...
    def destroy(self, handle: SandboxHandle) -> None: ...


@dataclass
class SandboxSpec:
    snapshot: str                     # prebuilt image/snapshot id, repo + toolchain baked in
    env_files: list[EnvFile]          # [(target_path, content)] — secrets, .env files
    setup_script: str | None          # repo-configured; runs before the agent starts
    labels: dict[str, str]            # run_id, repo, trigger — for reconciliation/GC
    resources: Resources | None       # vCPU/RAM/disk; provider defaults if None

@dataclass
class AgentLaunch:
    prompt: str                       # the task, rendered from the signal (issue body etc.)
    model: str                        # "anthropic/claude-..." (provider/model form)
    credentials: dict[str, str]       # {"ANTHROPIC_API_KEY": ...} — env for the agent process ONLY
    server_password: str              # per-run random; basic auth on opencode serve
    output_schema: dict | None        # JSON schema for the final structured report (pr_url, summary)

@dataclass
class AgentSession:
    session_id: str                   # OpenCode session id
    base_url: str                     # control-plane-reachable URL of opencode serve

@dataclass
class AttachEndpoints:
    web_url: str          # browser → opencode web UI (signed, expiring)
    api_url: str          # browser → opencode serve API (signed, expiring; for our dashboard UI)
    terminal_ws: str      # raw shell: PTY-over-WebSocket for our xterm.js web terminal
    tui_command: str      # copy-paste: `opencode attach <signed-url> --session <id> -p <password>`
```

Verb semantics (provider-agnostic):

| Verb | Contract | Daytona binding |
|---|---|---|
| `create_sandbox` | Boot from snapshot, materialize env files at their target paths, run setup script to completion (capturing output), return handle. Sandbox must not auto-terminate while a run is live. | `daytona.create(CreateSandboxFromSnapshotParams(snapshot=..., labels=..., auto_stop_interval=0))` — **`auto_stop_interval=0` is mandatory**, the 15-min default kills runs mid-flight ([comparison, watch-outs](./sandbox-provider-comparison.md)). Env files via `sandbox.fs.upload_file`; setup script via `sandbox.process.exec` ([Python SDK](https://www.daytona.io/docs/en/python-sdk/sync/daytona.md)). |
| `launch_agent` | Start `opencode serve` as a long-lived process with credentials injected as process env; wait for `/global/health`; create a session; submit the prompt asynchronously; return `AgentSession`. | Long-running process via a Daytona process session (`sandbox.process`); reachability via `sandbox.get_preview_link(4096)`. Session + prompt are OpenCode HTTP calls (shared code) — see §3. |
| `get_attach_endpoints` | Return the four attach endpoints; URLs handed to browsers must be time-limited and mintable on demand (they expire; re-call to refresh). | Signed preview URLs (`create_signed_preview_url`) for `web_url`/`api_url`; PTY session over WebSocket (`sandbox.process.create_pty_session`) for `terminal_ws` ([PTY docs](https://www.daytona.io/docs/en/pty/), [preview docs](https://www.daytona.io/docs/en/preview/)). See §4. |
| `stream_events` | Yield normalized `AgentEvent`s from OpenCode's SSE stream; transparently reconnect; surface transport death as a terminal event. | SSE GET on `{preview_url}/global/event` with `x-daytona-preview-token` header + basic auth (shared code). See §5. |
| `destroy` | Tear down the sandbox and all its state. Idempotent. **Caller must harvest persistables first** (§6) — destroy does not save anything. | `sandbox.delete()`. |

Non-verbs, deliberately: no `pause/resume` (not needed for V1, and not all providers have it), no `exec` in the public interface (setup runs inside `create_sandbox`; ad-hoc human shell access goes through `terminal_ws`).

## 2. Repo config → sandbox creation

Per-repo Foresight config (stored in the control plane, editable via dashboard) carries exactly three execution-relevant fields, mapping 1:1 onto `SandboxSpec`:

1. **Base snapshot** — built ahead of time from a Dockerfile (`daytona snapshot create --dockerfile`): Debian/Ubuntu base + Docker-in-Docker + Node/Bun + OpenCode (pinned version) + toolchain + the customer repo pre-cloned. Each run then only needs `git fetch` in the setup script. Prefer Debian over the Alpine `docker:dind` base — musl can bite Bun ([comparison, OpenCode-in-Daytona](./sandbox-provider-comparison.md)).
2. **Env files** — encrypted at rest in the control plane; decrypted and written into the sandbox at creation (`sandbox.fs.upload_file`), never baked into the snapshot. These are the *customer's* app secrets (DB URLs, service keys for the compose stack) — distinct from the agent's LLM credential (§3).
3. **Setup script** — runs after env files land, before the agent starts: `git fetch && git checkout <ref>`, `docker compose up -d`, dependency install. Its exit code gates the run: nonzero → run is `failed` before the agent ever starts, script output persisted as the failure detail.

## 3. Launching the agent

Inside the sandbox, `launch_agent` runs:

```bash
OPENCODE_SERVER_PASSWORD=<per-run-random> \
ANTHROPIC_API_KEY=<byo-key> \
OPENCODE_PERMISSION='{"*":"allow"}' \
opencode serve --hostname 0.0.0.0 --port 4096 --cors https://app.<foresight-domain>
```

- **Key injection.** OpenCode picks up provider API keys from process environment ([CLI docs, auth](https://opencode.ai/docs/cli/): "if there are any keys defined in your environments"). The BYO Anthropic key is env on the `opencode serve` process only — never in the snapshot image, never written to disk by us. We deliberately do **not** use `PUT /auth/:id`, which persists the key to `auth.json` on the sandbox disk ([CLI docs](https://opencode.ai/docs/cli/)); env is invisible to the workspace files the agent edits and dies with the process.
- **Server auth.** `OPENCODE_SERVER_PASSWORD` enables HTTP basic auth on the server (username defaults to `opencode`) — applies to `serve` and `web` ([server docs](https://opencode.ai/docs/server/)). Generated per run by the control plane, stored on the Run row.
- **Permissions.** The sandbox *is* the permission boundary, so the agent runs auto-approved (`OPENCODE_PERMISSION` inline JSON, [CLI env vars](https://opencode.ai/docs/cli/)). If we later want human-gated actions, `permission.updated` events + `POST /session/:id/permissions/:permissionID` give us the hook without changing the interface.
- **Bind and CORS.** `--hostname 0.0.0.0` (default is `127.0.0.1`, unreachable through the preview proxy); `--cors` with our dashboard origin so the user's browser can call the API directly (§4).

Then, from the control plane over the preview URL (shared OpenCode-HTTP code, [server docs](https://opencode.ai/docs/server/)):

1. Poll `GET /global/health` until healthy.
2. `POST /session` `{title: "<run title>"}` → `Session` (capture `session_id`).
3. Subscribe `stream_events` **before** submitting the prompt (no completion events missed).
4. `POST /session/:id/prompt_async` with `{model, parts: [{type:"text", text: prompt}]}` → `204`, fire-and-forget; completion arrives on the event stream. (The synchronous `POST /session/:id/message` blocks for the whole run — wrong shape for a 30–120 min job.)
5. The prompt instructs the agent to finish with a final report; using the structured-output `format: json_schema` option on the closing prompt ([SDK docs](https://opencode.ai/docs/sdk/)) gives us a machine-parseable `{pr_url, summary, outcome}` instead of regexing prose.

`opencode run` (non-interactive, [CLI docs](https://opencode.ai/docs/cli/)) was considered and rejected as the primary mechanism: it's a one-shot process without the always-on server the attach model needs. It remains useful for smoke tests (`opencode run --attach <url>` against a live sandbox).

## 4. Attach model — the auth/networking triangle

Three parties: **control plane** (Django), **sandbox** (`opencode serve` on :4096 + Daytona PTY), **user's browser/terminal**. The control plane is the credential broker; nothing reaches the sandbox without going through credentials it minted.

```
control plane ──(preview URL + x-daytona-preview-token header + basic auth)──▶ sandbox :4096
user browser ──(signed expiring preview URL + basic auth)────────────────────▶ sandbox :4096
user browser ──(control-plane websocket ──▶ Daytona PTY websocket)───────────▶ sandbox shell
user terminal ─(opencode attach <signed-url> -p <password>)──────────────────▶ sandbox :4096
```

- **Control plane → sandbox:** `sandbox.get_preview_link(4096)` + `x-daytona-preview-token` header ([preview docs](https://www.daytona.io/docs/en/preview/)), plus OpenCode basic auth. Two independent locks: Daytona's proxy gate and OpenCode's own password.
- **Browser → OpenCode (web UI / live session view):** control plane mints a **signed, expiring preview URL** (`create_signed_preview_url(4096)`) on click and hands it plus the basic-auth credential to the authenticated dashboard user. Two options, both supported by the same endpoints: (a) the user opens OpenCode's own web UI — `opencode web` and `opencode serve` are the same server, web serves the UI on top ([web docs](https://opencode.ai/docs/web/)); simplest is to run `opencode web` instead of `opencode serve` as the agent process, same flags, same API; or (b) our dashboard renders the session itself by calling the API cross-origin — this is what `--cors <dashboard-origin>` is for. Daytona's proxy passes WebSockets and SSE ([comparison](./sandbox-provider-comparison.md)). Signed URLs expire: the dashboard re-requests a fresh one from the control plane, never caches.
- **Browser → raw shell (web terminal):** our own xterm.js against Daytona's PTY WebSocket (`sandbox.process.create_pty_session`, with resize + reconnect — [PTY docs](https://www.daytona.io/docs/en/pty/)), proxied through a control-plane WebSocket endpoint that enforces dashboard auth and holds the Daytona API key server-side. Daytona's built-in :22222 web terminal is org-member-only and not for end users ([comparison](./sandbox-provider-comparison.md)).
- **Terminal → live TUI:** `opencode attach <url>` connects a local TUI to a remote server, with `--session <id>` to land in the run's session and `-p/-u` for basic auth ([CLI docs](https://opencode.ai/docs/cli/)). The dashboard shows a copy-paste command with a signed URL. Human and agent share the session — the human can watch, steer, or take over mid-run; that's the point.

## 5. Event stream → run status

The control plane subscribes to OpenCode's SSE stream through the preview URL. First event is `server.connected`, then bus events ([server docs](https://opencode.ai/docs/server/)). **Use `GET /global/event`**: the instance-scoped `/event` endpoint has a known delivery regression ([opencode#26866](https://github.com/anomalyco/opencode/issues/26866) — stream goes silent after `server.connected` in some 1.14.x versions; `/global/event` is the reported workaround). Pin the OpenCode version in the snapshot and verify end-to-end during build.

Event kinds (verified against the generated SDK types, [`types.gen.ts`](https://github.com/sst/opencode/blob/dev/packages/sdk/js/src/gen/types.gen.ts), the source of truth generated from the server's OpenAPI spec):

| Group | Events | Foresight use |
|---|---|---|
| Server | `server.connected`, `server.instance.disposed`, `global.disposed` | stream liveness |
| Session lifecycle | `session.created`, `session.updated`, `session.deleted`, `session.status` (`idle`\|`busy`\|`retry`), **`session.idle`**, **`session.error`**, `session.compacted`, `session.diff` | run status (below) |
| Messages | `message.updated`, `message.removed`, `message.part.updated`, `message.part.removed` | live progress display; harvesting the final report |
| Permissions | `permission.updated`, `permission.replied` | human-gate hook (unused in V1 auto-approve mode) |
| Workspace | `file.edited`, `todo.updated`, `command.executed`, `file.watcher.updated`, `vcs.branch.updated` | activity feed |
| PTY / TUI / infra | `pty.*`, `tui.*`, `lsp.*`, `installation.*` | ignored by the control plane |

Run-status mapping (control-plane state machine; sandbox/OpenCode never own status):

| Run status | Derived from |
|---|---|
| `provisioning` | `create_sandbox` in progress (no events yet) |
| `running` | prompt submitted; `session.status: busy`/`retry`, `message.*` flowing |
| `awaiting_review` | `session.idle` for our session **and** final structured output reports success with a PR URL — agent done, human review is the next actor. Also: `permission.updated` unanswered (if human-gating ever enabled). |
| `done` | run closed out after review/merge (control-plane action, not an OpenCode event) |
| `failed` | any of: `session.error` (payload carries `ProviderAuthError` \| `APIError` \| `MessageAbortedError` \| …, [types.gen.ts](https://github.com/sst/opencode/blob/dev/packages/sdk/js/src/gen/types.gen.ts)); `session.idle` with missing/failed structured output; setup script nonzero exit; SSE transport death that reconnection can't recover (sandbox died) |

Completion detection is `session.idle` for **our** session ID (`prompt_async` returns 204 immediately; idle is the only completion signal). Reconnect logic is mandatory: SSE drops are routine over any proxy; on reconnect, `GET /session/status` + `GET /session/:id/message` resynchronize state, so a dropped stream never wedges a run.

## 6. Teardown and persistence

**Everything inside the sandbox dies with `destroy`.** OpenCode stores all session/message data on local disk at `~/.local/share/opencode/project/<slug>/storage/` (plus `auth.json` and logs under the same root) — [troubleshooting docs](https://opencode.ai/docs/troubleshooting/). There is no OpenCode cloud persistence in our setup (we do not use session sharing). The workspace, the compose stack, docker images — all gone.

Before `destroy`, the control plane harvests (order matters — harvest, persist, only then delete):

| Artifact | How | Required? |
|---|---|---|
| Outcome + PR URL + summary | final message's structured output (`GET /session/:id/message/:messageID` or captured from `message.updated`) | **yes** — this *is* the run result |
| Session transcript | `opencode export <sessionID>` inside the sandbox (JSON, `--sanitize` available) or `GET /session/:id/message` dump from outside ([CLI docs](https://opencode.ai/docs/cli/)) | yes for V1 — cheap, invaluable for debugging; store in object storage keyed by run |
| Setup/agent process logs | captured at exec time (`create_sandbox`/`launch_agent` already hold them) | yes |
| Final diff | `GET /session/:id/diff` | optional — the PR itself carries the diff |

What we deliberately do **not** persist: the workspace (the PR branch on GitHub is the durable artifact), the sandbox filesystem, OpenCode's internal storage directory as-is (the export covers it).

The PR must be pushed by the agent *during* the run (it has repo credentials via env files / git config in the snapshot); teardown never depends on extracting uncommitted work. If a run fails before a PR exists, the transcript + logs are the whole story.

`destroy` also runs from a reconciliation sweep: any Daytona sandbox whose `run_id` label maps to a terminal-state run (or to no run) gets harvested-if-possible and deleted, so leaked sandboxes can't accumulate spend.

## Verify during build

Points that only a running system can settle — none block the interface shape, all are binding-level:

1. **SSE delivery end-to-end**: `/global/event` vs `/event` regression ([opencode#26866](https://github.com/anomalyco/opencode/issues/26866)) — pin an OpenCode version where the chosen endpoint demonstrably streams through the Daytona preview proxy without buffering (OpenCode sends `X-Accel-Buffering: no`, but verify once).
2. **Signed preview URL + basic auth in the browser**: confirm the browser's basic-auth prompt (or credential-in-URL) works through Daytona's signed-URL proxy for both the `opencode web` UI and cross-origin `fetch` from our dashboard; confirm the exact `--cors` origin needed (our dashboard origin vs the proxy domain).
3. **`opencode attach` through the proxy**: TUI attach uses the same HTTP+SSE API, but verify it tolerates the signed-URL query token end-to-end (token survives all request paths the TUI makes).
4. **Env-var-only provider auth**: confirm `ANTHROPIC_API_KEY` in the serve process env is sufficient with zero `auth.json` (expected per docs; also decide model pinning behavior when the config specifies an unavailable model).
5. **`session.idle` semantics**: exact ordering with `prompt_async`, and whether subagent child sessions emit their own idle events that must be filtered by session ID.
6. **Daytona PTY ergonomics**: reconnect-after-drop and resize behavior under our xterm.js wrapper; preview-proxy idle timeouts for hours-long SSE/WebSocket connections (reconnect logic is designed in regardless).
7. **Per-sandbox resource cap** (4 vCPU / 8 GiB / 10 GiB default, [comparison](./sandbox-provider-comparison.md)): a real customer compose stack + dockerd + OpenCode + LSPs must fit; measure with a representative repo.

## Sources

- OpenCode: [server API](https://opencode.ai/docs/server/) · [CLI (run/attach/serve/web/export, env vars)](https://opencode.ai/docs/cli/) · [web UI](https://opencode.ai/docs/web/) · [SDK & structured output](https://opencode.ai/docs/sdk/) · [storage layout](https://opencode.ai/docs/troubleshooting/) · [event types (`types.gen.ts`)](https://github.com/sst/opencode/blob/dev/packages/sdk/js/src/gen/types.gen.ts) · [SSE regression #26866](https://github.com/anomalyco/opencode/issues/26866)
- Daytona: via the [sandbox provider comparison](./sandbox-provider-comparison.md) (snapshots/DinD, preview URLs, signed URLs, PTY, auto-stop, Python SDK — all primary-source cited there)
