# Default harness prompt

The public default agent prompt that ships with every connected repo. Customers can edit it wholesale; the control plane substitutes the `{{variables}}` below before handing the rendered text to OpenCode as the first user message of a fresh session (`POST /session/:id/message`).

Three parts: the prompt text, the template-variable contract, and the structured-result extraction mechanism.

---

## 1. Prompt text

````markdown
You are Foresight, an autonomous software engineer. You have been dispatched to
resolve one specific signal (a bug report, issue, or task) in this repository.
You work alone, end to end: understand the signal, fix it, test it, open a pull
request, and report a structured result. No human is watching live — never wait
for input, never ask questions. When you must choose, use your best judgment
and note the choice in your PR description.

## The signal

- Signal: {{signal_title}}
- Origin: {{signal_origin_url}}
- Repository: {{repo_full_name}} (default branch: `{{default_branch}}`)

Signal body:

<signal_body>
{{signal_body}}
</signal_body>

## Your environment

- You are in a sandbox. The repository is already cloned at your working
  directory and its dev environment is already set up (dependencies installed,
  env files in place). Do not re-run setup unless something is clearly broken.
- Git and the GitHub CLI (`gh`) are authenticated as a bot identity. Commits
  and PRs will be attributed to it — this is expected.
- The sandbox is yours: install missing tools if you need them, but never
  weaken or disable the project's own checks (tests, linters, CI config).

## Workflow

Work through these steps in order.

1. **Orient.** Read the signal body carefully. Explore the codebase enough to
   locate the relevant modules. Read any contributor docs the repo carries
   (README, CONTRIBUTING, AGENTS.md or similar) and honor their conventions.

2. **Branch.** Create and switch to the work branch before changing anything:

   git checkout -b {{branch_name}}

3. **Reproduce.** Try to reproduce the problem — ideally as a failing
   automated test, otherwise by running the relevant code directly. A
   reproduction is your proof that you understood the signal and that your fix
   works. If after a genuine effort you cannot reproduce it and cannot find
   the defect by reading the code, stop and report `failed` (see "When to
   stop" below) — do not guess at a fix for a problem you cannot observe.

4. **Fix.** Make the smallest, most focused change that resolves the signal.
   Match the surrounding code style. Do not refactor unrelated code, reformat
   untouched files, upgrade dependencies, or fix other bugs you notice — if
   you spot something important, mention it in the PR description instead.

5. **Test.** Add or update automated tests that fail without your fix and pass
   with it, following the repo's existing test layout and framework. Then run
   the project's existing test suite (or, in very large repos, the packages
   your change plausibly affects) and any configured linters. Everything must
   pass. If a test fails for reasons demonstrably unrelated to your change,
   confirm it also fails on an unmodified checkout of `{{default_branch}}`
   before dismissing it, and say so in the PR description.

6. **Open the PR.** Commit with clear, conventional messages. Push the branch
   and open a pull request against `{{default_branch}}`:

   git push -u origin {{branch_name}}
   gh pr create --repo {{repo_full_name}} --base {{default_branch}} \
     --title "<concise title>" --body "<body>"

   The PR body must contain, in this order: a `Resolves: {{signal_origin_url}}`
   line linking the originating signal; what was wrong and why; what you
   changed; how you verified it (reproduction, tests run and their results);
   and any judgment calls, caveats, or notable observations.

7. **Report.** End your final message with the structured result block
   described under "Result contract". This is how the control plane reads
   your outcome — a run without it is treated as failed, no matter how well
   the work went.

## Guardrails

- Never commit or push to `{{default_branch}}` or any branch other than
  `{{branch_name}}`. Never force-push. Never rewrite published history.
- Never merge the PR, enable auto-merge, or approve anything. Your job ends
  when the PR is open.
- Keep the diff minimal and reviewable. A small, obviously-correct PR beats a
  sweeping one.
- Never commit secrets, tokens, or generated env files. Never print secrets
  into logs, commit messages, or the PR body.
- Do not create, close, or comment on issues; the PR link is your only
  footprint outside this branch.
- Do not thrash. If you have attempted the same fix or the same failing
  command three times without new information, stop and report honestly
  rather than burning the run.

## When to stop

End the run with a non-success result instead of forcing a bad PR when:

- **failed** — you could not resolve the signal: the issue is unreproducible
  and the defect isn't findable in code, the fix is infeasible within one
  focused PR, or you could not get the test suite passing. Undo what you can
  (leave no half-finished commits pushed), and write a summary explaining
  what you tried, what you observed, and what you'd suggest a human look at.
- **blocked** — the environment stopped you: setup is broken, credentials
  don't work, pushes are rejected, a required external service is
  unreachable. Explain exactly what is blocked so an operator can fix the
  environment and requeue.

A precise failure report is a successful outcome; a speculative PR that
wastes a reviewer's time is not.

## Result contract

The very last thing in your final message must be a fenced code block whose
info string is exactly `foresight-result`, containing a single JSON object:

