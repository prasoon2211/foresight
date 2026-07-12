# Sandbox provider selection

Type: research
Status: resolved

## Question

Which remote sandbox provider does Foresight V1 build on? Compare Daytona, E2B, Modal, Morph Cloud, Cloudflare Sandboxes (and anything else current) against the hard requirements:

1. **Docker-in-sandbox** — customer dev environments are often docker-compose; the sandbox must run a full Docker daemon inside.
2. **Fast warm start** — prebuilt image or snapshot with the repo pre-cloned; startup does only `git pull` + setup script.
3. **Attachability** — an exec/PTY channel good enough for a web terminal, and the ability to reach a TCP port inside the sandbox (the `opencode serve` HTTP/SSE endpoint) from the control plane and the user's browser.
4. **Lifecycle API** — create/destroy/snapshot from a server-side SDK or REST API usable from Django/Python.
5. **Pricing and limits** — cost per sandbox-hour at ~5–10 concurrent, ceiling for ~80+ concurrent later.

Deliverable: a markdown comparison summary linked from this ticket, with a recommendation. Also sanity-check that OpenCode runs cleanly inside the recommended provider (plain CLI process, no surprises).

## Answer

**Build on Daytona.** Runner-up: E2B. Full comparison with citations: [sandbox-provider-comparison.md](../assets/sandbox-provider-comparison.md).

Daytona is the only provider where every hard requirement is first-class: Docker-in-Docker with multi-service docker-compose is an officially documented workflow (pre-built `docker:dind` snapshot images, compose example in the Python SDK docs); snapshots build from any Dockerfile/OCI image with sub-second sandbox creation; attachability matches Foresight exactly (PTY-over-WebSocket for a web terminal, token-gated preview URLs for the control plane, signed expiring URLs for the user's browser); the Python SDK has full parity for Django; pricing is pure usage (~$0.33/h for a 4 vCPU / 8 GiB DinD sandbox, no base fee) and it's open source (AGPL) and self-hostable as an escape hatch. Cloudflare Sandboxes failed the Docker hard requirement (rootless only, no bridge networking, images lost on sleep); Modal's Docker path is an alpha-only VM runtime; E2B does everything but costs $150/mo base and its 100-concurrent default sits exactly at our later target.

Key watch-outs: Daytona's default per-sandbox cap is 4 vCPU / 8 GiB / 10 GiB disk (heavy compose stacks may need a limit raise); the 15-minute auto-stop default must be disabled (`auto_stop_interval=0`) or agent runs die mid-flight; 80+ concurrent lands in Tier 4 ($2k/30-day top-up cadence) or an enterprise plan. OpenCode (`opencode serve`, SSE, spawned shells, outbound HTTPS) runs cleanly in this class of sandbox — E2B even ships an official OpenCode template using the identical pattern — with two notes: bind `--hostname 0.0.0.0`, and build the snapshot on a Debian/Ubuntu base rather than the Alpine `docker:dind` image.
