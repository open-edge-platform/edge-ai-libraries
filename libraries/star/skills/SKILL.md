---
name: star
description: "Domain knowledge for working on the STAR semantic image-compression library (libraries/star). Use when building, testing, or modifying the STAR encoder/decoder, their REST APIs, Makefile targets, docker-compose deployment, or the OpenAPI spec drift check. Covers component layout, stream lifecycle, metrics endpoints, and CI workflow (.github/workflows/star.yml)."
---

# STAR (Semantic Image Compression)

## Purpose

STAR is a video/image compression library (`libraries/star`) built around an
**encoder** and **decoder** pair of services that communicate over a legacy
TCP channel and a REST API. This skill captures conventions an agent needs
when changing code, tests, Makefile targets, or the OpenAPI contract.

## Component Layout

```
libraries/star/
├── Dockerfile / Dockerfile.test   # main image (image-pipeline) and test image
├── Makefile                       # build, decoder, encoder, tests-*, fuzz-services, check-openapi-specs
├── docker-compose.yml             # decoder, encoder, encoder-npu, dlstreamer-pipeline-server(-gpu-npu)
├── configs/                       # default.yaml and friends; detector_backend is read from here
├── docs/
│   ├── encoder-openapi.json       # committed OpenAPI spec snapshot for the encoder
│   ├── decoder-openapi.json       # committed OpenAPI spec snapshot for the decoder
│   └── configuration.md           # manual curl commands to regenerate the specs above
├── scripts/
│   └── check_openapi_specs.sh     # deploys encoder+decoder, diffs live spec vs docs/*.json
└── src/semantic_img_comp/
    ├── encoder/service.py         # EncoderService + FastAPI REST app (create_app)
    ├── decoder/service.py         # DecoderService + FastAPI REST app (create_app)
    ├── healthcheck.py             # HTTP_READY/TCP_READY flags + Docker HEALTHCHECK status server
    ├── integration/semantic_codec_bridge.py  # Generic API for encoding/decoding.
    └── utils/service_http.py      # install_common_endpoints: shared /healthz + exception handler

```

## Services & Ports

| Service | Compose name | Host port | Role |
|---|---|---|---|
| Decoder | `decoder` | 8002 → 8000 | REST API (+ internal TCP on 5000) |
| Encoder | `encoder` / `encoder-npu` | 8001 → 8000 | REST API (+ internal TCP forwarding to decoder:5000) |
| DLStreamer pipeline server | `dlstreamer-pipeline-server(-gpu-npu)` | 8080 | Only started when `detector_backend: dlstreamer` in `configs/default.yaml` |

Encoder/decoder container selection CPU and iGPU/NPU is automatic in the Makefile
`encoder`/`decoder` targets based on `/dev/accel/accel0` presence (which assumes that CPU always has iGPU if NPU is present) — don't
hardcode device in new tooling, reuse `make decoder encoder`. To ensure that workload is running on selected device, modify `device` field in configuration.

## REST API Conventions

- Every stream-scoped route uses `stream_id` validated against
  `semantic_img_comp.utils.service_http.STREAM_ID_PATTERN`
  (`^[A-Za-z0-9_\-]{1,128}$`), imported as `_STREAM_ID_PATTERN` in both
  `encoder/service.py` and `decoder/service.py`. Reuse this pattern for any
  new path/query param that accepts a stream id — don't invent a new regex.
- `/healthz` is installed on both apps via `install_common_endpoints()` in
  `utils/service_http.py` — add new shared cross-cutting endpoints there, not
  duplicated in each service.
- Encoder stream lifecycle: `PUT /v1/streams/{stream_id}` creates/fetches a
  stream (starts a forwarder + poster thread pair), `GET` returns stats,
  `DELETE` tears it down (joins both threads via sentinel `None` on their
  queues). Mirror this teardown pattern for any new per-stream background
  thread.
