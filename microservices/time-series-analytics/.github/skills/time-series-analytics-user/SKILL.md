---
name: time-series-analytics-user
description: >
  Build a new time-series analytics use case on top of the deployed Time
  Series Analytics microservice — bring it up with Docker Compose (from a
  repo clone, or by fetching the compose files from GitHub when no clone
  exists) using the prebuilt intel/ia-time-series-analytics-microservice
  image, then author a UDF (Python) + TICKscript pair for the use case
  (threshold alerting, rate-of-change/spike detection, rolling-window
  anomaly detection, pretrained-model inference per point, or batch
  windowed inference over a time window), package it as a tar, deploy it
  via the REST API, and feed it data. Use when the user describes a
  sensor/metric monitoring or anomaly-detection scenario, wants to plug
  their own analytics logic or a trained scikit-learn model into a
  streaming or windowed-batch pipeline, or asks to wire up MQTT/OPC UA
  alerting on top of this service. Not for modifying the microservice's
  own source code — that is time-series-analytics-dev.
---

# Time Series Analytics — User

## Capabilities Required

This skill runs shell commands (`docker compose`, `curl`, `tar`,
`scripts/package_udf.sh`) and writes files to the working directory. The
STANDALONE setup path fetches a public Docker Compose configuration from
the official Intel GitHub repository. No credentials are transmitted; the
fetched file is a public configuration template only.

## Overview

Build new use cases on the deployed service: you write a small UDF and a
TICKscript, package them, deploy them over REST, and feed data in. **Run
commands yourself** and relay output. The service listens on host port
**5000**; Swagger UI is at `http://localhost:5000/docs`.

## When to Use

- Turn a monitoring/anomaly-detection description into a working UDF +
  TICKscript pair and deploy it
- Plug a pretrained scikit-learn model into the streaming pipeline (per-point)
  or batch windowed pipeline (`|window()` + `begin_batch`/`end_batch`)
- Wire up MQTT (native TICKscript alert node) or OPC UA (REST endpoint)
  alerting on flagged points
- Debug why a deployed UDF isn't receiving data or a package upload fails

## Example Prompts

Run these prompts to build a complete, working use case. Output is generated in `examples/<use-case-name>/`:

| Example Prompt | Use Case | Output Location |
|---|---|---|
| [windturbine-anomaly-model.md](./example-prompts/windturbine-anomaly-model.md) | Pretrained IsolationForest model inference (per-point) | `examples/<udf-name>/` |
| [pressure-threshold-alert.md](./example-prompts/pressure-threshold-alert.md) | Threshold-based alerts | `examples/<udf-name>/` |
| [vibration-spike-mqtt-alert.md](./example-prompts/vibration-spike-mqtt-alert.md) | Rate-of-change spike detection + MQTT | `examples/<udf-name>/` |

## Output Directory Layout

When you complete a prompt, the generated use case is placed in `examples/<use-case-name>/` following this structure:

```
examples/<use-case-name>/
├── README.md                           ← Quick start + customization guide
├── deploy.sh                           ← Setup automation script
├── test.sh                             ← Validation script
├── test_data.json                      ← Sample input for testing
├── config.json                         ← UDF configuration (upload to microservice)
├── <use-case-name>.tar                 ← Packaged UDF (upload to microservice)
├── DEPLOYMENT_VALIDATION_REPORT.md     ← Test results and diagnostics
│
├── udfs/
│   └── <udf-name>.py                   ← Kapacitor Python UDF handler
├── tick_scripts/
│   └── <udf-name>.tick                 ← TICKscript wiring
└── models/
    └── <model-name>.pkl (or .xml/.bin) ← Pre-trained model file(s) (if applicable)
```

**To run a generated example:**
```bash
cd examples/<use-case-name>
chmod +x deploy.sh test.sh
./deploy.sh    # prints next steps
./test.sh      # validates deployment
```

## Evidence you must show in the final answer

For evals and any live deployment/validation request, do not just say the
workflow succeeded — print concrete evidence gathered from the commands you
ran so the grader can verify it from your response alone:

- **REST deployment proof**
  - Print the exact response body from `POST /udfs/package`
  - Print the exact response body from `POST /config` (or `POST /config?restart=true`)
- **File proof**
  - Name the exact generated files, including:
    - `udfs/<name>.py`
    - `tick_scripts/<name>.tick`
    - `<name>.tar`
  - Quote the specific TICKscript line invoking `@<name>()`
  - For alerting scripts, also quote the full alert chain line showing the UDF
    node reference and required alert methods (for example
    `@<name>() |alert().crit(lambda: TRUE).mqtt('<topic>').brokerName('<broker>')`)
  - Quote the exact field-access line from the UDF showing it reads the required
    input field (for example `pressure_bar = point.fieldsDouble["pressure_bar"]`)
  - For pretrained-model UDFs, quote the `__init__`/startup line that loads the
    model once and the `model.predict(...)` line
- **Config proof**
  - Quote the exact JSON payload posted to `POST /config` (or `?restart=true`),
    so `udfs.name`, `udfs.models`, `udfs.device`, and `alerts.mqtt` settings are
    visible to the grader
- **Log proof**
  - Quote the exact container log line showing a flagged anomaly
  - Quote the exact container log evidence for the non-flag case:
    show the input/received line for the non-anomalous point and explicitly say
    no matching `Flagged anomalous point ...` line appeared afterward
- **MQTT proof**
  - Subscribe on the broker itself (for example with `docker exec <broker>
    mosquitto_sub ...`) and print the actual message captured from the broker
  - Also state explicitly that no second message arrived for the non-triggering
    point

If the user asked for live verification, your answer is incomplete unless it
includes these concrete response/log/message snippets.

## Reference Lookup

