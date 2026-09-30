<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Build & Deploy

## Build from source

The step-by-step build/push/deploy walkthrough is already maintained in
[Get Started](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.2.0/microservices/time-series-analytics/docs/user-guide/get-started.md)
(`docker compose build`, optional `--build-arg COPYLEFT_SOURCES=true` for
license-scan builds, `docker compose up -d`) — follow that rather than a
copy here. What it doesn't itemize is which build args matter for
day-to-day dev work (see `docker/docker-compose.yml`'s `build.args` and the
`Dockerfile`): `KAPACITOR_VERSION` (1.8.6 — sparse-checked-out from
`influxdata/kapacitor` for the UDF agent, and installed as a `.deb` for the
daemon), `PYTHON_VERSION` (3.13), `TIMESERIES_UID`/`TIMESERIES_USER_NAME`
(non-root user the container runs as).

## Environment (`docker/.env`)

| Var | Purpose |
|---|---|
| `KAPACITOR_PORT` | Kapacitor's internal port (default 9092; the REST API is always on host port 5000) |
| `LOG_LEVEL` | Sets `KAPACITOR_LOGGING_LEVEL`, controlling both the FastAPI app's and Kapacitor's log verbosity |
| `TIME_SERIES_ANALYTICS_IMAGE` / `IMAGE_SUFFIX` / `WEEKLY_BUILD_DATE` | Image name/tag resolution — see `release-conventions.md` |
| `DOCKER_REGISTRY` / `DOCKER_USERNAME` / `DOCKER_PASSWORD` | Only needed for pushing to a registry |
| `timeseries_no_proxy` | Proxy exclusions for the build/runtime environment |

## GPU support

- `scripts/install_gpu_drivers.sh` installs Intel iGPU drivers into the
  image at build time (version pinned via `INSTALL_DRIVER_VERSION` build
  arg).
- The compose file unconditionally mounts `/dev/dri` (as both a volume and
  under `devices:`) and adds render-group GIDs for Ubuntu 20.04/22.04/24.04
  hosts via `group_add`. On a host with no Intel iGPU, this device mount
  can fail container startup — comment out the `/dev/dri` volume and
  `devices:` entries if you're building/testing on such a host and don't
  need GPU-backed UDF inference.
- A UDF requests GPU execution via `config.json`'s `udfs.device`; see the
  `-user` skill's `references/udf-authoring.md` for the runtime contract.

## CPU core pinning

`docker/run.sh` (the container `ENTRYPOINT`) reads the `CORE_PINNING` env
var (`e-cores` / `p-cores` / `lp-cores` / `lpe-cores` / a literal core list)
and uses `docker/detect-cores.sh` to `taskset` the main process onto matching
cores. `lp-cores` and `lpe-cores` are aliases for the same LP/E-core set.
Unset or empty means no pinning. Useful when benchmarking on hybrid Intel
CPUs (P-core/E-core).

## Health & verification

```bash
curl -sf http://localhost:5000/health   # proxies Kapacitor daemon health, not just process liveness
docker logs -f ia-time-series-analytics-microservice
```

## Helm deployment

Full walkthrough:
[Deploy with Helm](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.2.0/microservices/time-series-analytics/docs/user-guide/get-started/deploy-with-helm.md)
(chart-specific value docs: `helm/README.md`). The one gotcha worth calling
out here since it's easy to trip over while testing: the Helm deployment's
externally exposed REST API port is **30002**
(`config.time_series_analytics_microservice_rest_api.ext.port` in
`helm/values.yaml`), distinct from the Docker Compose deployment's **5000**
— don't assume the port from one deployment mode carries over to the other.

## Teardown

```bash
docker compose down -v   # -v removes the tmpfs volume UDF packages extract into
helm uninstall time-series-analytics-microservice -n apps
```
