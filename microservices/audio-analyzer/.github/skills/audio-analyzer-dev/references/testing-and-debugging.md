<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Testing and Debugging Reference

Covers the two parallel test suites in this codebase, the Docker build
verification tests, runtime debug endpoints, and startup failure
diagnostics.

---

## Table of Contents

1. [Two Test Suites — Know Which One You're Running](#two-test-suites--know-which-one-youre-running)
2. [Suite A: Root-Level Lightweight Tests (`tests/*.py`)](#suite-a-root-level-lightweight-tests-testspy)
3. [Suite B: Tiered Functional Tests (`tests/functional/`)](#suite-b-tiered-functional-tests-testsfunctional)
4. [Tier-3 Docker Build Verification Suite](#tier-3-docker-build-verification-suite)
5. [Runtime Debug Endpoints](#runtime-debug-endpoints)
6. [Diagnosing Startup Failures](#diagnosing-startup-failures)

---

## Two Test Suites — Know Which One You're Running

This codebase has **two independently organized test suites** with
different conventions. Picking the wrong invocation silently runs zero
tests or the wrong subset — always confirm which suite a request is about
before suggesting a command.

| | Suite A — root-level | Suite B — tiered functional |
|---|---|---|
| Location | `tests/*.py` | `tests/functional/*.py`, `tests/functional/build/*.py` |
| Style | Plain `unittest.TestCase`, no custom markers | `pytest.mark.tier1`/`tier2`/`tier3` |
| Default `pytest` discovery | **Not** discovered by default (`pytest.ini` restricts `testpaths` to `tests/functional/build`) | Only `tests/functional/build/` is auto-discovered; `tests/functional/*.py` at the top level still needs an explicit path |
| Needs | No model weights or GPU (per the service's own get-started guide) | Tier-dependent — tier1 is CI-safe, tier2 needs `HF_TOKEN`, tier3 needs Docker/live server/real inference |

> [!IMPORTANT]
> `pytest.ini` sets `testpaths = tests/functional/build`. Running bare
> `pytest` or `pytest -m tier1` with **no path argument** only looks inside
> `tests/functional/build/` — it silently skips every test under `tests/`
> root and the rest of `tests/functional/`. Passing an explicit path (e.g.
> `pytest tests/ -v -m tier1`) overrides `testpaths` and scans recursively,
> which is why the commands below always include an explicit path.

---

## Suite A: Root-Level Lightweight Tests (`tests/*.py`)

Files: `test_api_hardening.py`, `test_pipeline_and_audio_util.py`,
`test_pyannote_diarizer.py`, `test_ov_pyannote_embedding_openvino.py`,
`test_speaker_identity.py`, `test_streaming_endpoints.py`,
`test_vss_endpoints.py`.

These use `unittest.TestCase` plus FastAPI's `TestClient` and are **not**
marked with `tier1`/`tier2`/`tier3` — do not add a `-m` filter when running
them, it will exclude everything.

```bash
pip install pytest httpx
pytest tests/test_streaming_endpoints.py tests/test_vss_endpoints.py -v
```

Covers: the SSE event sequence, the realtime WebSocket handshake and VAD
behavior, the VSS-compatible contract, API input-hardening (upload size,
extension, malformed requests), diarization/embedding math, and
speaker-identity store logic. Explicitly requires **no model weights or
GPU** — these are pure logic/contract tests with heavy dependencies mocked
inline per-file (not via the global stub mechanism Suite B uses).

Run the whole suite:
```bash
pytest tests/*.py -v
```

Run a single file:
```bash
pytest tests/test_api_hardening.py -v
```

---

## Suite B: Tiered Functional Tests (`tests/functional/`)

Files: `tests/functional/test_api_hardening.py`,
`tests/functional/test_speaker_identity.py`,
`tests/functional/build/test_build.py`,
`tests/functional/build/test_asr_component_diarization_startup.py`.

`tests/functional/conftest.py` stubs heavy ML libraries (`whisper`,
`whispercpp`, `torch`, `pyannote`, `openvino`, `openvino_genai`, `librosa`,
`soundfile`, `sounddevice`) into `sys.modules` **before** any test module
imports application code — this is what lets `tier1` tests import `main`,
`pipeline`, and `components` in a lightweight CI runner with no ML stack
installed. An already-installed real package always takes precedence
(`setdefault` is a no-op when the module exists).

```bash
pytest tests/functional -v -m tier1    # CI-safe, no model weights/Docker/GPU
pytest tests/functional -v -m tier2    # needs HF_TOKEN
pytest tests/functional -v -m tier3    # needs Docker daemon / full ML stack / live server
```

After a run, `conftest.py`'s `pytest_sessionfinish` hook writes a
human-readable CSV summary to `tests/functional/build/test_results.csv`
(one row per test: humanized description + `PASS`/`FAIL`/`SKIP`) — check
this file first when triaging a large batch of failures instead of
re-scrolling pytest's own console output.

---

## Tier-3 Docker Build Verification Suite

`tests/functional/build/test_build.py` runs **real Docker commands against
a live daemon** — no mocking, no text-parsing shortcuts. Use this when a
developer needs to validate a Dockerfile/Compose change without fully
deploying the service.

```bash
pytest tests/functional/build/test_build.py -m tier3 -v -s
```

What it actually validates:
- `docker compose build --no-cache` exits `0` (Dockerfile syntax, all
  `COPY`/`ADD` sources exist, `pip install -r requirements.txt` succeeds
  inside the image).
- The built image is present in the local Docker image store, with the
  image name read directly from `docker-compose.yml` (not hardcoded) so the
  test stays in sync with config changes.
- The documented local-only build path works: `REGISTRY=""` build (mirrors
  the no-registry-push workflow).
- `docker compose config` correctly resolves `ACCEL_MOUNT_PATH` into the
  fixed `/dev/accel/accel0` container target — both when the variable is set
  to a real host path and when it is unset (must fall back to `/dev/null`).

Every test in this file first checks Docker availability
(`docker info`) and calls `pytest.skip(...)` with a specific reason if the
daemon isn't reachable, rather than failing — a `SKIPPED` result here means
"no Docker daemon," not "the build is broken."

---

## Runtime Debug Endpoints

Two endpoints exist specifically for diagnosing a running deployment and
are **not** part of the OpenAI-compatible transcription contract — they are
undocumented in the published API reference but present in
`api/custom_endpoints.py` and safe to use for debugging:

### `GET /v1/model-info`

Returns the ASR configuration actually in effect for the running process —
useful when a deployment's behavior doesn't match what `config.yaml` on
disk appears to say (e.g. an env-var override changed it):

```bash
curl --noproxy '*' http://127.0.0.1:8010/v1/model-info
```

```json
{"model": "whisper-base", "provider": "openvino", "device": "CPU", "weight_format": null}
```

### `GET /v1/performance`

Returns the most recent ASR call's latency in milliseconds (a single
thread-safe `last_ms` value, not a rolling history):

```bash
curl --noproxy '*' http://127.0.0.1:8010/v1/performance
```

```json
{"latency": {"last_ms": 842.3}}
```

Use this to quickly confirm whether a perceived slowdown is real (e.g.
before escalating to GPU/NPU troubleshooting) rather than relying on
wall-clock timing from the client side, which also includes upload and
network time.

---

## Diagnosing Startup Failures

`tests/test_api_hardening.py`'s `StartupModelTests` documents the two
specific ways `main.startup_event()` can fail, both of which log a warning
containing **"ASR model is unavailable"** before re-raising:

| Failure point | What it means |
|---------------|----------------|
| `ensure_model` raises | The configured ASR model could not be downloaded/exported — check network access to Hugging Face and `models.tts`/`models.asr` config, and disk space under `models/` |
| `preload_models` raises | The model files exist but failed to load into the runtime — check the provider/device validation path (`utils/openvino_runtime_validation.py`) and GPU/NPU visibility before assuming the model asset itself is corrupt |

When triaging a container that exits immediately after startup, grep the
logs for this exact phrase first — it tells you whether the problem is
model acquisition or model loading before you go any further:

```bash
docker compose logs audio-analyzer 2>&1 | grep -i "ASR model is unavailable"
```
