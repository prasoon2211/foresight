# Foresight V1

Status: ready-for-agent

The build-ready spec for Foresight V1, assembled from the [wayfinder map](map.md). The map's Decisions section records how each choice was reached; the [glossary](../../CONTEXT.md) is canonical for all domain terms used here. Research assets with full detail: [sandbox provider comparison](assets/sandbox-provider-comparison.md), [sandbox + agent-session interface contract](assets/sandbox-agent-interface.md), [default harness prompt](assets/default-harness-prompt.md), [Django stack selection](assets/django-stack-selection.md).

## Problem Statement

Software teams accumulate a long tail of well-understood, bounded work — bug reports, small fixes, cleanup tasks — that arrives faster than engineers can absorb it. Each item is small, but collectively they dominate backlogs and force constant context-switching away from deep work. Coding agents can already complete much of this work end to end, but using one today means an engineer hand-holding it: setting up an environment, pasting in context, babysitting the session, opening the PR themselves. That doesn't scale past one person and one task at a time, has no team workflow around it, and leaves no durable record of what the agent did.

Teams want to point at a ticket and have the fix show up as a reviewable pull request — with the ability to watch the agent work, take over when it goes sideways, and trust that nothing runs outside an isolated environment.

## Solution

Foresight is an autonomous software factory. An org connects its GitHub account, enables repositories, and configures how each repo's environment is built. From then on, labeling a GitHub issue `foresight` (or creating a signal manually in the dashboard) automatically launches a coding agent in an isolated cloud sandbox: it reproduces the problem, fixes it, runs the tests, opens a pull request, and reports back — as a comment on the originating issue and as structured status in the dashboard.

Humans stay in the loop where it counts: they can watch the agent's session live, attach a terminal to it mid-run and steer or take over, review the PR like any other, and re-run a signal if the first attempt disappoints. Everything the agent did is preserved as a session export, so a run is inspectable after the fact. Orgs bring their own LLM API key; the whole control plane deploys with docker compose.

The API is the product and the web dashboard is one client of it: everything a human can do in the UI, an agent with an API token can do over HTTP.

## User Stories

