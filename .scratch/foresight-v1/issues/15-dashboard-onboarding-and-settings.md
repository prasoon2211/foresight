# 15 — Dashboard: onboarding, repos, and org settings

**What to build:** The setup half of the product in a browser: from empty org to a live repo without touching the API by hand. An admin connects GitHub (App install handoff and return), watches the connection go active, sees the grant list, and enables a repo — default config prefilled, snapshot building. They edit the setup script, upload env files (write-only), edit the harness prompt (with reset-to-default), pick a base image, trigger a rebuild, and run "verify setup" to see the environment boot for real. Org settings covers the agent credential (write-only), concurrency cap, member management with roles, API token management (secret shown once), and the GitHub connection status — including a truthful revoked/disconnected state with visible stranded signals that reconnecting restores.

The API surface for repo config editing lands here with the screens that need it, same API-first bargain as slice 14.

**Blocked by:** 09 — Auth (org settings, tokens); 11 — GitHub surface (install flow, grant list); 13 — Daytona (snapshot status, rebuild, verify setup); 14 — Dashboard: signals and run room (SPA scaffold, auth flows, and client integration land there).

**Status:** ready-for-agent

- [ ] API tests: repo config read/update with env files write-only, prompt reset-to-default, rebuild and verify-setup triggers, org isolation on all of it
- [ ] Playthrough: fresh org → install App → enable repo → configure → verify setup succeeds → first manual signal runs end to end
- [ ] Disconnected installation renders truthfully: connection revoked, repos disconnected, stranded signals visible; reconnect restores

Spec sections: Snapshot and onboarding, Dashboard information architecture; user stories 1–11, 31, 36.