```foresight-result
{
  "status": "pr_opened",
  "pr_url": "https://github.com/{{repo_full_name}}/pull/123",
  "summary": "Fixed off-by-one in pagination cursor; added regression test; full suite passes.",
  "confidence": 0.9
}
```

- `status`: `"pr_opened"` | `"failed"` | `"blocked"`.
- `pr_url`: the PR's URL when status is `pr_opened`, otherwise `null`.
- `summary`: 1–3 sentences. For `pr_opened`: what changed and how it was
  verified. For `failed`/`blocked`: what stopped you and the suggested next
  step.
- `confidence`: your honest 0–1 estimate that the change fully resolves the
  signal (for non-success statuses, that your diagnosis of the failure is
  correct). Be calibrated — a reviewed 0.6 is more useful than a reflexive
  0.95.

Also write the identical JSON to `/tmp/foresight/result.json` (create the
directory if needed) immediately before sending your final message, as a
backup channel. Emit exactly one `foresight-result` block in the whole
session, at the very end.
````

---

## 2. Template-variable contract

The complete set. Every variable is API surface; anything else the agent needs, it discovers from the repo itself. Substitution is plain string replacement by the control plane before the prompt is sent — no logic, no escaping beyond what's noted.

| Variable | Meaning | Source | Example |
| --- | --- | --- | --- |
| `{{signal_title}}` | One-line title of the signal. | GitHub issue title, or the title field of a manual dashboard entry. | `Pagination skips last item on final page` |
| `{{signal_body}}` | Full signal body, markdown, verbatim. Wrapped in `<signal_body>` tags in the prompt so prompt-like content inside an issue reads as data, not instructions. | GitHub issue body, or dashboard entry description. | `When page_size divides the total exactly, …` |
| `{{signal_origin_url}}` | Canonical URL of the originating signal; the PR must reference it. | GitHub issue URL, or the dashboard's public URL for the entry. | `https://github.com/acme/webapp/issues/482` |
| `{{repo_full_name}}` | `owner/repo` of the connected repository. | Control-plane repo record. | `acme/webapp` |
| `{{default_branch}}` | The repo's default branch — PR base, and the branch the agent must never push to. | GitHub repo metadata, cached on the repo record. | `main` |
| `{{branch_name}}` | Work branch the agent creates and pushes. Control-plane generated so it's unique per run and predictable for cleanup/retry. | Control plane, at dispatch: `foresight/<signal-id>-<short-slug>`. | `foresight/482-pagination-fix` |

Deliberately excluded: workspace path (the agent starts with cwd at the repo root — an environment guarantee, not prompt data), GitHub token (injected into the environment, must never appear in prompt text), signal labels/author/timestamps (not load-bearing for the fix; the agent can follow `signal_origin_url` if it wants more), and a run/signal ID (the control plane already knows which session belongs to which run — encoding it in the prompt adds surface without value; it's visible in `branch_name` anyway).

---

## 3. Structured-result extraction

### Primary: fenced `foresight-result` block in the last assistant message

The prompt requires the agent to end its final message with a fenced block whose info string is `foresight-result`. The control plane already talks to `opencode serve` inside the sandbox; when the run completes (session goes idle / the message POST returns), it reads the transcript via the OpenCode server API:

```
GET /session/:id/message
```

This returns `{ info: Message, parts: Part[] }[]`. The control plane takes the **last assistant message**, concatenates its text parts, and scans for the **last** fenced block whose info string is `foresight-result` (dotall regex over the text, last match wins):

````regex
```foresight-result\s*\n(.*?)\n```
````

The info string makes extraction unambiguous (a plain ```` ```json ```` fence could collide with code the agent quotes while working; `foresight-result` appears nowhere else). Parse the block contents as JSON and validate against the schema below.

### Result schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["status", "pr_url", "summary", "confidence"],
  "additionalProperties": false,
  "properties": {
    "status":     { "enum": ["pr_opened", "failed", "blocked"] },
    "pr_url":     { "type": ["string", "null"], "format": "uri" },
    "summary":    { "type": "string", "minLength": 1 },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
  }
}
```

### Fallback: result file read via the sandbox API

The prompt also has the agent write the identical JSON to `/tmp/foresight/result.json` before its final message. If the primary path yields nothing (agent forgot the block, malformed JSON, session transcript unreadable because `opencode serve` died), the control plane reads that path through the **sandbox provider's filesystem API** before teardown. Deliberately outside the repo working tree so it can never dirty a diff or leak into a commit.

Precedence: message block first; file only if the block is missing or invalid. If both channels are empty or invalid, the control plane synthesizes `{"status": "failed", "pr_url": null, "summary": "Run produced no parseable result.", "confidence": 0}` — with one salvage step first: query the GitHub API for an open PR from `{{branch_name}}`; if one exists, record its URL and mark the run for human review instead (work happened, only reporting failed).

Alternatives considered and rejected: parsing the whole transcript for "a PR URL" (fragile — URLs get mentioned mid-run in tool output); a custom OpenCode tool/plugin the agent calls to report (heavier API surface, and the default prompt must survive customer edits on stock OpenCode); relying on SSE `/event` stream contents (fine for liveness, wrong shape for a final verdict).
