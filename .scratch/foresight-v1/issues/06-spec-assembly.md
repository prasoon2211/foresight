# V1 spec assembly and issue slicing

Type: grilling
Status: resolved
Blocked by: 01, 02, 03, 04, 05

## Question

Assemble everything the map has decided into `spec.md` (the destination): product scope, architecture (control plane, sandbox interface, surface adapters, agent runner), data model, GitHub App integration, dashboard IA sketch, repo settings, run lifecycle, takeover story. Then slice into numbered implementation issues sized for mostly-AFK build sessions. Resolve remaining fog inline (onboarding flow, failure taxonomy, live-status display) — they're two-way doors by then; default and log them.

## Comments

2026-07-12 — First half done: [`spec.md`](../spec.md) published (`ready-for-agent`). All remaining fog defaulted inline and logged in the map. Three late decisions from a live grilling folded in before writing: Procrastinate-with-checkpoint-discipline over Temporal (deferred with revisit trigger), API-first / org API tokens in V1 (design for agents), hierarchical runs modeled for V2 (children are Runs, parent FK — recorded on ticket 04). Remaining: slice the spec into numbered implementation issues; this ticket resolves when the slicing is done.

## Answer

Spec published at [`spec.md`](../spec.md) (`ready-for-agent`), and the build sliced into twelve implementation issues, 07–18, each sized for a mostly-AFK session, each `ready-for-agent` with scope, acceptance criteria, and `Blocked by:` dependencies:

07 backend scaffold → 08 core domain models → {09 auth/org API, 11 GitHub surface}; 07 → 10 executor interface + fake → {12 harness prompt & result, 14 Daytona binding + snapshots}; 11 + 12 → 13 run orchestration (the durability centerpiece); 09 + 13 + 14 → 15 product API → {16 frontend signals/runs, 17 frontend onboarding/settings} → 18 deployment packaging.

The dependency spine keeps the two fakes (executor, GitHub client) available from issue 10/11 onward, so the canonical end-to-end test lands with issue 13 while the real Daytona binding (14) proceeds in parallel. This closes the map's destination: build-ready spec + sliced issue list.

**2026-07-12 amendment — re-sliced vertically.** The original 07–18 were layer slices (all models, then the executor layer, then the whole API, then the frontend); the `/to-tickets` skill demands tracer-bullet vertical slices, each demoable on its own. Replaced with ten tickets 07–16: 07 scaffold → 08 tracer bullet (manual signal → finished fake run, over the API — canonical test lands here) → {09 auth/orgs/tokens, 10 failure/durability/control} → 11 GitHub loop (09 also gates it) → 12 prompt & result contract → 13 Daytona + snapshots → 14 dashboard signals/run room → 15 dashboard onboarding/settings → 16 deployment. Same spec, same decisions — only the cut changed: each slice now delivers a behavior end to end, thickening the Run schema and API as it goes instead of front-loading them.