1. As a new user, I want to sign up with email and password (verified) and create an org, so that my team has a tenant to work in.
2. As an org admin, I want to invite teammates and assign them admin or member roles, so that the team shares one Foresight org.
3. As an org admin, I want to store my org's LLM API key (and optional base URL) encrypted in settings, so that agents run on our own account and the key never appears in plaintext.
4. As an org admin, I want to set an org-wide concurrency cap, so that a burst of signals can't launch unbounded sandboxes and unbounded spend.
5. As an org admin, I want to connect our GitHub account by installing the Foresight GitHub App, so that Foresight can read issues, post comments, and open PRs.
6. As an org admin, I want to see which repositories the installation grants and enable individual repos for Foresight, so that only the repos we choose ever get runs.
7. As an org member, I want each enabled repo to get a working default configuration (base image, empty setup script, default harness prompt), so that onboarding a repo doesn't start from a blank page.
8. As an org member, I want to edit a repo's setup script and env files (stored encrypted), so that the sandbox boots into a real, working dev environment for that repo.
9. As an org member, I want to edit the repo's agent harness prompt wholesale — and reset it to Foresight's default — so that I can tune agent behavior per repo without forking the product.
10. As an org member, I want to trigger a snapshot rebuild and see the snapshot's build status, so that sandbox startup stays fast and I can react when a build breaks.
11. As an org member, I want a "verify setup" action that boots a sandbox and runs the setup script without launching an agent, so that I can validate repo configuration before the first real signal arrives.
12. As a developer, I want labeling a GitHub issue `foresight` to create a signal and start a run automatically, so that dispatching work costs one click in the tool I already use.
13. As a developer, I want to create a manual signal in the dashboard (title, body, target repo) that starts a run immediately, so that not every task needs a GitHub issue.
14. As a developer, I want the originating issue to receive a comment when the run starts (with a link to watch) and a status label, so that anyone on GitHub can see Foresight has picked it up.
15. As a developer, I want the issue to receive a comment when the run finishes — linking the PR on success, explaining the failure otherwise — and updated labels, so that the loop closes where the work started.
16. As an org member, I want a signals list showing each signal's outcome status derived from its runs, so that I can see the state of all in-flight and completed work at a glance.
17. As an org member, I want a signal's detail view to list all its runs with their states and results, so that the history of attempts is visible in one place.
18. As an org member, I want signals whose repo has been disconnected to show as stranded, so that I understand why no runs are launching and know reconnecting will revive them.
19. As an org member, I want a run's detail view to show its live state (queued, provisioning, running, awaiting review, done, failed) as it changes, so that I can follow progress without refreshing.
20. As an org member, I want to watch the agent's session live — the conversation, tool calls, and file edits as they happen — so that I can judge whether the run is on track.
21. As an org member, I want a web terminal into the running sandbox, so that I can poke at the environment directly when something looks wrong.
22. As an org member, I want a copy-paste command that attaches my local terminal to the live agent session, so that I can steer or take over the agent mid-run from my own tools.
23. As an org member, I want to stop a running run from the dashboard, so that a clearly doomed run doesn't burn an hour of sandbox time.
24. As a developer, I want a finished run to present its structured result — outcome, PR link, summary, confidence — so that I can triage the output in seconds.
25. As a reviewer, I want the PR to describe what was wrong, what changed, how it was verified, and any judgment calls, so that reviewing an agent PR feels like reviewing a colleague's.
26. As a developer, I want merging the PR to mark the signal done automatically, so that Foresight's status tracks reality without bookkeeping.
27. As a developer, I want to re-run a signal manually (a fresh run, fresh sandbox), so that a failed or unsatisfying attempt doesn't dead-end the signal.
28. As an org member, I want a failed run to carry a precise failure reason (setup failed, sandbox died, agent errored, agent reported failure/blocked, no result, canceled), so that I know whether to fix config, re-run, or take the task myself.
29. As an org member, I want the full session transcript of any finished run preserved and viewable, so that I can audit what the agent actually did — even weeks later, even if the sandbox is long gone.
30. As an org member, I want to briefly revive a recently finished run's sandbox when available, so that I can continue the conversation with full environment context while investigating its work.
31. As an org admin, I want to create and revoke org API tokens, so that agents and scripts can use Foresight without a browser session.
32. As an agent (API client), I want every dashboard capability — create signals, list runs, read statuses and results, fetch transcripts, mint attach endpoints — available over the documented API with a token, so that I can operate Foresight autonomously on a standing instruction.
33. As an agent (API client), I want stable IDs, structured responses, and errors that state what went wrong and what to do next, so that I can drive Foresight without human interpretation.
34. As an operator (self-hoster), I want the control plane to run from docker compose with configuration via environment variables (including the GitHub App credentials and encryption keys), so that deployment is one command on one host.
35. As an operator, I want leaked sandboxes to be found and destroyed automatically by reconciliation, so that provider spend can't silently accumulate from crashes or bugs.
36. As an org admin, I want a disconnected GitHub installation to be represented truthfully (connection revoked, repos disconnected, signals stranded) rather than errored, so that reconnecting later restores the org cleanly.

## Implementation Decisions

### Architecture

