# 09 — Sign up, orgs, and API tokens

**What to build:** Foresight becomes multi-tenant and agent-usable. A new user signs up with email and password (verified), creates an org, and invites teammates with admin/member roles. An admin stores the org's LLM credential (encrypted, write-only) and concurrency cap, and mints org API tokens — shown once, hashed at rest, revocable. From this ticket on, *every* endpoint (including slice 08's signals and runs) is org-scoped and accepts either a session cookie or a bearer token interchangeably: the API-first rule made real.

This slice also establishes the agent-legible error convention (structured code + message + what-to-do-next hint) as the API-wide standard, per user stories 32–33.

**Blocked by:** 08 — Tracer bullet.

**Status:** claimed

- [ ] Signup → email verification → login → org creation → member invite with role, all driven through the real endpoints in tests
- [ ] Org agent credential and env-style secrets are write-only: accepted on write, never echoed on read
- [ ] An API token drives the full slice-08 flow (create signal, poll run); a revoked token is rejected
- [ ] Cross-org isolation: a member of org A gets 404s on org B's signals and runs
- [ ] Role enforcement: member-forbidden actions (token management, credential changes) rejected for non-admins
- [ ] OpenAPI schema carries both auth schemes so the generated TypeScript client can use them

Spec sections: Stack (allauth headless), Domain model (Org, OrgMembership, ApiToken), API-first rule; user stories 1–4, 31–33.
