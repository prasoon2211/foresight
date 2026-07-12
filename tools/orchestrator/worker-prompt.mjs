import { ticketPath, TICKETS } from "./tickets.mjs";

export function buildWorkerPrompt(nn) {
  const path = ticketPath(nn);
  if (!TICKETS[nn]) throw new Error(`unknown ticket ${nn}`);
  return `You are a worker agent building one implementation ticket for Foresight V1 in this repo (prasoon2211/foresight).

Your ticket: \`${path}\` (ticket ${nn}).

## Read first, in this order

1. \`AGENTS.md\` — repo-wide development rules. Binding.
2. \`CONTEXT.md\` — canonical domain glossary; use its terms in code and API names.
3. Your ticket file at \`${path}\` — the acceptance criteria are the contract.
4. \`.scratch/foresight-v1/spec.md\` — read the sections your ticket references, plus Testing Decisions. Read any assets under \`.scratch/foresight-v1/assets/\` that the ticket or those sections link.
5. \`docs/agents/issue-tracker.md\` — tracker conventions you must follow when closing out the ticket.

## Methodology

Read and follow the \`implement\` skill at \`.agents/skills/implement/SKILL.md\`, including the skills it references (\`.agents/skills/tdd/SKILL.md\` for test-first work at pre-agreed seams, and \`.agents/skills/code-review/SKILL.md\` to review your work before finishing). Do not invent methodology beyond what the skills and AGENTS.md mandate.

## The contract

- Implement the ticket COMPLETELY: code, tests, every acceptance criterion satisfied, with the full test suite green. Do not stop at a partial implementation.
- Work on your own branch. Open a PR titled \`${nn}: <short description>\` whose description maps your changes to each acceptance criterion.
- Do not modify other tickets, the spec, the assets, or \`CONTEXT.md\` (except where your ticket explicitly says to). Never commit secrets (no API keys, no .env contents).
- Follow AGENTS.md testing rules: behavior tested at module boundaries via the test suite; no UI test suites.

## Closing out (only after the full test suite is green)

1. In your ticket file \`${path}\`, ON YOUR BRANCH: check off every acceptance-criteria box, set \`Status: resolved\`, and append a dated comment under a \`## Comments\` heading with a one-line summary and the PR link.
2. Merge your PR into main yourself via git:
   - \`git fetch origin main\` and merge \`origin/main\` into your branch first if main moved; re-run the full test suite if you had to merge anything non-trivial.
   - \`git checkout main && git merge --no-ff <your-branch> -m "Merge ticket ${nn} PR" && git push origin main\`
   - GitHub will mark the PR merged automatically.
3. Only merge when the suite is green. If you cannot get it green, or an acceptance criterion is impossible as written, DO NOT merge — leave the PR open and report exactly what is blocking in your final message.

## Report back

End with a short report: what you built, test-suite result (command + outcome), PR URL, merge status, and any deviations from the ticket.`;
}
