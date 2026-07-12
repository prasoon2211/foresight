# Default harness prompt

Type: prototype
Status: resolved

## Question

Draft the public default agent prompt that ships with every repo (user-editable wholesale). It must drive OpenCode from a cold signal to a finished run: read signal context, branch, reproduce if possible, fix, write and run tests, open a PR linked to the signal, and end with a structured result the control plane can parse (PR URL, summary, confidence). Decide the template-variable set ({{signal}}, {{repo}}, …) and how "structured result" is extracted from an OpenCode session.

Deliverable: the prompt text + variable contract, linked as an asset. Cheap to iterate later — but the variable contract and result-extraction mechanism are load-bearing for the spec.

## Answer

Full prompt, variable contract, and extraction mechanism: [default-harness-prompt.md](../assets/default-harness-prompt.md).

Gist: the prompt drives OpenCode through orient → branch → reproduce → fix → test → PR → report, with explicit guardrails (never touch the default branch, minimal diffs, no secrets, stop after three fruitless retries) and graceful bail-outs (`failed` for unreproducible/infeasible signals, `blocked` for broken environments). Six template variables, all plain string substitution: `{{signal_title}}`, `{{signal_body}}`, `{{signal_origin_url}}`, `{{repo_full_name}}`, `{{default_branch}}`, `{{branch_name}}`. Result extraction: primary — the agent ends its final message with a fenced ` ```foresight-result ` JSON block (`status` / `pr_url` / `summary` / `confidence`), which the control plane reads from the last assistant message via OpenCode's `GET /session/:id/message`; fallback — the same JSON written to `/tmp/foresight/result.json`, read via the sandbox filesystem API before teardown. If both fail, salvage by checking GitHub for an open PR from `{{branch_name}}`, else synthesize a zero-confidence `failed` result.
