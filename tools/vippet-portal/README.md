# ViPPET Portal

Aggregates benchmark, performance and density results from **multiple ViPPET
instances** into a single comparison view. It is read-only: it never triggers
work on a machine, it only polls each instance's public API.

The UI reuses the ViPPET design system (Tailwind v4 tokens, shadcn/Radix
component kit, Intel branding) so the portal looks and behaves like ViPPET
itself.

## Registering instances

No instances are registered by default. Add them in the **Instances** page, or
pre-seed them with the `PORTAL_INSTANCES` environment variable:

```bash
PORTAL_INSTANCES="Lab machine 1=http://vippet-host-1:8080,Lab machine 2=http://vippet-host-2:8080"
```

Adding a machine requires nothing but its ViPPET URL — CPU/GPU/NPU identity and
version are discovered automatically from `/api/v1/devices` and `/api/v1/status`.

## What you can compare

- **Benchmark suite runs** — overall / performance / efficiency scores, pass
  rate and duration at suite level, then every workload and every test case
  (variant × stream count) aligned row-by-row across machines.
- **Performance tests** — individual runs, aligned by pipeline + stream count.
- **Density tests** — individual runs, aligned by pipeline + FPS floor.

Each comparison shows the first selected result as the **baseline** and colours
the deltas by whether the metric is better or worse for that metric's direction
(FPS higher-is-better, latency/power lower-is-better).

## Running

### Docker (recommended)

```bash
make run          # http://localhost:8080
make stop
```

Docker builds forward the shell's `http_proxy`, `https_proxy`, and `no_proxy`
settings (falling back to uppercase names) for npm and pip downloads. Export
these variables before running `make run` when a network proxy is required.
They are build-only settings and are not persisted in the runtime image.

### Local development

```bash
make install
make dev-server   # API on :8765, also serves ui/ build if present
make dev-ui       # Vite dev server on :5173, proxies /api to :8765
```

Node 20.19+ (22 recommended) is required by Vite 8.

## Configuration

| Variable                 | Default                        | Purpose |
| ------------------------ | ------------------------------ | ------- |
| `PORTAL_INSTANCES`       | _(empty)_                      | `Name=url,Name2=url2`, seeded into the database on first start only |
| `PORTAL_DATA_DIR`        | `./data`                       | Where `portal.db` lives |
| `PORTAL_REQUEST_TIMEOUT` | `15`                           | Per-request timeout against one instance (seconds) |
| `PORTAL_CACHE_TTL`       | `15`                           | TTL of cached benchmark run details (seconds) |

Outbound calls deliberately ignore `HTTP_PROXY`/`HTTPS_PROXY` so a corporate
proxy cannot hijack requests to testbed machines on the local network.

## Architecture

```
ui/      React 19 + TypeScript + Vite + Tailwind v4 (ViPPET component kit)
server/  FastAPI aggregator + SQLite instance registry
```

The backend fans out to every enabled instance with `asyncio.gather`, isolating
failures per instance — one offline machine degrades its card to “offline”
instead of breaking the page. Benchmark run details are stripped of their
embedded raw telemetry series (megabytes per run) before being returned.

### Portal API

| Endpoint | Purpose |
| -------- | ------- |
| `GET /api/v1/instances` | Registered instances with live health and platform identity |
| `POST/PATCH/DELETE /api/v1/instances[/{id}]` | Manage the registry |
| `GET /api/v1/benchmarks/runs` | All suite runs across all machines |
| `GET /api/v1/benchmarks/runs/{ref}` | One run in detail (telemetry stripped) |
| `GET /api/v1/benchmarks/compare?refs=…` | Aligned comparison matrix |
| `GET /api/v1/tests/{performance\|density}` | All test jobs across all machines |
| `GET /api/v1/tests/{kind}/compare?refs=…` | Aligned comparison matrix |

A *ref* is a stable portal-wide identifier:
`"<instance_id>:<suite_slug>:<run_id>"` for benchmark runs and
`"<instance_id>:<job_id>"` for test jobs.

### Upstream ViPPET endpoints consumed

`/api/v1/status`, `/api/v1/devices`, `/api/v1/benchmarks/runs`,
`/api/v1/benchmarks/{slug}/run/{id}`, `/api/v1/jobs/tests/{kind}/status`,
`/api/v1/jobs/tests/{kind}/{job_id}`.

Older instances that do not report `version` in `/status` are handled gracefully.
