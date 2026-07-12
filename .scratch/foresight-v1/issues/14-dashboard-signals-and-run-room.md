# 14 — Dashboard: signals and the run room

**What to build:** The daily-use half of the product in a browser. A user logs into the SPA, sees the signals list with derived outcome statuses (stranded ones flagged), creates a manual signal, and opens a signal's history of runs. In the run room they follow the state timeline live, watch the agent's session as it happens (served browser-to-sandbox via freshly minted signed URLs — re-requested on expiry, never cached), open a web terminal into the sandbox, copy the one-liner that attaches their local terminal to the live session, stop a doomed run, re-run a disappointing one, and read the result card, failure detail, and full transcript afterward — plus revive a recently archived sandbox when available.

The API additions this behavior needs land here with it, honoring API-first: attach-endpoint minting (signed web/API URLs, TUI command, web-terminal ticket), the dashboard-authenticated websocket proxy that bridges to the provider PTY so provider credentials never reach the browser, and live run-state updates streamed or cheaply polled off the Run rows. The SPA consumes the generated TypeScript client; per the repo's testing rules the UI gets no automated suite — the API tests carry the behavior, the UI is thin wiring.

**Blocked by:** 09 — Auth (login, org context); 10 — Run control (stop, re-run); 11 — GitHub surface (real signals to show); 13 — Daytona (real attach endpoints to mint).

**Status:** ready-for-agent

- [ ] API tests for every new capability: attach-URL minting calls the executor and never caches, websocket-proxy auth enforced, live state reflects Run-row changes, transcript retrieval, revive-when-available
- [ ] Playthrough against a locally running backend: a labeled-issue signal appears in the list, its run watched live, terminal attached, a run stopped, a signal re-run, result card and transcript render
- [ ] Stranded signals visibly flagged in the list; failure reasons and detail readable in the run room

Spec sections: Dashboard information architecture, API-first; user stories 13, 16–30.