- The control plane is a normal Django application, compose-deployable, no exotic infrastructure. Sandboxes are never colocated with it — always created via a remote provider API behind an interface Foresight owns.
- Six modules with a straight-line dependency graph (frontend → api → core ← orchestration → executor, surfaces):
  - **core** — the single Django app holding all domain models and domain rules: intake, dispatch, outcome-status and stranded derivation. Depends on nothing internal. (Deliberately not named after the Signal entity: a Django app named "signals" collides with Django's own signals machinery.)
  - **executor** — the sandbox + agent-session boundary: the Executor protocol, the shared OpenCode-over-HTTP session code, the Daytona binding, and a scriptable in-memory fake for tests.
  - **surfaces** — the origin-surface boundary: the surface adapter protocol, the GitHub adapter (webhook payload interpretation inbound, comments/labels outbound), GitHub App auth plumbing.
  - **orchestration** — the process layer: background jobs (run orchestrator, webhook processing, reconciliation sweep). Coordinates core, executor, and surfaces; owns no domain rules; nothing depends on it.
  - **api** — django-ninja routers translating HTTP into calls on core and executor. Thin by construction; logic found here is a review defect.
  - **frontend** — React SPA consuming the generated typed client. Thin wiring over the API.
- **API-first is an architectural rule, not an aspiration**: every capability ships in the API; the UI consumes only the public API; no UI-only endpoints. This is what makes the V2 MCP server a thin wrapper and agents first-class users.

### Stack

- Backend: Django on Postgres. Identity via django-allauth in headless mode (email/password with mandatory verification in V1; the door stays open for SSO). Org and membership models are owned by core, not a third-party package.
- API: django-ninja with its generated OpenAPI schema; TypeScript client generated via hey-api; API tokens and session cookies both accepted for authentication. Tokens are org-scoped and hashed at rest.
- Background work: Procrastinate — the job queue lives in the same Postgres, jobs are enqueued in the same transaction as the domain writes they relate to, and workers are async (one worker process multiplexes many concurrent orchestrator jobs on an event loop).
- Secrets at rest (org LLM credential, env files, surface connection credentials): encrypted fields via django-fernet-encrypted-fields, keys injected as environment variables, salt-list rotation supported.
- Frontend: React + Vite + TypeScript SPA.

### Domain model

The glossary is canonical; the entities and their load-bearing details:

- **Org** — name, encrypted agent credential (API key + optional base URL), concurrency cap. Users belong via OrgMembership (admin/member).
- **ApiToken** — org-scoped, named, hashed secret, creator, timestamps. V1 tokens carry full org scope; run-scoped tokens are a V2 extension.
- **SurfaceConnection** — one table for all surface types: org, type, status (pending/active/revoked), account label, adapter-owned identity blob and encrypted credentials blob. Unique on (type, external identity) so two orgs can never claim the same GitHub installation. The GitHub App's own credentials (app ID, private key, webhook secret) are per-deployment configuration, not rows.
- **Repo** — org, surface connection, full name, default branch, connection status (connected/disconnected — flipped by webhooks, never deleted), and run config inline: base snapshot reference plus build status, setup script, encrypted env files, harness prompt.
- **Signal** — org, repo, source (github_issue/manual), nullable origin connection (the surface it came from; null for manual signals, which record the creating user), origin reference as an adapter-shaped blob, payload (title, body), stored intake state (`received → dispatched`, permanently ending at dispatched — V2 triage inserts states between them), and adapter-owned surface state (opaque JSONB: comment IDs, applied labels; only the adapter reads or writes it).
- **Run** — signal, state machine below, agent runtime (opencode), executor type and sandbox ID, agent session ID, per-run server password, branch name, structured result columns (status, PR URL, summary, confidence), PR-merged timestamp, failure reason, session-export pointer, sandbox retention state, timestamps. At most one active run per signal, enforced by a partial unique index — not application bookkeeping.
- **Derived, never stored**: outcome status (intake state until dispatched, then from runs — any merged PR means done, else the latest run's state) and stranded (signal whose repo is disconnected; reconnection un-strands automatically).
- Executor and surface adapter are code interfaces, not tables. There are no Sandbox or Session entities — their identifiers ride on Run.

Run state machine (from the domain-model and interface-contract sessions):

```text
queued ──▶ provisioning ──▶ running ──▶ awaiting_review ──▶ done
   │             │             │               │
   └─────────────┴─────────────┴───────────────┴──▶ failed(reason)
```

- `queued`: created, waiting for an org concurrency slot.
- `provisioning`: sandbox creating, env files materializing, setup script running.
- `running`: prompt submitted, agent working.
- `awaiting_review`: agent finished and reported; a human is the next actor.
- `done`: closed out — in V1, the PR merged (webhook-driven).
- `failed`: terminal, with reason (see failure taxonomy).

### Orchestration and durability

Considered Temporal; deferred deliberately (revisit if control-plane workflows ever grow multi-step compensation logic). Instead, the orchestrator is held to a checkpoint discipline that provides the durability V1 needs:

- **State lives on rows, jobs are pointers.** A job carries only a run ID. The moment the orchestrator learns something (sandbox ID, session ID, state change), it writes it to the Run row before proceeding. The queue never holds state.
- **Every step is idempotent via row checks.** Each step begins "is this already done per the row? then skip." A requeued job replays the function from the top and falls through completed steps to wherever it died.
- **Jobs retry; runs don't.** Worker death → the stalled job is requeued and *resumes the same Run* (reattaching to the still-running sandbox). Sandbox or agent death → the Run is marked failed with a reason and the job completes; recovery is a new Run (manual re-run in V1), never a replay.
- **Event stream with resync.** The orchestrator consumes the agent's server-sent event stream (push, not polling); reconnection is mandatory and resynchronizes from session status on reconnect, backstopped by a periodic sandbox liveness check. Completion is the session-idle event for the run's own session.
- **Reconciliation sweep.** Every sandbox is created with its run ID in the provider labels. A periodic job lists all sandboxes at the provider and destroys (after harvesting where possible) any whose run is terminal or unknown — closing the created-but-not-yet-recorded crash window and every other leak class.
- **Concurrency cap by check-and-postpone.** The orchestrator job's first step counts the org's active runs; at cap, it reschedules itself. No slot bookkeeping to corrupt.
- Dispatch (signal → run) is plain code — a seam, not an entity: flip intake state, create the Run, enqueue the job, one transaction. V2 triage inserts itself before this seam without restructuring.

### Executor contract

The one-way door the control plane owns. Five verbs; only sandbox lifecycle, networking, and PTY are provider-specific — session control is shared OpenCode-HTTP code across all executors. Trimmed to the decision (full contract in the interface asset, which came out of the paper-prototype session):

```python
class Executor(Protocol):
    def create_sandbox(self, spec: SandboxSpec) -> SandboxHandle: ...      # snapshot + env files + setup script
    def launch_agent(self, handle, launch: AgentLaunch) -> AgentSession: ...  # opencode serve; key as process env only
    def get_attach_endpoints(self, handle, session) -> AttachEndpoints: ...   # web UI, API, PTY websocket, TUI command
    def stream_events(self, handle, session) -> Iterator[AgentEvent]: ...     # normalized SSE, auto-reconnect
    def destroy(self, handle) -> None: ...                                    # idempotent; caller harvests first
```

- Daytona is the V1 binding (sandboxes must not auto-stop while a run is live; signed preview URLs and the PTY websocket implement attach). A future own-fleet executor implements the same protocol.
- The LLM key is injected as process environment on the agent server only — never baked into snapshots, never written to sandbox disk. The agent server is locked with a per-run random password; browsers reach it only through signed, expiring URLs minted on demand by the control plane; the web terminal is proxied through a control-plane websocket that enforces dashboard auth.
- At run end, in order: harvest the structured result, export the session transcript to Foresight-owned storage (the durable system of record — mandatory), persist setup/agent logs, then archive the sandbox with a retention window (~14 days, auto-delete) instead of destroying it. Revival within the window is a best-effort executor capability; nothing correctness-critical depends on it.
- Human takeover is the same session the agent uses: watching, steering, and taking over are the attach endpoints, not a separate mechanism.

### GitHub integration

- A GitHub App (per-deployment credentials via environment) with webhooks; polling exists only as a documented fallback. Installation events create and update the SurfaceConnection; repository-selection events flip Repo connection status; issue label events create signals; pull-request merge events set the run's merged timestamp (driving done).
- All GitHub API calls use short-lived installation tokens minted from the App credentials; comments and PRs appear under the App's bot identity, which is expected and visible.
- The GitHub surface adapter owns both directions: interpreting inbound webhook payloads into domain actions, and write-back (start/finish comments, status labels) recording what it did in the signal's surface state blob.
- Disconnection is represented truthfully in V1 (statuses flip, signals strand, in-flight runs fail their next GitHub call); recovery UX beyond reconnect-and-resume is deferred.

### Harness prompt and result contract

- Every repo carries the full harness prompt, prefilled with Foresight's default and editable wholesale. Rendering is plain string substitution of exactly six variables: signal title, signal body, signal origin URL, repo full name, default branch, and the control-plane-generated branch name. Anything else the agent needs, it discovers in the repo.
- The agent reports through a fenced result block (info string `foresight-result`) at the end of its final message: status (pr_opened/failed/blocked), PR URL, summary, confidence. A result file in the sandbox is the fallback channel; if both are missing or invalid, the control plane checks GitHub for an open PR from the run's branch (work happened, only reporting failed — mark for review) before synthesizing a failure.
- The agent never merges; its job ends at an open PR. Guardrails (branch discipline, no secrets, no scope creep, when to stop and report failure honestly) are part of the default prompt text (see the prompt asset).

### Failure taxonomy and retry semantics

Failure reasons on Run — each names the next actor:

| Reason | Meaning | Next actor |
| --- | --- | --- |
| `setup_failed` | setup script exited nonzero during provisioning; output preserved as detail | human fixes repo config |
| `sandbox_died` | sandbox vanished mid-run (stream dead and provider confirms gone) | human re-runs |
| `agent_error` | agent runtime raised a session error (auth, API, abort) | human checks credentials/re-runs |
| `agent_reported_failed` | agent finished and honestly reported it could not resolve the signal | human takes the task or re-runs |
| `agent_reported_blocked` | agent reports the environment stopped it | human fixes environment, re-runs |
| `no_result` | session ended with no parseable result and no salvageable PR | human inspects transcript |
| `canceled` | stopped from the dashboard | nobody |

No automatic retries in V1: every failure reason except sandbox death indicates a condition a retry would repeat, and even sandbox death gets a human glance before more spend. Manual re-run is the universal recovery. (Automatic retry policy for `sandbox_died` is an easy later addition.)

### Snapshot and onboarding

- Each enabled repo gets a snapshot built from a base image (Debian-based, Docker-in-Docker, agent runtime pinned, toolchain) with the repo pre-cloned. Runs always fetch latest code in the setup script, so **correctness never depends on snapshot freshness — staleness only costs fetch time**. Rebuilds are manual (a dashboard action) plus automatic when the repo's base image setting changes. Snapshot build status (building/ready/failed) lives on the repo; runs won't dispatch while the snapshot isn't ready.
- Onboarding flow: install the GitHub App → connection becomes active → grant list appears → enable a repo (default config prefilled) → snapshot builds → optionally "verify setup" (boots a sandbox, runs the setup script, reports — no agent) → the repo is live; the first labeled issue or manual signal produces the first run. Foresight does not open its own setup PR in V1.

### Dashboard information architecture

Three top-level areas (a sketch, not a pixel spec — the UI is thin wiring):

- **Signals** — the default view: list with derived outcome status, source, repo; stranded signals visibly flagged. Signal detail: payload, origin link, run history. Manual signal creation lives here.
- **Run room** (run detail) — state timeline, live session view (served directly from the sandbox via signed URL), attach actions (web terminal, TUI copy-paste command), stop button, result card, failure detail, transcript link post-run, revive when available.
- **Repos & Settings** — repo list with snapshot status; repo config editor (setup script, env files, prompt, base image, rebuild, verify setup); org settings (credential, concurrency cap, members, API tokens, GitHub connection status).

Live updates reach the browser as run-state changes streamed or polled from the control plane (cheap — state lives on Run rows); the live *session* view goes browser-to-sandbox directly via signed URLs, so no agent events are ever stored in the control plane.

## Testing Decisions

- A good test drives the system at its boundary and asserts on externally observable behavior — domain rows, API responses, calls recorded by fakes — never on internals. The UI is not tested; it is thin wiring over the tested API (a UI bug is a wiring bug).
- Exactly two fakes, at the two seams where arrows leave the system, both implementing interfaces the design already owns:
  - a **fake executor** — in-memory, scriptable per test ("emit these events then idle", "fail the setup script", "die mid-stream") — so the entire run lifecycle is testable without a provider;
  - a **fake GitHub client** beneath the surface adapter — so write-back is asserted ("comment posted, labels applied, surface state updated") without network. Inbound needs no fake: tests POST recorded webhook payloads at the real webhook endpoint.
- Everything else runs real in tests: actual Postgres, real django-ninja endpoints through the test client, Procrastinate jobs executed in-process.
- The canonical test shape, end to end through one seam: *POST a labeled-issue webhook → assert the signal exists and dispatched → run jobs inline with the fake executor scripted to succeed → assert the run walked queued → provisioning → running → awaiting_review, result columns filled, transcript exported, and the fake GitHub client saw the start comment, finish comment, and labels.* Failure-taxonomy tests are the same shape with differently scripted fakes.
- Durability tests exploit idempotency directly: run the orchestrator partway, simulate death, re-invoke, assert exactly-once effects (one sandbox, one session, correct final state). The reconciliation sweep is tested against the fake executor's sandbox inventory.
- The Daytona binding gets thin contract tests; the seven verify-during-build items from the interface contract are validated against real Daytona during implementation, not simulated.
- Prior art: none — greenfield repo; these tests establish the house style.

## Out of Scope

- Linear connector, error-log/Sentry signals, feedback-form signals (V2 connectors; the origin-connection FK and adapter-shaped origin blobs are already in place for them).
- Pre-sandbox triage (V1 reserves the intake-state insertion point and dispatch seam; nothing else).
- Hierarchical runs — agent-spawned child runs (V2; modeled: children are runs with a parent FK, one-active-root-run, cap counts children).
- MCP server and run-scoped in-sandbox API tokens (V2; API-first and org tokens make both thin additions).
- Dashboard-native live-steering UI (watching and terminal takeover ship; a chat-style steering UI does not).
- Multi-agent runtimes (Claude Code, Codex) — future runner-interface implementations.
- Billing, platform-provided API keys, hosted multi-tenant SaaS operations (schema is org-ready; operations are not).
- Own sandbox fleet / self-hosted k8s executor (future Executor implementation).
- Signal dedup/grouping; automatic retry policies; PR-closed-unmerged and origin-issue-closed handling (additive columns and derivation tweaks recorded on the domain-model ticket).
- Temporal or any workflow engine (deferred with revisit trigger: multi-step compensation logic in the control plane).

## Further Notes

- The [glossary](../../CONTEXT.md) is canonical for terminology; specs, code, and API names should use it. The map's Decisions section preserves the reasoning trail; the four research assets carry implementation-grade detail (provider APIs, prompt text, event mappings) that this spec deliberately doesn't duplicate.
- The interface contract carries a seven-item **verify-during-build** list (SSE through the proxy, signed-URL auth in browsers, TUI attach, env-only provider auth, idle-event semantics, PTY ergonomics, resource caps). These are binding-level checks for the Daytona implementation — none affect the interface shape, but they should be burned down early in the build.
- The default harness prompt ships as a versioned public artifact; repos store their own copy, so improving the default never mutates existing repos' behavior.
- Next step after this spec: slice into numbered implementation issues sized for mostly-AFK build sessions (the second half of the spec-assembly ticket).