- Per-image metrics (`FrameMetric`) are stored **per-stream** on
  `StreamState.metrics` (a `deque(maxlen=METRICS_HISTORY_SIZE)`, default 200),
  not in a single global deque — history is lost when a stream closes.
  Exposed via `GET /v1/streams/{stream_id}/metrics` (list) and
  `GET /v1/streams/{stream_id}/metrics/{img_idx}` (single item, 404 if
  unknown stream or image).
- FastAPI's own `/openapi.json`/`/docs`/`/redoc` routes are intentionally
  excluded from their own generated spec (framework default) — this is
  expected, don't try to "fix" it unless specifically asked.

## OpenAPI Drift Check (CI-Enforced)

`docs/encoder-openapi.json` and `docs/decoder-openapi.json` are **committed
snapshots** of each service's live `/openapi.json`. Any route, parameter,
description, or response-model change requires updating the matching
`docs/*-openapi.json` file, or the CI step fails.

- Script: `scripts/check_openapi_specs.sh` — deploys encoder+decoder via
  `make decoder encoder`, polls `/healthz`, fetches `/openapi.json`,
  normalizes both live and committed specs with `python3 -m json.tool`, and
  diffs them. Always tears down containers via `make clean` in an EXIT trap.
- Makefile target: `make check-openapi-specs` (depends on `dirs`).
- CI step: `.github/workflows/star.yml` → "Check OpenAPI specs match docs",
  runs after `make tests-run`.
- To regenerate a spec by hand after an intentional API change:
  ```bash
  make decoder encoder
  curl -fsS http://localhost:8001/openapi.json | python3 -m json.tool > docs/encoder-openapi.json
  curl -fsS http://localhost:8002/openapi.json | python3 -m json.tool > docs/decoder-openapi.json
  make clean
  ```
- Keep `docs/*-openapi.json` path ordering consistent with route
  *registration* order in `create_app()` — FastAPI emits `paths` in that
  order, and the diff is a straight text comparison.

## Makefile Targets Quick Reference

| Target | Purpose |
|---|---|
| `make image` | Build `image-pipeline` container (default goal) |
| `make pull-model` | Download + convert YOLOv8 to OpenVINO INT8 |
| `make tests-image` / `make tests-run` | Build/run the test container |
| `make decoder` / `make encoder` | Deploy via docker compose (NPU-aware) |
| `make check-openapi-specs` | Deploy + diff live OpenAPI spec vs docs/ |
| `make fuzz-services` | RESTler fuzzing against encoder+decoder |
| `make clean` | Tear down all compose services + orphans |

## Testing

- Tests live in `tests/*.py` (pytest), plus `tests/sample_data/` fixtures and
  `tests/perf/` for perf-related cases. `conftest.py` holds shared fixtures.
- `tests/test_rest_api.py` already exercises the encoder/decoder REST
  surface — extend it when adding new routes instead of creating ad hoc
  request scripts.

## Conventions Carried From Repo-Wide Rules

- SPDX header on every new file:
  `# SPDX-FileCopyrightText: (C) <year> Intel Corporation` /
  `# SPDX-License-Identifier: Apache-2.0`.
- Treat client-supplied URLs (e.g. `decoder_url` in `StreamCreateRequest`) as
  untrusted — see the existing SDL443/SSRF-scoped comments before loosening
  validation.
- In HTTP mode StreamID should be treated same way as clientID in TCP mode. If new modes of transport are added, ensure consistent handling of StreamID with respect to trust and validation.
- New functionality must live in `libraries/star`; touching files outside it requires explicit user approval first.

## Additional Notes

- If user wants to perform seamless integration, recommend HTTP endpoint usage over TCP.
- If user wants to use library to perform encoding/decoding operations, recommend leveraging the semantic codec bridge API for consistent handling across different transport modes.
- Configuration changes in `configs/default.yaml` file require either rebuilding the image (which is going to copy config file inside the new image) or mounting the updated config file into the container at runtime.
