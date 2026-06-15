---
name: vss-doctor
description: Diagnose a running (or failing) VSS deployment. Probes the Pipeline Manager health and feature/config endpoints to detect which mode is live and what's enabled, then drills into docker compose state and logs for unhealthy services. Use when the user says "is vss up", "what mode is running", "vss is broken", "debug vss", "check vss health", or before any API workflow that needs a healthy backend.
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "vss operational diagnostics"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VSS Doctor

Find out whether VSS is healthy, which mode is running, and what's broken.
**Run every command yourself and relay the result.** If the stack isn't up, hand
off to the [`vss-up`](../vss-up/SKILL.md) skill.

Set `HOST=http://${HOST_IP:-localhost}:${APP_HOST_PORT:-12345}` for the snippets.

## 1. Is the backend reachable?

```bash
curl -sf --max-time 5 "$HOST/manager/health" && echo "  ← Pipeline Manager healthy" \
  || echo "UNREACHABLE — backend down or wrong HOST_IP/APP_HOST_PORT"
```
If unreachable → likely nothing deployed, or a crash. Go to step 4, then offer
`vss-up`.

## 2. Which mode is running & what's enabled?

```bash
curl -s "$HOST/manager/app/features" | jq .   # which capabilities are on (search/summary)
curl -s "$HOST/manager/app/config"   | jq .   # resolved system config
```
`app/features` returns **string flags**, not booleans —
`{"summary":"FEATURE_ON","search":"FEATURE_OFF"}` — so test against the string
(e.g. `jq -e '.search=="FEATURE_ON"'`). Use it to decide which workflow skills are
applicable (`vss-search` needs `search==FEATURE_ON`; `vss-summarize` needs
`summary==FEATURE_ON`).

## 3. Subsystem probes

```bash
curl -s "$HOST/manager/metrics/status"  | jq .   # telemetry collector connection
curl -s "$HOST/manager/audio/models"    | jq .   # whisper models loaded (summary modes)
curl -s "$HOST/manager/pipeline/evam"   | jq .   # EVAM pipeline status
```
In search modes also check the data-prep and embedding services:
```bash
curl -sf "http://${HOST_IP:-localhost}:7890/health" && echo "  ← data-prep ok"
curl -sf "http://${HOST_IP:-localhost}:9777/docs"   >/dev/null && echo "  ← embedding server ok"
```

## 4. Container-level diagnosis

> **⚠️ Bare `docker compose ps` fails from the repo root** with
> `no configuration file provided: not found` — the compose files live under
> `docker/` (`compose.base.yaml`, `compose.summary.yaml`, …) and `setup.sh`
> deploys them under the **project name `docker`**. Use `-p docker` (works from
> anywhere), or `cd docker/` first. Plain `docker ps` also works for a quick look.
> Container names are `docker-<service>-1` (e.g. `docker-pipeline-manager-1`).

```bash
docker compose -p docker ps                          # find Exited / unhealthy services
docker compose -p docker logs --tail=80 <service>    # read the failure
docker stats --no-stream                             # OOM / resource pressure on model servers
```
The heavy, slow-to-start services are the model servers: `ovms`, `vlm-ov` /
`vllm`, and the embedding server. A backend that 404s on `/manager/health` while
these are still loading is usually **starting**, not broken — re-probe step 1.

### Pipeline-manager unhealthy → check the DB connection

If `pipeline-manager` is the unhealthy/crashing service, inspect its logs for a
**database connection failure** before anything else:

```bash
docker compose -p docker logs --tail=120 pipeline-manager 2>&1 \
  | grep -iE "postgres|database|ECONNREFUSED|connection (refused|terminated)|password authentication|role .* does not exist|relation .* does not exist|migration"
```

If those lines are present, the metadata DB volume is the problem — typically a
stale Postgres volume left from a previous deploy whose credentials/schema no
longer match (e.g. after the credentials in `vss.secrets.env` were rotated). The
reliable fix is to wipe the user-data volumes and redeploy:

```bash
source setup.sh --clean-data
# then bring the stack back up in the desired mode (e.g. source setup.sh --summary)
```

> **⚠️ Destructive — confirm with the user first.** `--clean-data` removes all
> Docker volumes holding user data (DB, object store, ingested videos,
> embeddings). **Do not run it automatically.** Surface the DB-connection
> evidence, state that recovery requires wiping persisted data, and proceed only
> after the user explicitly agrees.

## Common diagnoses

| Symptom | Likely cause | Action |
|---|---|---|
| `/manager/health` connection refused | nothing deployed / wrong host:port | `vss-up` for the desired mode |
| Health OK but `app/features` lacks search | wrong mode deployed | redeploy with `--search`/`--dual`/`--unified` |
| A model-server container `Exited` | bad/missing model var or OOM | check `vss.config.env` model names; inspect `docker compose logs` |
| `Exited` right after start, env error in logs | missing required env var | re-source `vss-up/vss.config.env` + `vss-up/vss.secrets.env`, redeploy |
| `pipeline-manager` unhealthy, logs show DB connection errors | stale/mismatched Postgres volume | **confirm with user**, then `source setup.sh --clean-data` + redeploy (see step 4) |
| Everything `Up` but health still 404 | model servers still loading | wait and re-probe step 1 |

## Deeper failure modes → canonical troubleshooting doc

Once step 4 has surfaced a specific log signature, match it to the canonical
guide [`docs/user-guide/troubleshooting.md`](../../../docs/user-guide/troubleshooting.md)
and apply its fix — don't improvise. High-value mappings:

| Log / symptom you found | Section in `troubleshooting.md` |
|---|---|
| Containers `Up` but app misbehaves (stale data) | *Containers have started but the application is not working* (`--clean-data`) |
| OpenCV / `libGL` errors in summary or video-ingestion logs | *OpenGL/Mesa Library Dependencies* |
| Permission denied on `/app/ov-model` or `/home/appuser/.cache/huggingface`; VLM crashes loading models | *VLM Microservice Model Loading Issues* (remove `ov-models` / `docker_ov-models` volume) |
| Final summary stuck "Ready"/"In Progress"; OVMS exited; `…exceeds model max length` | *Final Summary Stuck or OVMS Container Stopped* / *Smaller Models… Limited Context Window* |
| `CL_OUT_OF_RESOURCES` / `onednn_verbose…errcode -5` on GPU | *GPU Out-of-Resources When Loading Multiple Models* |
| OVMS logs show `cache usage: 100.0%`; slow/truncated inference | *OVMS KV Cache Exhaustion* (`OVMS_CACHE_SIZE_GB`) |
| Search returns no results after switching embedding model | *Search returns no results after changing embedding model* |
| VLM/LLM fails only when `*_TARGET_DEVICE=NPU` | *VLM Workload Fails on NPU* |

## Output

Summarize as: **reachable?** → **mode/features** → **any unhealthy services** →
**recommended next step** (often a specific `vss-up` invocation).