| File | Load when… |
|---|---|
| [`references/patterns.md`](./references/patterns.md) | choosing an approach — threshold, rate-of-change, rolling z-score, **pretrained model (classification or regression-based anomaly detection)**, or batch inference — **start here** for any new UDF |
| [`references/udf-authoring.md`](./references/udf-authoring.md) | writing the UDF's `Handler` methods, reading point fields, loading a model, logging best practices, point emission strategy |
| [`references/tickscript-basics.md`](./references/tickscript-basics.md) | writing the tick script, wiring MQTT alerting; basic form (recommended) is just stream → UDF (no explicit influxDBOut needed) |
| [`references/api-workflow.md`](./references/api-workflow.md) | the package's internal structure and a troubleshooting table for a failed upload or a silent pipeline (links out to the microservice's own docs for the deploy sequence and API reference) |

## 1. Get the service running

```bash
[ -f docker/docker-compose.yml ] && echo REPO || echo STANDALONE
```

- **REPO** (repo clone present) → `cd docker && docker compose up -d`
- **STANDALONE** (no clone) → follow the
  [Get Started guide](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.2.0/microservices/time-series-analytics/docs/user-guide/get-started.md) to fetch
  the compose files and bring up the service (it covers the exact
  `docker compose up` sequence for the prebuilt image), then return here
  for step 2.
- Already running → confirm with the health-check command from the
  [Get Started guide](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.2.0/microservices/time-series-analytics/docs/user-guide/get-started.md)
  then skip to step 2.
- **Host has no Intel iGPU?** The compose file unconditionally mounts
  `/dev/dri` and adds it under `devices:`. If `docker compose up` fails on
  that device mount, comment out both the `devices:` entry and the
  `/dev/dri` line under `volumes:` in `docker/docker-compose.yml` — nothing
  else in this workflow needs a GPU unless you specifically set
  `udfs.device: GPU` in a UDF's config.

Wait for the REST API and Kapacitor to be reachable — use the wait
commands shown in the
[Get Started guide](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.2.0/microservices/time-series-analytics/docs/user-guide/get-started.md)
(`/docs` first, then `/health` after the first `POST /config`).

## 2. Pick a pattern

Read [`references/patterns.md`](./references/patterns.md) and match the
user's description to a row in its table (threshold, rate-of-change,
rolling z-score, or pretrained model). Confirm the specific parameters
(field name, thresholds, window size, model file) before writing code.

## 3. Write the UDF and tick script

Copy the two templates and fill in the pattern-specific `point()` body from
`references/patterns.md`:

```bash
mkdir -p udfs tick_scripts   # standalone: these won't exist yet
cp .github/skills/time-series-analytics-user/assets/udf_stream_template.py udfs/<name>.py
cp .github/skills/time-series-analytics-user/assets/tick_template.tick tick_scripts/<name>.tick
```

(Standalone/no-clone: fetch these two template files from GitHub raw the
same way as the compose files above, under
`.github/skills/time-series-analytics-user/assets/`.)

Full method contract and gotchas: [`references/udf-authoring.md`](./references/udf-authoring.md).
Tick script details: [`references/tickscript-basics.md`](./references/tickscript-basics.md).

## 4. Package and deploy

```bash
.github/skills/time-series-analytics-user/scripts/package_udf.sh <name> .
```

`package_udf.sh` validates file naming locally before tarring — read its
warnings if it fails.

For the `POST /udfs/package` upload and `POST /config` calls, follow the
exact request format and sequence from the
[Access Microservice API reference](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.2.0/microservices/time-series-analytics/docs/user-guide/how-to-access-api.md).
Full config shape and a troubleshooting table:
[`references/api-workflow.md`](./references/api-workflow.md).

When you deploy, **capture and print the real response bodies** from both
REST calls — quote them verbatim in your answer so the grader can verify.

## 5. Feed data and verify

Send test points using the `POST /input` request format from the
[Access Microservice API reference](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.2.0/microservices/time-series-analytics/docs/user-guide/how-to-access-api.md),
then tail the container log:

```bash
docker logs -f ia-time-series-analytics-microservice
```

`topic` must equal the `.measurement(...)` value in the tick script.
Anomalies your UDF flags (via `write_response`) show up in this log; for
Kapacitor-internal errors, `docker exec -it
ia-time-series-analytics-microservice bash` then `cat
/tmp/log/kapacitor/kapacitor.log | grep -i error`.

For grading, do not stop at "I checked logs" — print the exact evidence. A good
pattern is:

```bash
docker logs ia-time-series-analytics-microservice 2>&1 | grep -F "Flagged anomalous point"
docker logs ia-time-series-analytics-microservice 2>&1 | grep -F "Converted line protocol"
```

In your answer, quote:
- the exact flagged line for the anomalous point
- the exact received/input line for the non-anomalous point
- an explicit statement that no flagged line appeared for the non-anomalous
  point after that input

## 6. Optional: alerting

- **MQTT** — set `config.json`'s `alerts.mqtt`, chain
  `|alert()...mqtt('<broker_name>')` in the tick script. Native, automatic.
- **OPC UA** — set `config.json`'s `alerts.opcua`, then explicitly call
  `POST /opcua_alerts` (not automatic — see
  [`tickscript-basics.md`](./references/tickscript-basics.md#alerting-two-different-mechanisms-dont-conflate-them)
  for why).

For MQTT validation, **capture broker-side proof**, not just REST success or
UDF logs. Example:

```bash
docker exec <broker_container> sh -lc \
  "timeout 8 mosquitto_sub -h localhost -t '<topic>' -v"
```

Then print the exact subscribed output in your answer and state explicitly that
no additional message arrived for the non-triggering point.

## Stop / clean

```bash
docker compose down -v   # from docker/
```
