# V1 spec assembly and issue slicing

Type: grilling
Status: claimed
Blocked by: 01, 02, 03, 04, 05

## Question

Assemble everything the map has decided into `spec.md` (the destination): product scope, architecture (control plane, sandbox interface, surface adapters, agent runner), data model, GitHub App integration, dashboard IA sketch, repo settings, run lifecycle, takeover story. Then slice into numbered implementation issues sized for mostly-AFK build sessions. Resolve remaining fog inline (onboarding flow, failure taxonomy, live-status display) — they're two-way doors by then; default and log them.

## Comments

2026-07-12 — First half done: [`spec.md`](../spec.md) published (`ready-for-agent`). All remaining fog defaulted inline and logged in the map. Three late decisions from a live grilling folded in before writing: Procrastinate-with-checkpoint-discipline over Temporal (deferred with revisit trigger), API-first / org API tokens in V1 (design for agents), hierarchical runs modeled for V2 (children are Runs, parent FK — recorded on ticket 04). Remaining: slice the spec into numbered implementation issues; this ticket resolves when the slicing is done.
