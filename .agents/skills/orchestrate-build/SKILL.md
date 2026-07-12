---
name: orchestrate-build
description: "Orchestrate a fleet of Cursor Cloud worker agents through an existing ticket dependency graph: set up the cloud environment, launch one worker per frontier ticket in parallel, babysit them, have each merge its own PR and mark its ticket resolved, then advance the frontier until every ticket is merged. Use when a repo already has a spec and numbered, blocked-by-wired implementation tickets and the user wants the whole graph built autonomously."
disable-model-invocation: true
---

You are the **orchestrator**. You implement nothing yourself: every line of product code arrives through a worker agent's PR. Your job is dependency management, launching, babysitting, verification, and bookkeeping.

## Preconditions

- Tickets exist on the repo's issue tracker (see `docs/agents/issue-tracker.md` for conventions), each with a `Status:` line, acceptance-criteria checkboxes, and `Blocked by: NN, NN` edges.
- A spec and (usually) `AGENTS.md` + domain glossary exist. Workers will be told to read them; you follow them too.
- `CURSOR_API_KEY` is available. Any provider keys individual tickets need are available as env vars (in cloud: Dashboard → Cloud Agents → Secrets).
- An implementation-methodology skill exists in-repo (e.g. `.agents/skills/implement/SKILL.md`); workers are pointed at it rather than given ad-hoc methodology.

## Phase 0 — cloud environment (before any worker)

Cloud agents clone the repo fresh; without config they get a bare Ubuntu VM and waste their session installing toolchains (or failing to).

