# Core domain model

Type: grilling
Status: resolved

## Question

Pin the ubiquitous language and the core schema via `/grilling` + `/domain-modeling`: Org, User, Repo (connected repo + its config), Signal (source, origin reference, payload, status), Run (sandbox, agent session, states, artifacts like PR URL), Surface adapter, credentials. One-way door: names and relations here become migrations and API contracts.

Key tensions to resolve: Signal vs Run separation (re-runs, one-active-run rule), where the dispatch stage state lives (V2 triage insertion point), what of the agent session we persist vs leave in the sandbox, and how origin write-back state (comment IDs, labels) is tracked.

Deliverable: glossary + entity/relation sketch recorded via `/domain-modeling` conventions (CONTEXT.md), feeding the spec.

## Answer

Grilled live with the user. The ubiquitous language is recorded in [`CONTEXT.md`](../../../CONTEXT.md) (canonical); the entity/relation sketch below feeds the spec.

### Resolutions to the ticket's named tensions

- **Signal vs Run** — strictly separate entities. Signal is the durable record of intent; Run is one execution attempt; re-run = new Run row. "One active run per signal" is a partial unique index on Runs (signal_id where state non-terminal), not application bookkeeping.
- **Signal state** — two distinct things, deliberately named apart. A stored **intake state** covers the pre-run segment only and ends permanently at `dispatched` (V1: `received → dispatched`; V2 triage inserts `triaging` / `awaiting_reply` between them — states, not restructuring). The user-facing **outcome status** is derived, never stored: intake state until dispatched, then from runs — any merged PR ⇒ done, else latest run's state. The two cover disjoint segments, so no drift. Dispatch itself is a code seam (no Dispatch entity); the org concurrency cap is expressed as Runs waiting in `queued`.
- **Agent-session persistence** — structured result (status, PR URL, summary, confidence) as columns on Run; a mandatory **session export** (OpenCode's SQLite store / `opencode export` JSON, secrets scrubbed) into Foresight-owned storage at run end; no event-level rows ever (live status = relayed SSE). Then archive-with-retention (~14 days, auto-delete) instead of destroy, enabling best-effort **revival** — an optional executor capability (nearly free on Daytona; a k8s executor may no-op it). Recorded as an amendment on the interface-contract ticket (02).
- **Origin write-back state** — an opaque, adapter-owned `surface_state` JSONB on Signal (comment IDs, applied labels). One reader, one writer (the adapter's notify hooks); the core never interprets it. Consequence noted: the merged-PR rule requires the GitHub App to receive PR merge events, and Run carries `pr_merged_at`.

### Entity/relation sketch

- **Org** — name, encrypted agent credential (BYO API key + optional base URL), concurrency cap. Many Users via **OrgMembership** (role `admin`/`member`; identity via allauth).
- **SurfaceConnection** — org FK, type (`github`, later `linear`…), status (`pending / active / revoked`), account label, adapter-owned `identity` JSONB + encrypted `credentials` JSONB. One shared table for all surfaces; the GitHub App's own credentials (app id, private key, webhook secret) are per-deployment config, not rows. Happy path in V1 (installer is a GitHub admin); `pending` exists for the install-request flow.
- **Repo** — org FK, SurfaceConnection FK, full name, default branch, connection status (`connected / disconnected`, flipped by `installation`/`installation_repositories` webhooks; row never deleted), and run config inline: base snapshot ref, setup script, encrypted env files, harness prompt.
- **Signal** — org+repo FK, source (`github_issue` / `manual`), a nullable `origin_connection` FK to SurfaceConnection (the surface the signal *came from* — distinct from the repo's connection once non-GitHub connectors exist; null for manual signals, which reference the creating user instead), origin reference as an adapter-shaped blob (never GitHub-shaped columns), payload (title, body), intake state, adapter-owned surface_state JSONB. **Stranded** (repo disconnected) is derived, never stored — reconnection un-strands automatically.
- **Run** — signal FK, state (`queued → running → awaiting_review → done / failed`), `agent_runtime` (`opencode` in V1; the runtime is recorded per run because repo config can change between runs), executor + sandbox id, `agent_session_id` (runtime-agnostic name), branch name, structured result columns, `pr_merged_at`, failure reason, session-export pointer, sandbox retention state, timestamps.
- **Executor** and **surface adapter** are code interfaces, no tables. No Sandbox or Session entities — their ids and retention state ride on Run.

### V1 scope notes

- Disconnection is *represented* fully (status columns + webhook flips ship in V1); recovery UX (re-auth prompts, pending screens, bulk reconnect) is deferred. In-flight runs on a disconnect just fail their next GitHub call.
- Outcome-status derivation is deliberately simple; richer cross-run logic is a later refinement.

### Future-proofing notes (reviewed against the V2 list; additive changes, deliberately not built in V1)

- **Triage as a Run kind** — if V2's pre-sandbox triage becomes "a cheap run," Run grows a `kind` (`fix` / `triage`) and the one-active-run partial unique index becomes per-kind. Index recreation is cheap; no V1 column.
- **SurfaceConnection uniqueness under multi-tenancy** — hosted SaaS must prevent two Foresight orgs claiming the same GitHub installation: V1 ships a unique index on (type, external identity in `identity`); the claim-conflict flow is deferred.
- **PR lifecycle beyond merge, and origin closure** — PR closed-unmerged and origin-issue-closed-mid-run both arrive as webhooks the GitHub App already receives; handling is additive columns (`pr_state`, `origin_closed_at`) plus derivation tweaks. Owned by spec assembly's failure-taxonomy pass.
- Checked and needing nothing: billing/platform keys (credentials already per-org), live-steering (OpenCode HTTP control channel, no schema), signal dedup/grouping (future grouping entity, nothing blocks it), config reproducibility (session export captures the actual prompt), k8s executor (executor type + optional archive capability suffice).

## Comments

Spec-assembly session (2026-07-12) — three amendments from the orchestration/agents grilling:

- **Hierarchical runs (V2, decided now)** — when the agent-as-orchestrator lands, children are **Runs** on the same signal (not a new entity) with a nullable `parent_run` self-FK; the one-active-run partial unique index becomes one-active-*root*-run (where `parent_run IS NULL`); the org concurrency cap counts children. No V1 column — a nullable FK plus index recreation is trivially additive. The control plane stays a flat one-job-per-run launcher; the parent agent coordinates the tree via the API.
- **ApiToken entity added to the V1 schema** — org FK, name, hashed secret, created-by, timestamps. Design-for-agents decision: API-first, tokens ship in V1. Run-scoped tokens (minted into sandboxes) are the V2 extension.
- **Run states normalized** — `provisioning` (sandbox create + setup script) promoted into the stored state set: `queued → provisioning → running → awaiting_review → done / failed`. It's user-visible and setup failures need a home. Glossary updated.
