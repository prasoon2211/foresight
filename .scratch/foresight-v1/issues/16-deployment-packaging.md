# 16 — Deployment packaging and operator docs

**What to build:** A self-hoster goes from git clone to a working Foresight with one command and one document. Production compose runs web (ASGI, serving the built SPA), the worker, Postgres, and storage for session exports, with health checks and restart policies. The operator guide walks through every environment variable (encryption keys and rotation, Daytona credentials, storage), creating the GitHub App (permissions, webhook URL and secret, private key), webhook reachability, and backups. Release hygiene: versioned images, a migration-on-deploy story, and the pinned agent-runtime version surfaced as configuration.

**Blocked by:** 14 — Dashboard: signals and run room; 15 — Dashboard: onboarding and settings.

**Status:** ready-for-agent

- [ ] Clean-machine dry run of the guide: compose up, App configured, org onboarded, one real signal → PR → merge → done, sandbox archived, reconciliation clean
- [ ] Every required environment variable documented; missing required config fails loudly at startup, not at first use
- [ ] Images versioned and migrations applied on deploy without manual steps

Spec sections: Solution (compose-deployable); user stories 34–35.