1. On a branch, write `.cursor/environment.json` + `.cursor/Dockerfile`; open a PR; merge to `main` immediately (workers inherit the config **at the commit they start from**).
2. Dockerfile rules: never `COPY` the project (Cursor manages the checkout); install system deps only — language runtimes, package managers, Node if there's a frontend, and Docker CE when the dev loop is compose-based. For Docker-in-VM use the known-good block from `cursor.com/docs/cloud-agent/setup`: `fuse-overlayfs` storage driver, `iptables-legacy`, ubuntu user in the `docker` group.
3. `environment.json`: `build.dockerfile`/`build.context` (paths relative to `.cursor/`, `..` = repo root), an **idempotent** `install` command that no-ops until manifests exist (e.g. `if [ -f pyproject.toml ]; then uv sync; fi`), and `start: "sudo service docker start"` if Docker is needed.
4. Add a `## Cursor Cloud specific instructions` section to `AGENTS.md` (what's preinstalled, how to start the daemon, dev-loop commands). **Update it in your bookkeeping commits as the toolchain lands** — the first scaffold ticket changes what's true.

## The toolkit

Write a small Node toolkit under `tools/orchestrator/` (`npm install @cursor/sdk`; it's legitimate project tooling — commit it). Reference implementation lives in this repo. Scripts:

- `tickets.mjs` — the ticket table (`{ NN: { slug, blockedBy: [...] } }`) mirroring the tracker's `Blocked by:` lines, plus `frontier(state)`: tickets whose blockers are all `merged` and which aren't launched/merged themselves.
- `state.mjs` — load/save/patch `state.json`: `ticket → { status, agentId, runId, branch, prUrl, timestamps }`. Commit it to `main` after every transition; agent IDs are resumable across processes, so this file is your crash recovery.
- `launch.mjs <NN> ["orchestrator note"]` — create + send, record state.
- `watch.mjs <NN>` — poll until terminal, print final report + branch + PR.
- `peek.mjs <NN>` — last few conversation steps of a live worker (for babysitting).
- `resume.mjs <NN> "message"` — follow-up to an existing worker.
- `frontier.mjs` — print merged / in-flight / launchable.

### SDK usage — hard-won specifics

- **Always pass the cloud runtime explicitly**: `cloud: { repos: [{ url, startingRef: "main" }], autoCreatePR: true, skipReviewerRequest: true }`. Omitting `cloud` silently gives a local agent.
- **Model params must match a full variant.** `{ id, params: [partial] }` fails with `invalid_model`. Call `Cursor.models.list()`, find the model, and pass **every** parameter (e.g. for `gpt-5.6-sol`: `context`, `reasoning`, and `fast` all together).
- **Wrap every SDK call in try/catch and print only `err.message`/`err.code`.** Uncaught SDK errors dump a ~250KB minified bundle line into the terminal and bury the actual message.
- **Poll `Agent.getRun(runId, { runtime: "cloud", agentId })`**, not `Agent.get(agentId).status` — the latter is often `undefined` for SDK-launched cloud agents. Terminal statuses: `finished` / `error` / `cancelled`.
- **`run.result` is often empty** even on success. Fall back to `run.conversation()` → last `assistantMessage` for the worker's report.
- Distinguish failure kinds: thrown error on create/send = never started (fix env/auth; retry if `isRetryable`); `status === "error"` = ran and failed (inspect, then `resume` with corrections — the worker has context; relaunch only as last resort).
- Secrets go in per-agent `cloud.envVars` (encrypted at rest, deleted with the agent) — only for tickets that need them, never in the repo or the prompt text.
- Poll gently (60–90s). Run watchers in tmux writing to log files so monitoring survives your own session.

## The worker prompt

Workers are fresh agents with zero context. Every prompt must carry:

1. **Reading order**: `AGENTS.md` → glossary/`CONTEXT.md` → the ticket file (acceptance criteria are the contract) → the spec sections + assets the ticket references → tracker conventions doc.
2. **Methodology**: point at the in-repo implementation skill (and the skills it references, e.g. tdd, code-review). Don't invent methodology in the prompt.
3. **The contract**: implement COMPLETELY — code, tests, every criterion, full suite green; own branch; PR titled `NN: <desc>` mapping changes to criteria; don't touch other tickets/spec; never commit secrets.
4. **Closing out** (this is what makes the fleet self-serve): on their branch, check off criteria, set `Status: resolved`, append a dated `## Comments` entry with the PR link; then fetch+merge `origin/main` into the branch, re-run the suite if the merge was non-trivial, and **merge to main themselves via git** (`git checkout main && git merge --no-ff <branch> && git push origin main` — GitHub marks the PR merged; the `gh` token in cloud VMs is read-only, so `gh pr merge` is not available). Merge only on green; otherwise leave the PR open and report what's blocking.
5. **Report format**: what was built, test command + outcome, PR URL, merge status, deviations.
6. Optional **orchestrator note**: parallel-collision warnings, credentials available in env, constraints ("no real GitHub App yet — use recorded payloads").

Because the tracker bookkeeping rides on the worker's branch, ticket resolution lands atomically with the code.

## The loop

Repeat until the last ticket merges:

1. **Claim**: set the ticket's `Status: claimed`; commit to `main` (orchestrator bookkeeping goes straight to `main`; product code never does).
2. **Launch** every frontier ticket. When two frontier tickets will collide (same models file, same migrations dir, same route file), still parallelize but put an explicit note in each prompt: keep scope tight; before merging, fetch+merge `origin/main`, resolve conflicts (**Django-style migration numbering is the classic one — renumber on top of whatever landed first**), re-test, then merge; if main moved again, repeat. This protocol was exercised successfully — a schema-touching pair merged cleanly with the second worker renumbering its migration.
3. **Monitor** via the tmux watcher; `peek` if a run seems long. Long ≠ stuck: playthrough/e2e phases run quietly for 30+ minutes; look at the conversation tail before intervening.
4. **Verify** after the run: `git pull` main; PR merged? CI green on the merge commit (`gh run list`)? ticket file resolved with boxes checked? spot-check the diff against the acceptance criteria (the load-bearing design decisions especially). Scan for leaked secrets. If the worker finished but didn't merge, read its report — it may be blocked for a legitimate reason.
5. **Correct** via `resume` with specific instructions. Two resume rounds without progress → stop and ask the human; don't merge garbage or burn attempts.
6. **Advance**: mark `merged` in `state.json`, commit, recompute frontier, go to 1. Report to the user as tickets complete: ticket, agent, PR, outcome, what's launching next.

## Human intervention points

Pause and ask (only) when: a ticket needs credentials/accounts you don't have; external resources must be created manually (OAuth/GitHub Apps, billing); two correction rounds failed; or a worker reports an acceptance criterion impossible as written. Otherwise act — the user set the destination; you own the route.
