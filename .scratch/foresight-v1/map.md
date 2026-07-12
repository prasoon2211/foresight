# Foresight V1 — Wayfinder Map

Label: wayfinder:map

## Destination

A build-ready V1 spec for Foresight (`spec.md` in this directory) plus a sliced implementation issue list — data model, architecture, sandbox and agent-runtime choices locked, so the build itself can run as a separate, mostly-AFK effort.

## Notes

- Product: autonomous software factory — signals (GitHub issues, manual entries) trigger coding agents in cloud sandboxes that fix, test, open PRs, and report back.
- Worked with `/wayfinder-quick`: one-way doors and core features get HITL tickets; two-way doors and stock parts get best-judgment defaults logged in Defaults taken.
- Skills to consult per ticket: `/grilling`, `/domain-modeling`, `/prototype`, `/research`.
- Stack constraints (company policy): Django backend, TypeScript SPA frontend.

## Decisions so far

Settled during charting (no ticket; grilled live with the user):

- **Destination shape** — build-ready spec + sliced issues; building happens after this map.
- **Control plane / sandbox split** — control plane is a normal Django app (compose-deployable now, cloud-hostable later, no exotic dependencies); sandboxes are never colocated, always created via a remote provider API behind a thin interface we own. Self-hosted k8s fleets later = another interface implementation.
- **Tenancy** — org model in the schema from day one; operationally single-tenant in V1. Auth ships in V1; billing deferred.
- **Signal sources V1** — GitHub Issues (picked up via `foresight` label) + manual signal creation in the dashboard. Linear cut from V1 (GitHub already required for PRs).
- **Agent runtime** — OpenCode only, behind an agent-runner interface. Chosen for its client/server architecture: `opencode serve` + `opencode attach --session` gives live takeover for free and kills the event-projection/storage subsystem. Claude Code can't attach to a live headless run; subscription OAuth in third-party harnesses is a ToS violation anyway (confirmed Feb–Apr 2026 policy), so BYO API key was always the model.
- **Credentials** — per-org encrypted API key + optional base URL in settings; strictly BYO-key in V1; modeled per-org so platform-provided keys/billing can come later.
- **Repo configuration** — all in-app, per repo: base image (default fat image), setup script (freeform bash), env files (repo-relative path → contents, encrypted), and the full agent harness prompt (editable wholesale, prefilled with Foresight's public default). No in-repo `.foresight/` YAML in V1.
- **Run lifecycle** — fully automatic start on label (the label is the approval), one active run per signal with manual re-run, org-level concurrency cap as the only brake, minimal states (`new → running → awaiting review → done / failed`). An explicit dispatch stage sits between "signal ingested" and "run launched" so the V2 pre-sandbox triage step (cheap sandbox analyzes signal, pushes clarifying questions back to origin) can be inserted without surgery — no-op in V1.
- **Write-back** — surface adapter interface (`notify_run_started` / `notify_run_finished`); GitHub adapter = issue comments with a session link, plus status labels (`foresight:in-progress`, `foresight:pr-open`).
- **Takeover** — attach to the live OpenCode session (web terminal into sandbox and/or `opencode web`); watching live is a core feature. No dashboard-native live-steering UI in V1.
- [Sandbox provider selection](issues/01-sandbox-provider-research.md) — Daytona (runner-up E2B): only provider with first-class documented Docker-in-Docker + docker-compose; PTY over WebSocket + signed preview URLs map directly onto our attach design; full Python SDK; ~$0.33/h per 4 vCPU DinD sandbox, no base fee. Watch-outs: default 4 vCPU/8 GiB/10 GiB cap needs raising for heavy stacks, must set `auto_stop_interval=0`, Tier 4 conversation needed at 80+ concurrent. Full comparison: [asset](assets/sandbox-provider-comparison.md).
- [Core domain model](issues/04-domain-model.md) — glossary canonical in `CONTEXT.md`; entities: Org, OrgMembership, SurfaceConnection (one table, all surfaces, adapter-owned identity/credentials blobs), Repo (config inline, `connected/disconnected`), Signal (stored intake state ending at `dispatched`; derived outcome status and derived "stranded"), Run (one-active-per-signal via partial unique index; structured result columns + mandatory session export, then archive-with-retention/revival). Dispatch is a code seam; write-back memory is adapter-owned `surface_state` JSONB on Signal. Reviewed against the V2 list: Signal carries a nullable origin-connection FK (origin surface ≠ repo surface once Linear lands), Run records its agent runtime; triage-as-run-kind, installation-claim uniqueness, and PR/origin closure handling recorded as additive future notes. Sketch + notes on the ticket.
- [Sandbox + agent-session interface contract](issues/02-sandbox-agent-interface-prototype.md) — five-verb Executor interface (`create_sandbox / launch_agent / get_attach_endpoints / stream_events / destroy`); only lifecycle/networking/PTY are provider-specific, session control is shared OpenCode-HTTP code; API key injected as process env only, server locked with per-run password; attach triangle via signed preview URLs + PTY WebSocket; event→status mapping and a persist-before-destroy list. Resolved on paper (prototype skipped by user decision); carries a 7-item verify-during-build list. Amended by the domain-model session: mandatory session export to our storage at run end, then archive-with-retention instead of destroy (revival as optional executor capability) — see ticket comments. Contract: [asset](assets/sandbox-agent-interface.md).
- [Default harness prompt](issues/05-default-harness-prompt.md) — six-variable template contract (`signal_title/body/origin_url`, `repo_full_name`, `default_branch`, `branch_name`); result extracted from a `foresight-result` fenced JSON block in the final message (`status`/`pr_url`/`summary`/`confidence`), with a `/tmp/foresight/result.json` file fallback and a GitHub PR-existence salvage check. Prompt text: [asset](assets/default-harness-prompt.md).
- [Django stack selection](issues/03-django-stack-research.md) — django-allauth headless (we own the org schema), django-ninja + hey-api typed client, Procrastinate for background/orchestration work (Postgres broker, async-native; Celery has no asyncio tasks), django-fernet-encrypted-fields for secrets at rest (django-cryptography is abandoned). Full comparison: [asset](assets/django-stack-selection.md).

Settled during spec assembly (grilled live with the user; no ticket):

- **Orchestration durability — Procrastinate, not Temporal** — the orchestrator is a resumable checkpoint machine: all state on the Run row the moment it exists, jobs carry only a run id, every step idempotent via row checks, stream reconnect + resync, reconciliation sweep (provider labels → Run rows) closes the created-but-unrecorded gap. Jobs retry (resume the same Run after worker death); runs don't (sandbox/agent failure is a terminal domain outcome; recovery = new Run). Temporal considered and deferred: it solves orchestrator durability, not sandbox reliability; costs a server cluster, a deterministic-workflow idiom, and versioning discipline, and breaks compose-deployability. Revisit trigger: control-plane workflows grow multi-step compensation logic (own-fleet executor era).
- **Design for agents — API-first** — the API is the product, the web UI one client of it; no UI-only capabilities, ever. Org-scoped API tokens (hashed at rest) ship in V1 so agents (e.g. Claude Code on a user's machine) can drive Foresight directly. MCP server = V2 thin wrapper over the OpenAPI surface; run-scoped in-sandbox tokens = V2 (enables agent-spawned runs).
- **Hierarchical runs (V2, modeled now)** — children are Runs on the same signal with a nullable `parent_run` self-FK; the one-active-run index becomes one-active-*root*-run; org concurrency cap counts children. The agent is the orchestrator (spawns/monitors children via the API); the control plane stays a flat one-job-per-run launcher — a further argument against a heavyweight workflow engine. No V1 column; recorded on ticket 04.
- **Remaining fog resolved inline in [spec.md](spec.md)** — snapshot rebuild/staleness policy, repo onboarding flow, dashboard IA, failure taxonomy + retry semantics: all defaulted in the spec's Implementation Decisions.
- [V1 spec assembly and issue slicing](issues/06-spec-assembly.md) — **destination reached**: [spec.md](spec.md) published (`ready-for-agent`) and the build sliced into implementation issues 07–16 — tracer-bullet vertical slices, re-cut 2026-07-12 from the original layer-based 07–18 (dependency graph and re-slice rationale on the ticket). The map's work is done; building proceeds issue by issue.

## Defaults taken

<!-- one line per best-judgment call made instead of asking — skim and veto -->

- GitHub integration mechanism — GitHub App with webhooks (polling fallback), standard shape for label events + bot-identity comments/PRs.
- Database — Postgres.
- Frontend — React + Vite + TypeScript SPA.
- Manual signals start a run immediately on create, same path as labeled issues.
- Signal→repo mapping — a GitHub issue maps to its own repo; manual signals pick a connected repo at creation.
- Run states normalized to `queued → provisioning → running → awaiting_review → done / failed` — `provisioning` promoted from the interface contract's derived status into the domain state set (user-visible, and setup failures need a home).
- Org concurrency cap enforced by check-and-postpone: the orchestrator job's first step counts the org's active runs and reschedules itself if at cap. Dumb, self-healing.
- No automatic retry of failed runs in V1 — manual re-run only (worker-death job requeue is resume, not retry).
- Runs can be stopped from the dashboard (teardown + `failed` with reason `canceled`).

## Not yet specified

(none — remaining fog was resolved inline in [spec.md](spec.md); see Decisions above)

## Out of scope

- Linear connector, error-log/Sentry signals, feedback-form signals — V2 connectors.
- Signal dedup/grouping ("these 10 tickets are the same bug") — V2.
- Pre-sandbox triage step itself (V1 only reserves the pipeline stage for it).
- Dashboard-native live-steering of a running agent (send messages mid-run) — V2 control channel.
- Multi-agent support (Claude Code, Codex) — V2 implementations of the runner interface.
- Billing, platform-provided API keys, hosted multi-tenant SaaS operations.
- Own sandbox fleet / self-hosted k8s executor — future interface implementation.
