# 11 — Labeled GitHub issue → run, loop closed on the issue

**What to build:** The signature workflow. An org connects GitHub by installing the Foresight App; the installation becomes an active surface connection and its granted repos can be enabled (default config prefilled). A developer labels an issue `foresight`: a signal is created and a run dispatched. The originating issue gets a start comment with a watch link and an in-progress label; when the run finishes, a finish comment (PR link on success, failure explanation otherwise) and a label swap. Merging the PR flips the run — and thus the signal — to done, with zero bookkeeping. Uninstalling the App is represented truthfully: connection revoked, repos disconnected, signals visibly stranded; reinstalling un-strands them.

The boundary discipline from the spec holds: the webhook endpoint verifies signatures and hands payloads to the GitHub surface adapter, which owns both directions — interpreting inbound events into domain actions, and write-back through a fakeable GitHub client (installation tokens minted from per-deployment App credentials). Everything the adapter remembers (comment IDs, applied labels) lives in the signal's surface-state blob; core never reads it.

**Blocked by:** 08 — Tracer bullet; 09 — Auth and orgs (connections belong to orgs).

**Status:** ready-for-agent

- [ ] Recorded webhook payloads POSTed at the real endpoint drive the whole flow: installation created → connection active; repos selected → Repo rows enabled with default config; issue labeled → signal + run; PR merged → run and signal done. Bad signatures rejected.
- [ ] The canonical end-to-end: labeled-issue webhook in, fake executor scripted to succeed, fake GitHub client saw the start comment, finish comment, and label swap, surface state updated, re-notify idempotent
- [ ] Failure write-back: a failed run's finish comment explains the failure reason
- [ ] Installation deleted → repos disconnected → signals derive stranded → dispatch refuses them; reinstall reverses it
- [ ] Demoable: a real App pointed at a test repo (or replayed payloads) produces the comments and labels

Spec sections: GitHub integration, Domain model (SurfaceConnection, Repo, surface state); user stories 5–6, 12, 14–15, 18, 26, 36.
