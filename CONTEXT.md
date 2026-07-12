# Foresight

Autonomous software factory: signals from customer surfaces (GitHub issues, manual entries) launch coding agents in cloud sandboxes that fix, test, open PRs, and report back. This is the single context for the control plane and its domain.

## Language

### Tenancy and connections

**Org**:
The tenant. Owns users (through memberships), surface connections, repos, the encrypted agent credential (BYO API key), and the concurrency cap.
_Avoid_: Team, workspace, account

**Surface connection**:
An org's authenticated link to an external surface (GitHub App installation in V1; Linear etc. later). One table for all surfaces: core-queried columns (org, type, status `pending / active / revoked`, account label) plus adapter-owned `identity` (plain JSONB) and `credentials` (encrypted JSONB) blobs.
_Avoid_: Integration, installation (GitHub-specific detail)

**Repo**:
A connected GitHub repository, org-scoped, referencing its surface connection. Carries its run config inline: base snapshot, setup script, encrypted env files, harness prompt. Has a connection status (`connected / disconnected`); the row is never deleted on disconnect.
_Avoid_: Project, repository config (no separate config entity exists)

**API token**:
An org-scoped credential for non-browser API clients — agents (Claude Code on a user's machine), scripts, CI. Hashed at rest; created and revoked in org settings. The API is the product and the web UI is one client of it: every capability is reachable with a token. V2 adds run-scoped tokens minted into sandboxes so agents can spawn child runs.
_Avoid_: Personal access token (they're org-scoped, not user-scoped)

### Signals and runs

**Signal**:
The durable record of a request for work — its source, origin reference, payload, and repo. Its origin surface (where it came from) is distinct from its repo's surface (where work lands); in V1 both are GitHub. A signal carries no lifecycle state machine of its own beyond intake; its status is derived from its runs.
_Avoid_: Ticket, task, request, job

**Intake state**:
The stored state machine covering a signal's life *before* runs exist; it ends permanently at `dispatched`, where Runs take over. V1 is `received → dispatched`; V2 triage inserts states (`triaging`, `awaiting_reply`) between them. Queue mechanics (job rows) are machinery, not intake states.
_Avoid_: Signal lifecycle, pipeline state

**Run**:
One execution attempt against a signal: a sandbox, an agent session, a lifecycle state (`queued → provisioning → running → awaiting_review → done / failed`), and artifacts (branch, PR, structured result, session export). A signal may have many runs; at most one run per signal is active at a time (partial unique index).
_Avoid_: Job, execution, attempt

**Outcome status** (derived):
The user-facing answer to "how is this signal going?" — never stored. Before dispatch it mirrors the intake state; after dispatch it derives from runs: if any run's PR was merged the signal is done, otherwise it reflects the latest run. Deliberately simple in V1.
_Avoid_: Signal status (ambiguous)

**Stranded** (derived):
A signal whose repo is currently disconnected: intact but unactionable — dispatch refuses to launch, write-back is impossible. Never stored; reconnecting the repo un-strands its signals automatically.
_Avoid_: Detached, orphaned

### Surfaces

**Surface adapter**:
The code interface through which Foresight talks back to a signal's origin surface (`notify_run_started` / `notify_run_finished`). GitHub adapter in V1: issue comments + status labels.
_Avoid_: Integration, connector (reserved for signal *sources*)

**Surface state**:
An opaque JSONB blob on Signal, owned exclusively by its surface adapter — its private memory of what it did at the origin (comment IDs, applied labels). The core never reads or interprets it; only adapter hooks touch it.

### Execution

**Agent runtime**:
The coding-agent product a run executes with (OpenCode in V1; Claude Code, Codex as future runner-interface implementations). Recorded per run, since repo config can change between runs.
_Avoid_: Agent (ambiguous), harness (that's the prompt)

**Executor**:
The code interface the control plane owns for sandbox + agent lifecycle (create sandbox, launch agent, attach endpoints, event stream, retire). Daytona binding in V1; future own-fleet/k8s implementations conform to it. Not a table.
_Avoid_: Provider (that's the vendor behind an executor), runner

**Session export**:
The copy of the agent session data (OpenCode's SQLite store or `opencode export` JSON) pulled into Foresight-owned storage when a run ends. The durable system of record for what the agent did; never lives only in a provider's storage.

**Revival**:
Restoring an archived sandbox to continue the agent session inside its full environment. A best-effort, optional executor capability with a retention window (archive → auto-delete); nothing correctness-critical depends on it.
_Avoid_: Resume (overloaded)
