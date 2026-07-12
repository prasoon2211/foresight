---
name: wayfinder-quick
description: Wayfinder under time pressure — same map, but only core or hard-to-reverse decisions reach the human; the agent takes defaults on everything standard and logs them for review.
disable-model-invocation: true
---

Wayfinding with a shipping deadline. Read the /wayfinder skill first and follow it in full; this file overrides only what changes when the destination is a V1 that has to ship soon. The shape of the work is a production web app — SaaS, server + client, maybe a CLI — and the scarce resource is the human's attention. Spend it only where it buys something.

## One-way doors and two-way doors

Sort every decision the effort surfaces by its door:

- **One-way door** — hard to reverse once V1 has users: anything whose change later means a data migration, a broken external contract, or a rename across the domain model. The data model, the tenancy shape, ID and naming schemes, API contracts, the glossary. Worked exactly as classic wayfinder: HITL tickets, grilled one question at a time.
- **Two-way door** — cheap to revisit in V2 on solid foundations: dashboard layout, which widgets ship, copy, styling, non-core flows. Walk through it: the agent decides by best judgment and logs it (see Defaults taken) — no ticket, no question.

**Core features get one-way treatment regardless of reversibility.** The product's reason to exist — its core features, the primitives beneath them, their data model — is what the human came to discuss. That's where the session's depth goes.

## Stock parts

Standard B2B SaaS primitives — orgs and multi-tenancy, users and roles, auth and login flows, billing, settings, transactional email — are **stock parts**: the industry has converged on their shape, and this V1 is not innovating on them. Fit the standard shape by best judgment and log the fit as a default. A stock part earns a ticket only where it crosses a one-way door: the org/user *schema* is the data model, so it's discussed; the login *flow* around it is stock, so it's defaulted.

## Defaults taken

The map body gains one section, after **Decisions so far**:

```markdown
## Defaults taken

<!-- one line per best-judgment call made instead of asking — skim and veto -->

- <the decision> — <the default chosen, and why in a clause>
```

Every default lands here the moment it's taken, whether during charting or while resolving a ticket. The human reviews by skimming: silence is consent; a veto promotes the line into a fresh ticket and deletes it from the list.

## What changes in the flow

- **Charting**: while mapping the frontier, triage each surfaced decision by door. Only one-way doors and core features become HITL tickets; two-way doors and stock parts are defaulted on the spot and logged in Defaults taken.
- **Grilling**: every question carries a recommendation, and the bar for asking is higher — a question the human would answer "whatever's standard" was a default in disguise. When unsure which way a door swings, ask *that* (one cheap question) rather than grilling the whole branch.
- **Prototyping**: no UI prototypes. The frontend is a two-way door — it gets reshaped freely during the build — so a mockup decides nothing a sentence can't. Settle the *shape* in conversation (which widgets, what the screen is for) and move on. A prototype ticket is reserved for one-way doors where code pins down what prose can't — a state model, a schema, a tricky reducer.
