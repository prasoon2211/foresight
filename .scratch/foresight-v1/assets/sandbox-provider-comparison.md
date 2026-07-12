# Sandbox provider comparison for Foresight V1

Research for [issue 01](../issues/01-sandbox-provider-research.md), July 2026. All claims cite primary sources (official docs, pricing pages, SDK references, source repos) current as of this date.

**Recommendation: Daytona.** Runner-up: **E2B**. Details and reasoning below.

Providers compared: Daytona, E2B, Modal, Morph Cloud, Cloudflare Sandboxes, plus Fly.io Sprites as a credible extra candidate.

---

## Requirement 1 — Docker-in-sandbox (HARD)

| Provider | Verdict | Detail |
|---|---|---|
| **Daytona** | ✅ First-class | Officially documented Docker-in-Docker: create a snapshot from a pre-built `docker:28.3.3-dind` image (or install Docker in a custom image), then run a full Docker daemon and **multi-service docker-compose** inside the sandbox. Docs show the exact compose workflow in Python. Recommends ≥2 vCPU / 4 GiB for the daemon overhead. Daytona also offers full Linux VM sandboxes (`LINUX_VM` sandbox class) if container-level DinD ever proves insufficient. ([Daytona snapshots docs — "Run Docker in a sandbox"](https://www.daytona.io/docs/en/snapshots/), [sandboxes docs — VM sandboxes](https://www.daytona.io/docs/en/sandboxes/)) |
| **E2B** | ✅ Supported | Official docs and cookbook show templates with Docker Engine + docker-compose installed and running inside the Firecracker microVM (E2B pre-configures the guest kernel, so none of the raw-Firecracker kernel pain applies). Recommends ≥2 CPU / 2 GB RAM. ([E2B template examples — Docker & Docker Compose](https://e2b.dev/docs/template/examples/docker), [e2b-cookbook docker-in-e2b](https://github.com/e2b-dev/e2b-cookbook/tree/main/examples/docker-in-e2b)) |
| **Modal** | ⚠️ Experimental | Default sandboxes run on gVisor, which **cannot run `dockerd`** (multi-service compose networking explicitly fails). Docker requires the new "VM Sandboxes" runtime via `experimental_options={"vm_runtime": True}` — announced as **Alpha** and still flagged experimental in the SDK. Betting a hard requirement on an alpha flag is risky. ([Modal VM Sandboxes guide](https://modal.com/docs/guide/vm-sandboxes), [Modal product update — "VM Sandboxes (Alpha)"](https://modal.com/blog/product-updates-vm-sandboxes-domain)) |
| **Morph Cloud** | ✅ Full VM | MorphVMs are real VMs; docs state "run any docker container (and any docker-in-docker workload)". No caveats found. ([Infinibranch announcement](https://cloud.morph.so/docs/blog/developers), [Devboxes product page](https://cloud.morph.so/web/product/devboxes)) |
| **Cloudflare Sandboxes** | ❌ Effectively disqualified | DinD added Feb 2026, but containers run **without root**: rootless Docker only, `--iptables=false` required, inner containers need `--network=host`, no privileged containers, and built images are **lost when the sandbox sleeps**. Typical customer docker-compose files (multiple services on a bridge network, published ports) will not run as-written. ([Cloudflare DinD guide](https://developers.cloudflare.com/sandbox/guides/docker-in-docker/), [changelog](https://developers.cloudflare.com/changelog/post/2026-02-17-docker-in-docker/)) |
| **Fly.io Sprites** | ⚠️ DIY | Full VMs with root, so Docker works, but there's no official recipe: no systemd (start `dockerd` manually), and Fly's own CEO advises moving Docker storage off `/var/lib/docker` onto a loopback-mounted sparse image to avoid severe I/O degradation. Workable but rough. ([Fly community — Docker on Sprites](https://community.fly.io/t/how-to-get-docker-running-on-sprites/27168), [Sprite too slow for docker?](https://community.fly.io/t/sprite-too-slow-for-docker/27088)) |

Cloudflare is disqualified on the hard requirement. Modal is effectively disqualified for V1 (alpha-only path). Fly Sprites deprioritized (no official Docker support path, no Python SDK — CLI/REST/JS/Go only).

## Requirement 2 — Fast warm start (prebuilt image with repo pre-cloned)

- **Daytona**: Snapshots are reusable templates built from any Docker/OCI image, a Dockerfile (`daytona snapshot create --dockerfile`), or a declarative builder — so we bake the customer repo + toolchain into a snapshot and each run only does `git pull` + setup. Sandbox creation from a snapshot is **sub-90 ms** (marketing figure; real-world "ready" time is dominated by our own setup script, not the provider). ([Snapshots docs](https://www.daytona.io/docs/en/snapshots/), [daytona.io](https://www.daytona.io/))
- **E2B**: Templates build to a **Firecracker snapshot including a running process**: `setStartCmd` + `readyCmd` run at build time and get captured, so a sandbox can start with `opencode serve` (or dockerd) already running — genuinely zero-wait warm start. Sandbox creation ~150 ms. ([Start & ready commands](https://e2b.dev/docs/template/start-ready-command), [template quickstart](https://e2b.dev/docs/template/quickstart))
- **Morph**: Snapshot/branch/restore of full VM state (memory + filesystem) in <250 ms ("Infinibranch"); snapshot a fully-warmed VM with dockerd running and repo cloned, restore on demand. Strongest snapshot model of the group. ([Morph docs](https://cloud.morph.so/docs/developers))
- **Modal**: filesystem snapshots + memory snapshots exist, but see Req 1.
- **Cloudflare**: has backup/restore APIs, but Docker images inside don't survive sleep — defeats the purpose.

All three finalists satisfy this. E2B's captured-running-process snapshot and Morph's memory snapshots are technically nicer; Daytona's image-based snapshots are sufficient (dockerd starts fresh each run — a few seconds).

## Requirement 3 — Attachability (web terminal + reachable TCP port)

- **Daytona**: Best-in-class for our shape.
  - **PTY**: first-class PTY sessions via SDK/WebSocket (`sandbox.process.create_pty_session`, resize, reconnect) — exactly what a web terminal needs. Plus a built-in browser web terminal on port 22222. ([PTY docs](https://www.daytona.io/docs/en/pty/), [web terminal docs](https://www.daytona.io/docs/en/web-terminal/))
  - **Port access**: preview URLs for any port 1–65535: `https://{port}-{sandboxId}.proxy...`. Two auth modes: header token (`x-daytona-preview-token`) for the control plane, and **signed URLs** (token embedded, expiring) for handing to a user's browser. WebSockets/SSE proxied. A self-hostable custom preview proxy is available if we want our own domain + auth. ([Preview docs](https://www.daytona.io/docs/en/preview/), [custom preview proxy](https://www.daytona.io/docs/en/custom-preview-proxy/))
  - Caveat: the built-in web terminal (22222) is restricted to Daytona org members even on public sandboxes — for end-user browser attach we'd use our own xterm.js + PTY WebSocket or a signed preview URL to `opencode web`, which is the plan anyway.
- **E2B**: PTY module in the SDK (`sandbox.pty.create`, `send_stdin`, connect-by-pid); every sandbox gets a public URL per port via `sandbox.get_host(port)` (`https://{port}-{sandboxId}.e2b.app`), with optional auth-gating (`allow_public_traffic=False`) and host masking. Fully adequate. ([PTY docs](https://e2b.dev/docs/sandbox/pty), [public URL docs](https://e2b.dev/docs/network/public-url))
- **Morph**: `instance.expose_http_service(name, port, auth_mode="api_key")` gives public or API-key-gated URLs; SSH-based exec; built-in browser remote desktop. No purpose-built PTY-over-WebSocket API in the docs — web terminal would ride on SSH. ([HTTP services docs](https://cloud.morph.so/docs/documentation/instances/http-services))
- **Modal**: tunnels (`encrypted_ports` + `sb.tunnels()`), connect tokens, PTY support in exec. Good, but moot given Req 1.
- **Cloudflare**: excellent PTY/xterm.js story, moot given Req 1.

## Requirement 4 — Lifecycle API from Django/Python

- **Daytona**: Python SDK is a first-class citizen (sync + async), covering create/destroy/snapshot/PTY/preview/fs/exec; plus REST API with OpenAPI spec. `pip install daytona`. ([Python SDK reference](https://www.daytona.io/docs/en/python-sdk/sync/daytona.md))
- **E2B**: mature Python SDK (`e2b`, v2.x) with same coverage incl. template builds from Python. ([Python SDK reference](https://e2b.dev/docs/sdk-reference/python-sdk/v2.15.0/sandbox_sync))
- **Morph**: official Python SDK (`morphcloud`) — instances, snapshots, TTL, exec, expose services. Smaller ecosystem/company than the other two. ([Morph docs](https://cloud.morph.so/docs/developers))
- **Modal**: Python-first, the best pure SDK of the lot — but the runtime we need is alpha.
- **Cloudflare**: **TypeScript-only SDK** bound to Workers/Durable Objects — no server-side Python SDK at all; a Django control plane would need a Worker shim. ([Sandbox SDK docs](https://developers.cloudflare.com/sandbox/))

## Requirement 5 — Pricing and limits

Reference workload: a DinD-capable sandbox at 4 vCPU / 8 GiB RAM (Daytona's recommended-plus size for compose stacks).

| Provider | Compute rate | 4 vCPU/8 GiB sandbox-hour | Base fee | Max lifetime | Concurrency ceiling |
|---|---|---|---|---|---|
| **Daytona** | $0.0504/vCPU-h + $0.0162/GiB-h + $0.000108/GiB-h disk | **≈ $0.33/h** | none ($200 free credits) | none (auto-stop default 15 min; set `auto_stop_interval=0`) | org compute pool by tier: T1 10 vCPU → T2 100 vCPU ($25 top-up) → T3 250 → T4 500 ($2k/30d top-ups) → custom |
| **E2B** | $0.0504/vCPU-h + $0.0162/GiB-h (per-second) | **≈ $0.33/h** | **$150/mo Pro required** (free tier caps sessions at 1 h — too short for us) | 24 h continuous (Pro); pause/resume resets the clock | 100 concurrent (Pro), addon to 1,100, Enterprise beyond |
| **Modal** | $0.1419/physical-core-h (=2 vCPU) + $0.0242/GiB-h, ×1.25 region multiplier | ≈ $0.48–0.60/h | none | 24 h max timeout | very high (platform-level) |
| **Morph** | $0.05/MCU-h, MCUs = max(vCPU, RAM/4GiB, disk/16GiB) | **≈ $0.20/h** (4 MCU) | $0 / $40 / $250 tiers | none (TTL is user-set) | tier caps: 64 vCPU total (free) → 256 ($40) → 1024 ($250) |
| **Cloudflare** | Active-CPU pricing on Workers Paid | n/a | Workers Paid | sleeps on idle | 1,000+ large instances |

Sources: [Daytona pricing](https://www.daytona.io/pricing) + [limits docs](https://www.daytona.io/docs/en/limits/); [E2B pricing](https://www.e2b.dev/pricing) + [billing docs](https://www.e2b.dev/docs/billing); [Modal pricing via sandbox docs](https://modal.com/docs/guide/sandbox); [Morph subscribe page](https://cloud.morph.so/web/subscribe); [Cloudflare GA post](https://blog.cloudflare.com/sandbox-ga/).

**At our scale.** 5–10 concurrent 4-vCPU sandboxes ≈ 20–40 vCPU → Daytona Tier 2 (a $25 top-up), roughly $0.33/sandbox-hour, no monthly base. 80+ concurrent ≈ 320+ vCPU → Daytona Tier 4 (500 vCPU, requires $2,000/30-day top-up cadence — which real usage at that scale would consume anyway: 80 sandboxes × $0.33/h × ~8 h/day ≈ $6.3k/mo) or a custom limit. E2B at the same scale: same compute rate + $150/mo, 100-concurrent default is exactly at our ceiling; the addon to 1,100 covers growth. Morph is cheapest per hour but its published tiers cap total vCPU lower (1,024 vCPU at $250/mo tier) and concurrency figures for devboxes (8/32/128) suggest earlier sales conversations.

**Lifetime limits vs 30–120 min agent runs.** No provider's cap threatens us: Daytona has none (must disable 15-min auto-stop or call `refresh_activity()`), E2B Pro allows 24 h continuous, Modal 24 h, Morph unlimited via TTL. E2B's free tier (1 h) is the only outright conflict, and only if we tried to avoid the Pro fee.

---

## Recommendation: Daytona (runner-up: E2B)

**Daytona wins** because it is the only provider where every hard requirement is first-class and documented, with no monthly base fee:

1. **Docker-compose-in-sandbox is an officially documented, supported workflow** — pre-built DinD snapshot images, compose example in the Python SDK docs. (Third-party corroboration: the Inspect Sandboxes project routes multi-service compose workloads to Daytona precisely because Modal can't do it.)
2. **Attachability matches Foresight's architecture exactly**: PTY sessions over WebSocket for our web terminal, token-gated preview URLs for the control plane → `opencode serve`, signed expiring URLs to hand to a user's browser.
3. **Python SDK parity** — Django control plane needs no shim.
4. **Snapshot-from-Dockerfile** gives the prebuilt-image + `git pull` warm start pattern directly; sandbox creation is sub-second.
5. Escape hatches exist: full Linux **VM sandboxes** if container DinD hits a wall, and the platform is **open source (AGPL) and self-hostable** if pricing/limits ever bite.

**E2B is the runner-up**, not far behind: Docker + compose documented, superb template snapshots (can capture a *running* `opencode serve`), mature Python SDK, public per-port URLs, pause/resume. It loses on: $150/mo base fee before the first sandbox, 24 h continuous-runtime cap (harmless now, one more thing to manage), a default concurrency ceiling (100) exactly at our later target, and DinD being a cookbook recipe rather than a headline feature.

### Watch-outs for Daytona (for the map)

- **Per-sandbox resource cap is 4 vCPU / 8 GiB RAM / 10 GiB disk by default** ([sandboxes docs](https://www.daytona.io/docs/en/sandboxes/)). A heavy customer compose stack (several services + DB + the OpenCode agent) could hit RAM or disk; higher limits require contacting Daytona. This is the biggest single risk.
- **Auto-stop defaults to 15 minutes** even with processes running — every Foresight sandbox must set `auto_stop_interval=0` or refresh activity, or agent runs die mid-flight.
- DinD means Docker images are pulled into the sandbox's 10 GiB disk each run unless baked into the snapshot — bake `docker pull` results into the snapshot image where possible.
- Tier system ties limits to top-up cadence ($2k/30 days for Tier 4); at 80+ concurrent, plan an enterprise conversation.
- Isolation is container-grade (user namespaces), not microVM — fine for trusted-ish customer code, worth noting for the security story.

## OpenCode inside Daytona — sanity check

OpenCode is a plain Node/Bun CLI; `opencode serve --hostname 0.0.0.0 --port 4096` exposes an OpenAPI HTTP server with an SSE `/event` stream ([OpenCode server docs](https://opencode.ai/docs/server/)). Checks against Daytona:

- **Long-running process**: fine — sessions via `sandbox.process` persist; the only killer is the 15-min auto-stop default, which we disable (above).
- **Reaching the port**: `sandbox.get_preview_link(4096)` from Django (header token); `create_signed_preview_url(4096)` for the user's browser running `opencode web`. Daytona's preview proxy explicitly supports WebSockets, and SSE is plain HTTP streaming — no special handling. Bind to `0.0.0.0`, not the default `127.0.0.1`.
- **SSE buffering**: OpenCode already sends `X-Accel-Buffering: no` on SSE responses to defeat proxy buffering; verify end-to-end once, but no red flag.
- **Nested processes / outbound network**: OpenCode spawns shells and needs outbound HTTPS to LLM APIs — Daytona sandboxes have outbound network by default and no restrictions on child processes. The DinD base image is Alpine (`docker:dind`); prefer building our snapshot on a Debian/Ubuntu base with Docker installed so Node/Bun and customers' toolchains behave normally (Alpine musl can bite Bun).
- **CORS**: if the user's browser talks to `opencode serve` directly through a preview URL, pass `--cors <our-dashboard-origin>` since the origin won't be localhost.
- **Precedent**: E2B ships an official OpenCode template running exactly this pattern (`opencode serve --hostname 0.0.0.0 --port 4096` + public URL) ([E2B OpenCode guide](https://e2b.dev/docs/agents/opencode)), confirming the agent runs happily in this class of sandbox; nothing in it is E2B-specific.

## Sources index

- Daytona: [snapshots/DinD](https://www.daytona.io/docs/en/snapshots/) · [sandboxes & VM class](https://www.daytona.io/docs/en/sandboxes/) · [preview URLs](https://www.daytona.io/docs/en/preview/) · [PTY](https://www.daytona.io/docs/en/pty/) · [web terminal](https://www.daytona.io/docs/en/web-terminal/) · [custom preview proxy](https://www.daytona.io/docs/en/custom-preview-proxy/) · [limits/tiers](https://www.daytona.io/docs/en/limits/) · [pricing](https://www.daytona.io/pricing) · [Python SDK](https://www.daytona.io/docs/en/python-sdk/sync/daytona.md)
- E2B: [Docker templates](https://e2b.dev/docs/template/examples/docker) · [docker-in-e2b cookbook](https://github.com/e2b-dev/e2b-cookbook/tree/main/examples/docker-in-e2b) · [start/ready cmd snapshots](https://e2b.dev/docs/template/start-ready-command) · [public URLs](https://e2b.dev/docs/network/public-url) · [PTY](https://e2b.dev/docs/sandbox/pty) · [persistence/pause-resume](https://e2b.dev/docs/sandbox/persistence) · [billing/limits](https://www.e2b.dev/docs/billing) · [pricing](https://www.e2b.dev/pricing) · [OpenCode template](https://e2b.dev/docs/agents/opencode)
- Modal: [VM Sandboxes (Docker)](https://modal.com/docs/guide/vm-sandboxes) · [VM Sandboxes alpha announcement](https://modal.com/blog/product-updates-vm-sandboxes-domain) · [Sandbox SDK](https://modal.com/docs/sdk/py/latest/modal.Sandbox) · [tunnels](https://modal.com/docs/guide/tunnels)
- Morph Cloud: [docs/Infinibranch](https://cloud.morph.so/docs/developers) · [HTTP services](https://cloud.morph.so/docs/documentation/instances/http-services) · [TTL](https://cloud.morph.so/docs/documentation/instances/ttl) · [pricing/tiers](https://cloud.morph.so/web/subscribe)
- Cloudflare: [DinD guide](https://developers.cloudflare.com/sandbox/guides/docker-in-docker/) · [GA announcement](https://blog.cloudflare.com/sandbox-ga/) · [terminal/PTY](https://developers.cloudflare.com/sandbox/api/terminal/index.md) · [lifecycle](https://developers.cloudflare.com/sandbox/api/lifecycle/)
- Fly Sprites: [design post](https://fly.io/blog/design-and-implementation/) · [Docker-on-Sprites community threads](https://community.fly.io/t/how-to-get-docker-running-on-sprites/27168)
- OpenCode: [server docs](https://opencode.ai/docs/server/)
