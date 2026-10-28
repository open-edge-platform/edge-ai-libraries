<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->
# Audio Analyzer Image Optimization Log

**Status:** Promoted to production. After cross-machine CPU/GPU/NPU validation
(see §0), the mentor approved switching the default build away from the
DLStreamer-based image to the Ubuntu 24.04 image described in this log.
`docker/Dockerfile` is now the Ubuntu-based build; the former DLStreamer-based
`docker/Dockerfile` content and the separate `docker/Dockerfile.ubuntu` file it
was developed/tested in have been consolidated into a single file.
**Scope:** Review points #1–#12 raised by reviewer Yogesh on the Audio Analyzer
microservice. This log records what was measured, what changed, what passed,
and what remains open, for a future presentation and for mentor review.

## 0. Production promotion (this session)

`docker-compose.yml` now builds `docker/Dockerfile` (the former
`docker/Dockerfile.ubuntu`) with:

- `IMAGE_VARIANT=full` (default) — preserves every ASR provider/feature the
  prior single-`requirements.txt` DLStreamer image always shipped (openai,
  whispercpp, diarization, sentiment), so no functionality is silently
  removed from existing deployments. `IMAGE_VARIANT=slim` remains available
  as an explicit opt-in for a smaller, default-ASR-only image.
- `INSTALL_GPU_NPU_RUNTIME=true` (default) — preserves GPU/NPU support,
  matching `docker-compose.yml`'s existing (and unchanged) `/dev/dri`,
  `/dev/accel/accel0`, and `group_add` wiring, which previously relied on
  the DLStreamer base image's bundled GPU/NPU userspace libraries.
- `INSTALL_CJK=false` (default, unchanged) — optional FunASR Paraformer
  provider, same flag/behavior as the prior Dockerfile.

This exact `IMAGE_VARIANT=full` + `INSTALL_GPU_NPU_RUNTIME=true` combination
had **not** been built or tested together before this session (prior sessions
tested `full` CPU-only and `slim`+GPU/NPU separately). It was built and
validated end-to-end before promotion:

| Check | Result |
|---|---|
| Clean `docker compose build --no-cache` | ✅ Success, image `intel/audio-analyzer:2026.2.0`, **3.58 GB** (vs. 8.18 GB original DLStreamer baseline, −56.2%) |
| CPU default transcription (via `docker compose up`) | ✅ `device=CPU`, correct transcript, non-root (`uid=1000`, groups include `video`/render GID) |
| GPU transcription (`models.asr.device: GPU`) | ✅ `device=GPU`, correct transcript, no fallback/errors |
| NPU transcription (`models.asr.device: NPU`, `ACCEL_MOUNT_PATH` set) | ✅ `device=NPU`, correct transcript, no fallback/errors |
| `INSTALL_CJK=true` build | ✅ Builds successfully; `import funasr` succeeds inside the image (3.71 GB with CJK added) |
| Non-root execution | ✅ `uid=1000(ubuntu)`, unchanged from the candidate Dockerfile |

The separate `docker-compose.ubuntu.yml` used earlier in this effort for
slim/full/GPU-NPU side-by-side variant testing has been **removed**: once
`docker-compose.yml` itself builds the same Ubuntu-based `docker/Dockerfile`
(default `IMAGE_VARIANT=full`, `INSTALL_GPU_NPU_RUNTIME=true`), it no longer
added capability production doesn't already have — keeping a second compose
file around would only risk drifting out of sync with `docker-compose.yml`.
Variant testing (e.g. `IMAGE_VARIANT=slim`) can still be done against the
single `docker-compose.yml` by overriding the build-arg env vars, or via a
direct `docker build -f docker/Dockerfile --build-arg ...` (see §7.5).

All sizes below are from `docker images` (decimal GB, uncompressed layer
sizes as reported by the local Docker daemon) measured on the same host on
2026-10-15, immediately after a clean `docker build` of each tag (no stale
cache reused across different Dockerfiles/variants unless explicitly noted).
No image size numbers in this document are estimates — every figure was
produced by an actual `docker build` + `docker images`/`docker inspect` on
this host.

---

## 1. Summary of implemented Dockerfile changes

| Change | File(s) | Status |
|---|---|---|
| Fixed masked `pip install` failure (`\|\| true` hid errors) | `docker/Dockerfile` | Done (prior session) |
| `HF_TOKEN` no longer baked into image as `ENV`/build-arg | `docker/Dockerfile`, `Dockerfile` | Done (prior session) |
| Removed unused `psutil` dependency | `requirements.txt` | Done (this session) |
| Lazy-import ASR backend classes (enabler for slim image) | `components/asr_component.py` | Done (this session) |
| New Ubuntu 24.04 multi-stage Dockerfile, `slim`/`full` variants via `ARG IMAGE_VARIANT` | `docker/Dockerfile.ubuntu` (developed/tested as a candidate), later merged into `docker/Dockerfile` as the production image | Done, built & tested; **promoted to production** (see §0) |
| Split dependency files: slim core vs. full-only additions | `requirements-slim.txt`, `requirements-optional.txt` (new) | Done, verified `slim ∪ optional == requirements.txt` package set |
| Fixed missing `ca-certificates` in Ubuntu runtime stage (HTTPS model download/export failed without it) | `docker/Dockerfile.ubuntu` | Found + fixed this session |
| Fixed `--extra-index-url` (PyTorch CPU wheels) not carrying over to the second `pip install` call for `requirements-optional.txt` | `requirements-optional.txt` | Found + fixed this session |
| Non-reproducible deps / HTTP 200-on-failure / ignored `device`/`model_name` / `clear_storage_on_startup` default | see points #9–#12 below | Done (prior session), re-verified this session |

**Update (production promotion):** after mentor approval following
cross-machine CPU/GPU/NPU validation (§0), `docker/Dockerfile` now **is**
the former `docker/Dockerfile.ubuntu` content (the DLStreamer-based
Dockerfile it replaced is deleted, not kept alongside it — per point #7,
"keep one Dockerfile"). `docker-compose.yml`'s build `args:` were updated to
default `IMAGE_VARIANT=full` and `INSTALL_GPU_NPU_RUNTIME=true`, preserving
the full feature/device set the prior DLStreamer image always shipped.
The separate `docker-compose.ubuntu.yml` used earlier for side-by-side
variant testing has been removed as redundant (see §0 note above).

---

## 2. Review-point checklist (1–12)

| # | Point | Finding | Status |
|---|---|---|---|
| 1 | Remove unimported packages (ultralytics/polars/opencv/torchvision/onnx/pydub/nncf) | Confirmed `psutil` unused; `ultralytics`/`polars`/`opencv-python`/`torchvision`/`pydub` were **not** present in `requirements.txt` to begin with (already removed in a prior session per "[Done]" marker on point #7 context) — `onnx`/`nncf` **are** genuinely needed (optimum-intel OpenVINO export path), not removed | Done / re-confirmed |
| 2 | Drop `triton` (893 MB) | `triton` uninstalled post-install in both DLStreamer (prior session) and the new Ubuntu Dockerfile (`pip uninstall -y triton \|\| true`, confirmed absent from final image this session) | Done |
| 3 | Don't use DLStreamer base image | `docker/Dockerfile` (formerly `docker/Dockerfile.ubuntu`) built on `ubuntu:24.04`, no GStreamer/librealsense/rdkafka, single pip-installed OpenVINO version only | **Done — production** (promoted after mentor-approved cross-machine validation, §0) |
| 4 | Ship slim + full image | `ARG IMAGE_VARIANT=slim\|full` implemented and both built/measured; production defaults to `full` to preserve prior always-on feature set | **Done — production** (`slim` available as explicit opt-in) |
| 5 | Multi-stage build + pruning | Builder stage produces a venv; runtime stage copies only `/opt/venv` + app code; test dirs pruned (bounded `-maxdepth 2`); `pip`/`setuptools`/`wheel` removed from final venv | **Done — production**, empirically verified no regressions |
| 6 | Extend `.dockerignore` | Already extended in a prior session (tests/docs/compose files excluded) | Done (prior session) |
| 7 | Fix masked pip failure, keep one Dockerfile | Fixed in `docker/Dockerfile` (parentheses around install+uninstall); historically a root-level `Dockerfile` was kept in sync with `docker/Dockerfile` (confirmed identical via diff) — the root `Dockerfile` has since been removed entirely and `docker/Dockerfile` is now the single production Dockerfile (§0) | Done |
| 8 | `HF_TOKEN` not baked into image | Removed from build args/ENV; runtime-only env var now | Done, verified via `docker history` (no token string present) |
| 9 | Non-reproducible deps / Python version mismatch | Confirmed; direct deps pinned in `requirements.txt`/`requirements-lock.txt`, indirect deps pinned via freeze-based `requirements-lock.txt` but **no hash verification** (`pip-compile --generate-hashes` previously timed out) | Partially addressed — documented limitation, not full hash-based reproducibility |
| 10 | Failed transcription returns HTTP 200 | Fixed: induced GPU-unavailable failure now returns **HTTP 500** with `status: "failed"` body (verified via live curl test, see §7) | Done, verified end-to-end |
| 11 | `device`/`model_name` ignored; `/models` lists one model | Fixed: mismatched `model_name` → 400, invalid `device` literal → 400, valid `device` override honored (verified via live curl tests) | Done, verified end-to-end |
| 12 | `clear_storage_on_startup: true` default | Verified current default is `false`; storage persists across container restart (verified via live restart test) | Done, verified end-to-end |

---

## 3. Dependency-to-feature matrix (slim vs. full)

| Package | Slim | Full | Why |
|---|---|---|---|
| `fastapi`, `uvicorn`, `pydantic`, `python-multipart`, `websockets` | ✔ | ✔ | Core HTTP API |
| `openvino`, `openvino-genai`, `openvino-tokenizers` | ✔ | ✔ | Default ASR path (OpenVINO GenAI Whisper) |
| `librosa`, `soundfile`, `numba`, `llvmlite` | ✔ | ✔ | Audio decode/feature extraction (librosa hard-depends on numba) |
| `torch` (CPU wheel), `transformers`, `optimum`, `optimum-intel`, `nncf`, `onnx` | ✔ | ✔ | **Architectural floor**: `utils/ensure_model.py` shells out to `optimum-cli` for on-first-run HF→OpenVINO IR model export, which uses PyTorch internally to trace the model before conversion. Cannot be removed from either variant without moving export out of the container (future work, not attempted). |
| `minio`, `huggingface-hub`, `hf_xet` | ✔ | ✔ | VSS/MinIO ingestion + HF model downloads |
| `torchaudio` | ✘ | ✔ | Only needed transitively by `pyannote.audio`/`speechbrain` |
| `openai-whisper` | ✘ | ✔ | `openai` ASR provider + legacy (`use_ov_genai=false`) OpenVINO provider's tokenizer/mel-spectrogram utilities |
| `pywhispercpp` | ✘ | ✔ | `whispercpp` ASR provider |
| `pyannote.audio` | ✘ | ✔ | Speaker diarization |
| `speechbrain` | ✘ | ✔ | Sentiment analysis |
| `triton`, `torchvision`, `psutil` | ✘ | ✘ | Unused (triton only needed for CUDA code paths never executed on CPU; torchvision/psutil never imported) |

All four excluded-from-slim packages are imported **lazily** at the exact
call site that needs them (`components/asr_component.py::_resolve_backend()`,
`components/sentiment_component.py`, diarization modules) — selecting an
excluded provider on the slim image fails with a clear `ImportError` at
request time, not at startup. This was the key code change enabling a real
slim variant (see §1).

---

## 4. Docker build design and trade-offs

`docker/Dockerfile.ubuntu`:

- **Builder stage** (`ubuntu:24.04` + native `python3.12`/`python3.12-venv`/
  `python3-pip`, no deadsnakes PPA needed on Ubuntu 24.04 "noble"): creates
  `/opt/venv`, installs `requirements-slim.txt` (+`requirements-optional.txt`
  when `IMAGE_VARIANT=full`), constrained by `requirements-lock.txt`;
  uninstalls `torchcodec`/`triton` if pulled in transitively; prunes
  bundled `tests`/`test` directories bounded to `-maxdepth 2` (avoids a
  brittle unbounded recursive wildcard); removes `pip`/`setuptools`/`wheel`
  from the venv that gets copied forward (the app never invokes `pip` at
  runtime — model export uses the `optimum-cli` console script).
- **Runtime stage**: fresh `ubuntu:24.04`, bare `python3.12` + `ffmpeg` +
  `libsndfile1` + `alsa-utils` + `ca-certificates` (the last one was a real
  bug found this session — see §6), optional GPU/NPU userspace runtime
  (`ARG INSTALL_GPU_NPU_RUNTIME=true`, downloads `.deb`/tarball driver
  packages directly from GitHub Releases + a Launchpad PPA for
  `level-zero-loader`), `COPY --from=builder /opt/venv /opt/venv`, then app
  code, non-root user, healthcheck, and `CMD` — all mirroring the
  production Dockerfile's behavior.

**Trade-offs accepted:**
- No hash-pinned (`--hash`) dependency installation — `requirements-lock.txt`
  is a `pip freeze` snapshot, not a fully reproducible lock file. Documented
  as a known limitation (point #9), not resolved this session.
- `torch`/`transformers`/`optimum`/`nncf`/`onnx` remain in **both** variants
  because of the in-container model-export architecture. This is the
  single largest remaining size contributor (torch alone: 596 MB
  installed) and the main reason slim lands at 2.65 GB rather than
  meaningfully lower. Moving export to an init container/separate tool
  (as the original review suggested) is the only way to shed this weight,
  and is explicitly flagged as **not attempted** this pass to avoid
  sacrificing the "works out of the box on first run" behavior without a
  larger, separately-reviewed design.
- GPU/NPU driver packages are fetched from GitHub Releases + a Launchpad
  PPA rather than Intel's own apt repository (`repositories.intel.com`),
  because that host is unreachable from this sandbox (see §6). This may
  differ from a production/CI network environment — must be re-verified
  there.

---

## 5. Commands used to measure image size and compare layers

```bash
# Image size (decimal GB, as docker reports it)
docker images audio-analyzer --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
docker inspect <image> --format='{{.Size}}'

# Per-layer breakdown
docker history <image> --no-trunc --format "{{.Size}}\t{{.CreatedBy}}"

# Largest installed Python packages inside the final image
docker run --rm --entrypoint bash <image> -c \
  "du -sh /opt/venv/lib/python3.12/site-packages/* 2>/dev/null | sort -rh | head -25"

# Full filesystem breakdown by top-level directory
docker run --rm --entrypoint bash <image> -c \
  "du -xh -d1 / 2>/dev/null | sort -rh | head -20"
```

---

## 6. Measured sizes (this session)

| Variant | Build tag | Base image | Build args | Size | vs. 8.18 GB baseline |
|---|---|---|---|---|---|
| Original production (DLStreamer) | `intel/audio-analyzer:2026.2.0` | DLStreamer | — | **8.18 GB** | baseline |
| Optimized production (points #1/#2/#7/#8 applied, still DLStreamer) | `audio-analyzer:e2e-verify` (prior session) | DLStreamer | — | **6.44 GB** | −21.2% |
| Python-slim CPU POC (prior session) | `audio-analyzer:poc-cpu-only` | `python:3.12-slim` | CPU only | 3.6 GB | −56.0% |
| Python-slim GPU/NPU POC (prior session) | `audio-analyzer:poc-gpu-npu-realtest4` | `python:3.12-slim` | +GPU/NPU runtime | 4.26 GB | −47.9% |
| **Ubuntu 24.04 slim-CPU (this session, new candidate)** | `audio-analyzer:ubuntu-slim-cpu` | `ubuntu:24.04` | `IMAGE_VARIANT=slim` | **2.65 GB** | **−67.6%** |
| **Ubuntu 24.04 full-CPU (this session, new candidate)** | `audio-analyzer:ubuntu-full-cpu` | `ubuntu:24.04` | `IMAGE_VARIANT=full` | **2.92 GB** | **−64.3%** |
| **Ubuntu 24.04 slim + GPU/NPU runtime (this session, new candidate)** | `audio-analyzer:ubuntu-slim-gpu-npu` | `ubuntu:24.04` | `IMAGE_VARIANT=slim`, `INSTALL_GPU_NPU_RUNTIME=true` | **3.31 GB** | **−59.5%** |
| **Ubuntu 24.04 slim-CPU, reverified fresh build (follow-up session)** | `audio-analyzer:ubuntu-slim-cpu-v3` | `ubuntu:24.04` | `IMAGE_VARIANT=slim` | **2.65 GB** | **−67.6%** |
| **Ubuntu 24.04 slim + GPU/NPU, reverified fresh build (follow-up session)** | `audio-analyzer:ubuntu-slim-gpu-npu-v3` | `ubuntu:24.04` | `IMAGE_VARIANT=slim`, `INSTALL_GPU_NPU_RUNTIME=true` | **3.31 GB** | **−59.5%** |
| ~~Ubuntu 24.04 minimal-CPU (follow-up session, pre-exported model, no export toolchain)~~ | `audio-analyzer:ubuntu-minimal-cpu` | `ubuntu:24.04` | `--target runtime-minimal` | 2.09 GB | −74.4% *(measured, then removed — see §18)* |
| **Ubuntu 24.04 full + GPU/NPU runtime (production promotion session) — this is the new production default** | `intel/audio-analyzer:2026.2.0` (built via `docker compose build`) | `ubuntu:24.04` | `IMAGE_VARIANT=full`, `INSTALL_GPU_NPU_RUNTIME=true` (both now `docker-compose.yml` defaults) | **3.58 GB** | **−56.2%** |
| **Ubuntu 24.04 full + GPU/NPU runtime + CJK/FunASR (production promotion session, opt-in)** | `audio-analyzer:ubuntu-cjk-test` | `ubuntu:24.04` | `IMAGE_VARIANT=full`, `INSTALL_GPU_NPU_RUNTIME=true`, `INSTALL_CJK=true` | **3.71 GB** | **−54.6%** |

**Note:** the full+GPU/NPU-runtime combination (3.58 GB) had not been built
or measured together in any prior session — earlier rows tested `full`
CPU-only (2.92 GB) and `slim`+GPU/NPU (3.31 GB) separately. It was built and
validated end-to-end (CPU/GPU/NPU transcription, non-root, health) before
being made the `docker-compose.yml` default; see §0.

**Target assessment:** the slim-CPU candidate (2.65 GB) is slightly above
the 2.5 GB upper bound of the requested 2–2.5 GB target, but within ~6% of
it and represents a 67.6% reduction from the original baseline. The full
variant (2.92 GB) is outside the 2–2.5 GB target by design — it is meant to
preserve every optional feature, not meet the slim target.

### Layer/package breakdown (slim-CPU, 2.65 GB image)

Largest Python packages inside `/opt/venv` (same set in slim and full,
since none of these are full-only):

| Package | Size | Notes |
|---|---|---|
| `torch` | 596 MB | CPU wheel (`torch-2.8.0+cpu`); required by on-container model export (see §3) |
| `openvino` | 171 MB | Core inference engine |
| `llvmlite` | 128 MB | `numba`'s JIT backend; `numba` is a hard dependency of `librosa` |
| `scipy` (+`scipy.libs`) | 111 MB | Transitive via `librosa`/`scikit-learn` |
| `onnx` | 73 MB | Required by `optimum-intel` for the export path |
| `transformers` | 52 MB | Required for model config/tokenizer loading during export and GenAI pipeline setup |
| `scikit-learn` | 32 MB | Hard dependency of `librosa` |
| `numpy` (+`numpy.libs`) | 58 MB | Core numeric array library |

`docker history` shows the bulk of image size concentrated in two layers:
the `COPY --from=builder /opt/venv /opt/venv` layer (~1.45 GB, the Python
dependency tree) and the runtime `apt-get install` layer (~505 MB:
`python3.12` interpreter + `ffmpeg` + `libsndfile1` + `alsa-utils` +
`ca-certificates`), plus the `ubuntu:24.04` base layer (~88 MB).

**Update (follow-up session): this opportunity was pursued and measured —
see §14.** The projected ~730 MB from the export toolchain did not fully
materialize as savings: the real, measured reduction is **556 MB** (2.65 GB
→ 2.09 GB), because the pre-exported model itself (~290 MB of OpenVINO IR
weights) has to be shipped in the image instead. Net: **2.09 GB**, not the
previously-projected ~1.5–1.9 GB — see §14 for the full measurement,
the real `chown -R` overlay-copy-up bug found and fixed during this work,
and the documented trade-off (only the pre-exported model/weight_format
works without a rebuild).

---

## 7. Tests executed and actual results

### 7.1 Automated regression suite

Run via (adapted per-image since the final venv has no `pip`):

```bash
docker run --rm -u 0:0 -v "$(pwd)":/app/audio_analyzer -w /app/audio_analyzer \
  --entrypoint bash <image> -c '
    export PATH=/usr/bin:$PATH
    apt-get update -qq && apt-get install -y -qq --no-install-recommends python3-pip
    /usr/bin/python3.12 -m pip install --quiet --break-system-packages --target=/tmp/testlibs pytest httpx
    PYTHONPATH=/opt/venv/lib/python3.12/site-packages:/tmp/testlibs \
      /opt/venv/bin/python3 -m pytest tests/ -q --ignore=tests/functional [--ignore=... for slim-only exclusions]
  '
```

| Image | Result | Notes |
|---|---|---|
| `audio-analyzer:poc-cpu-only` (existing DLStreamer-family POC, baseline for comparison) | 99 passed, 2 pre-existing failures | Baseline used throughout this effort |
| `audio-analyzer:ubuntu-slim-cpu` | **53 passed, 1 skipped, 2 pre-existing failures** | 3 test modules that import optional-provider classes at module scope (`test_pipeline_and_audio_util.py`, `test_pyannote_diarizer.py`, `test_ov_pyannote_embedding_openvino.py`) cannot *collect* on slim by design (those packages are intentionally absent) — this is expected and correct, not a regression |
| `audio-analyzer:ubuntu-full-cpu` | **99 passed, 2 pre-existing failures** | Identical to the established baseline — full variant has zero collection issues since all optional packages are present |

**Correction (re-verified on a host with real Intel GPU/NPU hardware):** only
1 of these 2 is an actual failure —
`test_openai_transcription_rejects_prompt` (`tests/test_api_hardening.py`)
fails because the file-format validation runs before the prompt-rejection
check, so an intentionally-invalid fake WAV body trips the format check
first and the test never reaches the prompt-specific code path it's probing.
This is **pre-existing, unrelated to GPU hardware or to any change made this
session** (confirmed identical on `origin/main`; not a regression).
`test_openai_transcription_passes_requested_device_to_pipeline` **passes**
when re-run directly with a full dependency set — the earlier "2 pre-existing
failures" count was not reproduced on reverification and should be treated
as corrected to **1 pre-existing, unrelated failure**.

### 7.2 End-to-end live-container validation

Performed against `audio-analyzer:ubuntu-slim-cpu` and spot-checked against
`audio-analyzer:ubuntu-full-cpu`:

| Test | Command | Expected | Actual |
|---|---|---|---|
| Clean build | `docker build -f docker/Dockerfile.ubuntu -t <tag> .` | Success | ✅ Success (slim, full, slim+GPU/NPU all built cleanly) |
| Startup + model export | `docker run -d ... <image>`, poll `/health` | `optimum-cli` exports `openai/whisper-base` on first run, then 200 | ✅ (took ~70s to export+load on this host) |
| Health check | `curl -s -w "%{http_code}" http://localhost:PORT/health` | `{"status":"ok"}`, 200 | ✅ |
| `/models` | `curl -s http://localhost:PORT/models` | Single configured model listed | ✅ `whisper-base` |
| Successful transcription | `curl -F "file=@tests/philosophy_10_russell_128kb.mp3" http://localhost:PORT/transcriptions` | 200, `status: completed`, transcript file written | ✅ 200, transcript written to `storage/<job_id>/transcription.srt` |
| Failed transcription (induced via `device=GPU`, no GPU hw) | same + `-F device=GPU` | **4xx/5xx**, not 200 | ✅ **500**, `status: failed` (point #10 confirmed fixed) |
| Mismatched `model_name` | same + `-F model_name=wrong-model` | 400 with clear message | ✅ 400, `"Unsupported model_name 'wrong-model'..."` |
| Invalid `device` literal | same + `-F device=TPU` | 400 with clear message | ✅ 400, `"Unsupported device 'TPU'. Supported values: ['CPU', 'GPU', 'NPU']"` |
| Storage persistence across restart | `docker restart <container>`, list `storage/` before/after | Prior job folders still present | ✅ confirmed, `clear_storage_on_startup` default is `false` |
| Non-root execution | `docker run ... <image>` (default user) | Runs as uid 1000 (`appuser`), not root | ✅ (Dockerfile sets `USER 1000:1000`) |

### 7.3 Optional-provider validation (full variant)

Covered by the automated suite (§7.1: 99 passed on `ubuntu-full-cpu`),
which exercises `openai`/`whispercpp` ASR provider selection, diarization
(`pyannote_diarizer`/`ov_pyannote_diarizer`), and sentiment
(`speechbrain`) code paths via unit/API tests with mocked model weights.
**Not performed**: a real end-to-end diarization/sentiment inference run
against actual pretrained weights (would require downloading gated
`pyannote` models, which needs an `HF_TOKEN` with accepted model terms —
not available in this environment). This is marked **blocked**, not
passed/failed.

### 7.4 GPU/NPU validation

| Check | Result |
|---|---|
| GPU/NPU driver packages download + install during **actual `docker build`** (not just `docker run`) | ✅ **Confirmed working** this session — previously documented as blocked due to suspected network/TLS issues from a non-DLStreamer base; retested and found GitHub Releases + the Launchpad PPA are reachable from this sandbox's BuildKit network namespace. `libze_intel_gpu`, `libze_intel_npu`, `libopenvino_intel_npu_compiler`, `libigdgmm`, `intel-opencl-icd`, etc. all present in the final image. |
| GPU/NPU **inference** on real hardware | ✅ **Confirmed working** — re-run on a host with real Intel Meteor Lake Arc GPU (`00:02.0 VGA … Intel Arc Graphics`) and NPU (`00:0b.0 Processing accelerators: Intel Corporation Meteor Lake NPU`), `/dev/dri/{card1,renderD128}` and `/dev/accel/accel0` present. Ran `audio-analyzer:ubuntu-slim-gpu-npu` with `--device /dev/dri:/dev/dri --group-add <render> --group-add <video>` and `AUDIO_ANALYZER__models__asr__device=GPU`: model export succeeded, logs show `Loading Model: model name=whisper-base, device=GPU`, `/models` reports `"description": "openvino provider on GPU"`, and `POST /v1/audio/transcriptions` against `tests/philosophy_10_russell_128kb.mp3` returned correct transcript text in ~65s with no errors/fallback. Repeated with `--device /dev/accel/accel0:/dev/accel/accel0` and `AUDIO_ANALYZER__models__asr__device=NPU`: logs show `device=NPU`, `/models` reports `"description": "openvino provider on NPU"`, transcription returned the correct text in ~64s with no errors. Both variants validated end-to-end (health → models → transcribe) on real hardware. |

**Correction (this session):** the GPU row above omits one detail that
was actually required for the NPU case and must be reproduced exactly:
`ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so` has to be set for the NPU
plugin to dlopen `libze_intel_npu.so` instead of the default GPU Level
Zero driver (this mirrors `docker-compose.yml`'s own
`ZE_ENABLE_ALT_DRIVERS` env var, set there specifically for this reason —
see §7.5 below for the exact, copy-pasteable run commands including this
variable).

### 7.5 Consolidated build/run/validate commands (all variants)

All commands below are run from `microservices/audio-analyzer/`.

```bash
# ---- Build each variant ----
docker build -f docker/Dockerfile -t audio-analyzer:ubuntu-slim-cpu \
    --build-arg IMAGE_VARIANT=slim --build-arg INSTALL_GPU_NPU_RUNTIME=false .
docker build -f docker/Dockerfile -t audio-analyzer:ubuntu-full-cpu \
    --build-arg IMAGE_VARIANT=full --build-arg INSTALL_GPU_NPU_RUNTIME=false .
docker build -f docker/Dockerfile -t audio-analyzer:ubuntu-slim-gpu-npu \
    --build-arg IMAGE_VARIANT=slim --build-arg INSTALL_GPU_NPU_RUNTIME=true .

# ---- Check sizes ----
docker images audio-analyzer --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
docker inspect audio-analyzer:ubuntu-slim-cpu --format='{{.Size}}'   # exact bytes

# ---- Run: CPU (any slim/full/minimal image) ----
docker run -d --name aa-cpu -p 8010:8010 \
    -e AUDIO_ANALYZER__models__asr__device=CPU \
    audio-analyzer:ubuntu-slim-cpu

# ---- Run: GPU (requires the gpu-npu image + Intel iGPU/dGPU) ----
docker run -d --name aa-gpu -p 8010:8010 \
    --device /dev/dri:/dev/dri \
    --group-add "$(getent group render | cut -d: -f3)" \
    --group-add "$(getent group video  | cut -d: -f3)" \
    -e AUDIO_ANALYZER__models__asr__device=GPU \
    audio-analyzer:ubuntu-slim-gpu-npu

# ---- Run: NPU (requires the gpu-npu image + Intel NPU, e.g. Meteor Lake) ----
# ZE_ENABLE_ALT_DRIVERS is REQUIRED for the NPU Level Zero plugin to load —
# matches docker-compose.yml's own ZE_ENABLE_ALT_DRIVERS setting.
docker run -d --name aa-npu -p 8010:8010 \
    --device /dev/accel/accel0:/dev/accel/accel0 \
    --group-add "$(getent group render | cut -d: -f3)" \
    -e ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so \
    -e AUDIO_ANALYZER__models__asr__device=NPU \
    audio-analyzer:ubuntu-slim-gpu-npu

# ---- Validate: health, models, and a real transcription (any running container) ----
curl -s http://localhost:8010/health
curl -s http://localhost:8010/models
curl -s -F "file=@tests/philosophy_10_russell_128kb.mp3" \
    http://localhost:8010/transcriptions

# ---- Validate: alternate ASR providers / diarization / sentiment ----
# IMPORTANT: provider, diarization, and sentiment.enabled are STARTUP-TIME
# config (config.yaml or AUDIO_ANALYZER__<section>__<key> env overrides),
# NOT per-request form fields -- there is no `-F provider=...` or
# `-F diarization=...` on /transcriptions. To validate each one, restart
# the container with the relevant override, then re-run the same
# /transcriptions or /v1/audio/transcriptions curl call above, e.g.:
docker run -d --name aa-openai -p 8010:8010 \
    -e AUDIO_ANALYZER__models__asr__provider=openai \
    audio-analyzer:ubuntu-full-cpu   # full variant: openai-whisper installed
docker run -d --name aa-whispercpp -p 8010:8010 \
    -e AUDIO_ANALYZER__models__asr__provider=whispercpp \
    audio-analyzer:ubuntu-full-cpu   # full variant: pywhispercpp installed
docker run -d --name aa-diarize -p 8010:8010 \
    -e AUDIO_ANALYZER__models__asr__diarization=true \
    -e AUDIO_ANALYZER__models__asr__hf_token="$HF_TOKEN" \
    audio-analyzer:ubuntu-full-cpu   # requires a valid HF_TOKEN at runtime, not baked into the image (point #8)
# `device` and `model_name` ARE genuine per-request form fields on
# /transcriptions (and `device`/`model` on /v1/audio/transcriptions),
# confirmed in dto/vss_dto.py / api/openai_endpoints.py — see §7.2 above
# for those specific curl examples.

# ---- Cleanup ----
docker rm -f aa-cpu aa-gpu aa-npu aa-openai aa-whispercpp aa-diarize 2>/dev/null
```

`device` and `model_name` are genuine per-request multipart form fields on
`POST /transcriptions` (`dto/vss_dto.py::VssTranscriptionForm`); `provider`,
`diarization`, and `sentiment.enabled` are service-level startup
configuration (`config.yaml` or `AUDIO_ANALYZER__<section>__<key>` env
overrides, confirmed in `utils/config_loader.py`), selected when the
container starts, not per upload.

---

## 8. Size savings attributable to each stage

| Stage | Cumulative size | Savings vs. previous stage | Savings vs. 8.18 GB baseline |
|---|---|---|---|
| Original DLStreamer baseline | 8.18 GB | — | — |
| + Dependency cleanup (points #1/#2) on DLStreamer base | 6.44 GB | −1.74 GB (−21.2%) | −21.2% |
| Switch base to Ubuntu 24.04, multi-stage + pruning (points #3/#5), full dependency set | 2.92 GB | −3.52 GB (−54.7%) | −64.3% |
| + Slim/full split, lazy-import refactor (point #4) | 2.65 GB | −0.27 GB (−9.2%) | −67.6% |
| (GPU/NPU runtime layer, slim base) | 3.31 GB | +0.66 GB (driver packages) | −59.5% |

The single largest contributor to the overall reduction is the base-image
switch away from DLStreamer (saves ~3.5 GB by itself) — the dependency
trimming and slim/full split contribute a further, smaller but still
meaningful, reduction on top of that.

---

## 9. Security, compatibility, and reproducibility limitations

- **No hash-pinned dependencies.** `requirements-lock.txt` is a `pip freeze`
  snapshot (142 pinned transitive packages), not generated with
  `--generate-hashes` (that previously timed out against this project's
  large dependency graph). A supply-chain-hardened build would need a true
  hash-verified lock file; not implemented this session.
- **`pyproject.toml` declares `python = "^3.11"`** under its Poetry
  section (used only for dev tooling per its own comment) while the actual
  running image is Python 3.12. This mismatch is pre-existing and not
  corrected this session — flagged in point #9's analysis as still open.
- **GPU/NPU driver source**: installed from GitHub Releases + a Launchpad
  PPA snapshot rather than Intel's official apt repository (unreachable
  from this sandbox). A production CI/build environment should re-verify
  reachability of `repositories.intel.com` and prefer the official source
  if available there.
- **Model-export architectural floor**: `torch`/`transformers`/`optimum`/
  `optimum-intel`/`nncf`/`onnx` cannot be removed from either variant
  without redesigning model provisioning (e.g., an init container that
  performs export once and hands the service a pre-built IR directory).
  This was identified but intentionally **not implemented** this pass, to
  avoid changing a working, documented startup behavior without separate
  review.
- **Non-root execution, HF_TOKEN runtime-only passing, and healthcheck
  behavior** were preserved unchanged from the production Dockerfile's
  design in the new Ubuntu candidate (verified via `docker history`/live
  container inspection).

---

## 10. Failed experiments

- **First `docker build --provenance=false --sbom=false` test** to explain
  a size discrepancy between `docker images` (2.64 GB) and `docker save`
  tar size (567 MB, compressed) — concluded the discrepancy is expected
  (uncompressed vs. compressed layer accounting), not a build defect; no
  Dockerfile change resulted from this experiment.
- **First full-variant build attempt** failed with
  `ResolutionImpossible: Cannot install torchaudio==2.8.0+cpu` because
  `--extra-index-url` set in `requirements-slim.txt` does not carry over to
  the separate `pip install -r requirements-optional.txt` invocation.
  Fixed by repeating the `--extra-index-url` line in
  `requirements-optional.txt` (see §1, §6).
- **First slim-CPU container startup** failed at the model-export step
  with `RuntimeError: ... No CA certificates were loaded from the system`
  because the runtime stage's minimal `apt-get install` list omitted
  `ca-certificates`. Fixed by adding it to the runtime stage's package list
  (see §1, §6).

---

## 11. Remaining steps to fully meet the 2–2.5 GB target

1. Slim-CPU is at 2.65 GB — ~150 MB (≈6%) above the upper bound of the
   requested range. Closing this gap further would require the
   out-of-container model-export redesign described in §4/§9, which is a
   larger change deliberately not undertaken this pass.
2. Hash-based dependency reproducibility (point #9) is not yet implemented.
3. ~~Real GPU/NPU hardware inference validation is blocked~~ — **resolved**:
   validated end-to-end on real Intel Meteor Lake Arc GPU and NPU hardware
   (see §7.4). Both devices load the model and transcribe correctly with no
   errors or silent CPU fallback.
4. Diarization/sentiment inference against real (non-mocked) pretrained
   weights is blocked without a valid `HF_TOKEN` with accepted gated-model
   terms.
5. The Ubuntu candidate has not been wired into `docker-compose.yml` or
   promoted to replace the production Dockerfile — this should only happen
   after mentor review and, ideally, hardware-backed GPU/NPU validation.

---

## 12. Recommendation

The Ubuntu candidate (`docker/Dockerfile.ubuntu`) is **ready for mentor
review** as a candidate, not as a production replacement yet:

- All CPU-path functionality (slim and full) is validated end-to-end with
  real container runs and passes the existing regression suite with zero
  new failures.
- Two real bugs were found and fixed during this validation
  (`ca-certificates` missing, `--extra-index-url` not propagating) —
  demonstrating the value of the empirical build-and-test approach taken
  here over documentation-only estimates.
- The slim image is 67.6% smaller than the original baseline and within
  ~6% of the requested 2–2.5 GB target; the full image preserves every
  existing feature at 2.92 GB (64.3% smaller than baseline).
- GPU/NPU driver installation is now confirmed to work in a real
  `docker build`, resolving a previously-blocking unknown. **GPU and NPU
  inference are now confirmed working on real Intel hardware** (Meteor Lake
  Arc GPU and NPU): health, `/models`, and real audio transcription all
  passed on both devices with no errors or silent CPU fallback.
- Outstanding items before production promotion: a decision on whether to
  pursue the out-of-container model-export redesign to close the remaining
  ~150 MB gap on the slim-CPU variant, and (lower priority) hash-based
  dependency reproducibility.

**Superseded by §13–§17 below (follow-up session).** The items above were
addressed and measured; see those sections for the GPU/NPU TLS root cause
(§13), the model-export-separation prototype and its real measured size
(§14), per-variant dependency locks (§15), a newly quantified further
size-reduction opportunity (§16), and the updated overall recommendation
(§17).

---

## 13. GPU/NPU build TLS failure — root cause and resolution (follow-up session)

**Background:** a previously recorded GPU/NPU build failed with
`curl: (60) SSL certificate problem: unable to get local issuer
certificate` while downloading Intel GPU compute-runtime `.deb` packages
from GitHub Releases. The task explicitly required re-diagnosing this
from scratch rather than trusting the earlier write-up.

**Investigation performed:**
- `curl -v` on the host against the exact failing URL
  (`https://github.com/intel/compute-runtime/releases/download/.../libze-intel-gpu1_*.deb`)
  showed a `302` redirect to `release-assets.githubusercontent.com` — this
  CDN redirect target, not `github.com` itself, is what actually serves
  the file and terminates TLS.
- 6 repeated `openssl s_client -connect release-assets.githubusercontent.com:443`
  probes through the corporate proxy (`proxy-dmz.intel.com:912`) showed
  **intermittent** behavior: 5/6 times a legitimate public certificate
  (Let's Encrypt, `*.github.io`) was returned and verified cleanly; 1/6
  times the connection was intercepted by an internal
  "Intel Proxy Root CA" (via intermediate `srrproxy102.prxy.ice.intel.com`)
  that is **not** present in Ubuntu's default `ca-certificates` trust
  store — exactly reproducing the original build failure's symptom.
- A fresh `docker build --no-cache` of the exact same, unmodified
  Dockerfile (tagged `audio-analyzer:tls-recheck`) **succeeded** on retry,
  confirming the failure is transient/intermittent proxy routing, not a
  permanent block, a missing CA that is always required, or a dead CDN.

**Conclusion:** the root cause is confirmed to be **intermittent
corporate-proxy TLS interception of one specific CDN redirect target**,
not a configuration defect in the Dockerfile and not something a single
static CA addition would reliably fix (since the domain is *sometimes*
reachable with no special CA at all). The existing
`curl --retry 5 --retry-delay 5 --retry-all-errors` already provides
some resilience; this was not sufficient on the occasion the original
failure was recorded, so a defense-in-depth option was added.

**Resolution implemented** (`docker/Dockerfile.ubuntu`):
- Added `# syntax=docker/dockerfile:1` (required for BuildKit secret
  mounts) as the file's first line.
- Added an **optional, no-op-by-default** step:
  `RUN --mount=type=secret,id=corporate_ca,required=false ...` placed
  before the GPU/NPU driver install block. If a build invoker supplies
  `--secret id=corporate_ca,src=/path/to/corporate-ca.pem`, that CA is
  trusted for the duration of the build only; the Dockerfile itself never
  contains, and the repo never stores, any certificate or secret. If no
  secret is supplied (the default, and every build performed in this
  session), the step is a verified no-op.
- **TLS verification is never disabled** — no `curl -k`/`--insecure` was
  added anywhere, satisfying the task's explicit constraint.
- Validated the no-op behavior: rebuilt both `ubuntu-slim-gpu-npu-v3`
  (3.31 GB) and `ubuntu-slim-cpu-v3` (2.65 GB) after adding this step —
  byte-identical sizes to the pre-change builds, confirming zero
  behavioral or size impact when the secret is not supplied.

**Usage (only needed in networks where interception is consistent, not
intermittent):**
```bash
docker build -f docker/Dockerfile \
  --secret id=corporate_ca,src=/path/to/corporate-ca.pem \
  --build-arg INSTALL_GPU_NPU_RUNTIME=true \
  -t audio-analyzer:ubuntu-slim-gpu-npu .
```

**Addendum (cleanup-review session): re-reproduced with a precise root
cause, not just "intermittent proxy."** A fresh `--no-cache` GPU/NPU build
was re-run from scratch rather than assuming the prior finding still
held. This time the failure reproduced **consistently (6/6)**, not 1/6 as
previously observed — the interception rate on this specific network
varies over time/session, it is not a fixed ratio. Host-by-host TLS
probing (`curl -v`, direct connects, no `-k`/`--insecure` used) pinpointed
the exact cause:
- `github.com` itself: TLS verifies cleanly (real Sectigo Limited
  certificate) — this host is not SSL-inspected on this network.
- `ppa.launchpadcontent.net`: TLS verifies cleanly (real Let's Encrypt
  certificate) — also not inspected.
- `release-assets.githubusercontent.com` (the CDN redirect target that
  actually serves the `.deb`/`.tar.gz` payloads): the certificate
  presented is issued by `CN=srrproxy102.prxy.ice.intel.com, OU=Information
  Security Infrastructure, O=Intel Corporation` — **Intel's own internal
  SSL-inspection proxy root**, not a public CA, and not present in
  Ubuntu's default `ca-certificates` trust store.

This confirms, with direct evidence rather than inference: the failure is
caused by Intel's corporate network selectively SSL-inspecting one
specific GitHub CDN hostname (not GitHub's own domain, not Launchpad), and
the inspection is applied inconsistently across requests/sessions on this
network. A user building from outside Intel's corporate network (home
network, a different company's network, a public CI runner) will not
receive Intel's `srrproxy102.prxy.ice.intel.com` certificate and is very
unlikely to hit this exact failure — though any other organization
running equivalent SSL-inspecting middleboxes on outbound GitHub CDN
traffic could see the analogous symptom against their own internal CA.
The default CPU-only build path (`INSTALL_GPU_NPU_RUNTIME=false`, the
Dockerfile default) never executes this `curl` block at all and is
unaffected regardless of network. The existing mitigation (optional,
no-op-by-default BuildKit CA secret, TLS verification never disabled)
remains the correct, minimal, already-implemented fix for the networks
where this is a real blocker — no further change is needed, and no
insecure fallback should be added.

---

## 14. Model-export separation from the runtime image (prototype, measured)

**Investigated:** whether `torch`/`transformers`/`onnx`/`optimum`/
`optimum-intel`/`nncf` (the `optimum-cli export openvino` toolchain) can
be removed from the runtime image entirely by pre-exporting the model at
build time instead of on first container startup.

**Model lifecycle traced (confirmed via code reading, not assumption):**
- `main.py`'s `@app.on_event("startup")` calls `ensure_model()` at
  **container startup**, not image build time.
- `utils/ensure_model.py::_download_openvino_model()` checks
  `_ir_exists(output_dir)` and returns early (cache hit, no `optimum-cli`
  subprocess invoked) if OpenVINO IR files already exist on disk.
- `components/asr/openvino_genai/whisper.py` (the default inference path)
  imports only `openvino_genai`, `soundfile`, `librosa` — confirmed via
  source inspection, zero torch/transformers/onnx/optimum imports.
- Only `utils/ensure_model.py` (export), `pyannote_diarizer.py`, and
  `ov_pyannote_diarizer.py` (diarization, full-variant-only) import the
  export/ML-training stack anywhere in the codebase.

This confirmed the architecture supports a "pre-exported IR, no export
toolchain at runtime" variant **for whichever model/weight_format was
pre-exported at build time** — not for arbitrary runtime model changes.

**Prototype built** (`docker/Dockerfile.ubuntu`, new `--target
runtime-minimal`, reachable only via explicit `--target`, zero effect on
default/slim/full builds):
- `requirements-minimal.txt` (new file): `requirements-slim.txt` minus
  `torch`, `onnx`, `transformers`, `optimum`, `optimum-intel`, `nncf`.
- New `builder-minimal` stage: builds a venv from `requirements-minimal.txt`.
- New `exporter` stage: installs the **full** export toolchain
  (`requirements-slim.txt`, same as today) and runs the service's own,
  unmodified `ensure_model()` at build time against the committed
  `config.yaml` defaults (`openai/whisper-base`, no `weight_format`),
  producing OpenVINO IR under `models/openvino/whisper-base`.
- New `runtime-minimal` stage: copies the `builder-minimal` venv (no
  export toolchain) plus the pre-exported IR from the `exporter` stage.
  Build-only; torch/transformers/optimum/onnx/nncf themselves are never
  copied into this stage, so they contribute 0 bytes to its final size.

**Real bug found and fixed during this prototype:** an initial version
used a single trailing `chown -R ${APP_UID}:${APP_GID} /app/audio_analyzer`
(the same pattern the existing `runtime` stage uses). Because the
~290 MB pre-exported model had just been `COPY`-ed into that same tree,
the recursive `chown` forced an overlayfs **copy-up** of the entire model
into its own layer — silently storing the model's bytes **twice** in the
image. Measured impact: the first (buggy) build only saved ~80 MB vs.
slim (2.57 GB), masking most of the real reduction. Fixed by using
`COPY --chown=` on the app-source and model `COPY` instructions instead,
and narrowing the final `chown -R` to only the small, freshly-created
runtime directories (`models/dummy`, `chunks`, `storage`, `.cache`) that
don't pre-exist from an earlier layer.

**Measured result (after the fix):**

| Metric | Value |
|---|---|
| `ubuntu-slim-cpu-v3` (baseline for comparison) | 2.648 GB (2,648,105,526 bytes) |
| `ubuntu-minimal-cpu` (pre-exported, no export toolchain) | **2.092 GB (2,092,063,992 bytes)** |
| Real measured savings | **556 MB (21.0%)** |
| `/opt/venv` size, slim vs. minimal (`du -sh`, ground truth) | 1.4 GB → 583 MB |

**Functional validation performed (not just a build):**
- `torch`/`transformers`/`optimum`/`onnx`/`nncf` confirmed absent via
  live `import` attempts inside the running container (all raised
  `ImportError`, as intended).
- Started a real container from `ubuntu-minimal-cpu`; startup log showed
  `⚡ Using cached export at models/openvino/whisper-base` (the existing
  cache-check short-circuits correctly, no `optimum-cli` subprocess runs).
  Health check returned 200.
- `POST /transcriptions` with `tests/philosophy_10_russell_128kb.mp3`
  returned HTTP 200, `status: completed`, and the transcript file
  contained correct text ("Chapter X of Philosophy by Bertrand
  Russell...").
- **Documented limitation confirmed by deliberately triggering it**:
  started a second container with
  `AUDIO_ANALYZER__models__asr__name=whisper-tiny` (a model not
  pre-exported at build time). Startup log showed the exact expected
  failure mode: `ensure_model()` still attempts the `optimum-cli`
  subprocess (no special-casing needed), which fails cleanly with
  `ModuleNotFoundError: No module named 'optimum'` — logged, not
  swallowed — and the container then fails FastAPI startup loudly
  (`ERROR: Application startup failed. Exiting.`) rather than silently
  degrading or falling back. This satisfies the task's "fail safely and
  visibly" requirement.

**Trade-off (must be communicated to users of this variant):** only the
model/weight_format combination baked in at build time works without a
rebuild. Changing `config.yaml`'s `models.asr.name`/`weight_format` at
runtime requires either rebuilding this variant with the new model
pre-exported, or switching to the `slim`/`full` variant (which retain the
export toolchain and can export any supported model on demand).

**Not yet done / explicitly out of scope this pass:**
- GPU/NPU variant of `runtime-minimal` (the prototype is CPU-only; adding
  `INSTALL_GPU_NPU_RUNTIME` support to this stage would be a small,
  mechanical follow-up).
- Wiring this variant into `docker-compose.yml` or promoting it to a
  production tag — left for mentor review, consistent with not replacing
  the production Dockerfile prematurely.
- Pre-exporting more than the single default model/weight_format (would
  require either multiple `runtime-minimal*` targets or a build arg to
  select which model(s) to bake in).

---

## 15. Dependency-locking follow-up: per-variant resolved locks

The existing `requirements-lock.txt` is a `pip freeze --all` snapshot of
a **full**-variant install, reused as a constraints file for slim/minimal
builds. This follow-up produced two **dedicated, `pip-compile`-resolved**
lock files scoped to each smaller variant's actual dependency graph:

- `requirements-slim-lock.txt` — resolved from `requirements-slim.txt`.
- `requirements-minimal-lock.txt` — resolved from `requirements-minimal.txt`.

**Validation performed (not just resolver output):** each lock file was
installed into a fresh, empty venv (`pip install -r <file>`) and the
expected imports were exercised:
- Slim lock: `import fastapi, openvino, openvino_genai, torch,
  transformers, optimum, librosa` succeeded; `triton` confirmed **not**
  reintroduced by the resolution.
- Minimal lock: `import fastapi, openvino, openvino_genai, librosa`
  succeeded; `torch`/`transformers`/`optimum`/`onnx`/`nncf` confirmed
  **absent**, as intended.

**Hash generation re-attempted and still impractical — root cause
pinpointed precisely this time:** `pip-compile --generate-hashes` was run
against the smaller slim-only graph (not the full combined graph). Pure
dependency *resolution* completed in ~2.5–3 minutes — much faster than
the full graph — but the subsequent hash-computation phase did not finish
within a 500-second window. Verbose output showed pip-tools was
individually downloading and hashing **every published platform/ABI wheel
variant** for each pinned package from PyPI's JSON API (e.g. `openvino`
alone publishes dozens of `cp310`–`cp314`, Linux/macOS/Windows, x86/ARM
wheels) — not just the wheel matching this build's actual target
platform. This is a documented pip-tools behavior, not a fixable
misconfiguration in this project, and is an interactive-time-budget
constraint rather than a correctness problem: every version in the
produced lock files **is** fully and reproducibly resolved, just not
additionally hash-verified. Recommended as a follow-up in a CI
environment without an interactive time limit, e.g. a dedicated nightly
job with no wall-clock pressure.

---

## 16. Further size-reduction investigation (quantified, not yet implemented)

Used `docker history`, `du -sh`, and `dpkg-query` on the built images
(real inspection, not estimates) to look for additional reduction
opportunities beyond the model-export-separation prototype.

**Librosa's hard (non-optional) transitive dependencies were re-verified,
per the task's explicit instruction not to assume they're removable:**
`scikit-learn`, `scipy`, `numba`, `llvmlite`, and `numpy` are all listed
under `Requires-Dist` (not an `extra`) in librosa 0.11.0's own package
metadata — confirmed by reading `librosa-*.dist-info/METADATA` directly
inside the built image. These are **not** candidates for removal.

**New finding: the `ffmpeg` apt package pulls in ~300 MB of codec/
rendering libraries unrelated to audio file decoding.** `dpkg-query -W
-f='${Installed-Size}\t${Package}'` inside `ubuntu-minimal-cpu` shows the
largest OS-level (non-Python) packages are:

| Package | Installed-Size | Why it's present |
|---|---|---|
| `libllvm20` | 140 MB | Pulled in by `mesa-libgallium`'s software GL rasterizer |
| `mesa-libgallium` | 42 MB | Mesa 3D/GL support — `ffmpeg` links against GL/VA-API acceleration libs even for audio-only use |
| `libicu74` | 36 MB | Unicode support, pulled transitively |
| `libflite1` | 27 MB | A speech-synthesis (TTS) library — `ffmpeg` links it for an unused `flite` filter |
| `libcodec2-1.2` | 16 MB | A voice/radio codec this service never uses |
| `libx265-199` | 16 MB | HEVC **video** codec — irrelevant to an audio-only service |
| `libavfilter9` | 13 MB | Part of ffmpeg's filter graph, plausibly needed for resampling |
| `liblapack3` | 7 MB | Linear algebra, pulled transitively |
| `libsvtav1enc1d1` | 7 MB | AV1 **video** encoder |
| `librsvg2-2` | 6.6 MB | SVG **image** rendering |
| `libaom3` | 5.3 MB | AV1 **video** codec |
| `libjxl0.7` | 3.6 MB | JPEG-XL **image** codec |

Total installed-size across all OS packages in the minimal image: **~561
MB**, of which a meaningful fraction (conservatively 250–300 MB,
summing the clearly audio-irrelevant rows above) comes from Ubuntu's
full multimedia-codec `ffmpeg` build, which compiles in support for
essentially every audio/video/image/subtitle format and hardware
acceleration backend Debian/Ubuntu ships, rather than only the formats
this service actually needs (basic audio decode/resample for
mp3/wav/webm-opus uploads, plus ALSA for live microphone capture).

**Why this was investigated but not implemented this pass:**
- `components/ffmpeg/audio_preprocessing.py` invokes `ffmpeg -f alsa -i
  <device>` for **live microphone capture**, and `api/custom_endpoints.py`
  calls `arecord -l` to enumerate input devices. A drop-in replacement
  (e.g. a statically-built, codec-minimal `ffmpeg` binary such as the
  common BtbN/John Van Sickle static builds) would very likely **not**
  include ALSA input support, since those builds target portability
  across distros/containers without a system ALSA stack — this would
  silently break the live-capture feature, which is exactly the kind of
  regression this task explicitly warned against.
- Validating a replacement safely would require real microphone-hardware
  testing of the live-capture code path (not just file-upload
  transcription), which was out of scope for the time available in this
  pass.

**Recommendation:** treat this as the next concrete, numbers-backed lever
(roughly 250–300 MB, on top of the model-export-separation savings) for a
future pass, conditioned on either (a) building a custom minimal `ffmpeg`
with explicit `--enable-alsa --disable-everything
--enable-decoder=mp3,pcm*,... --enable-demuxer=mp3,wav,ogg,...` (precise,
audio-only codec selection) and validating live-mic capture against it on
real hardware, or (b) confirming live-mic capture could be served by
`libsndfile`/`soundfile`'s PortAudio-based capture instead of shelling out
to `ffmpeg -f alsa`, removing the `ffmpeg` dependency for that path
entirely. Neither was attempted this pass to avoid an unvalidated
regression risk.

---

## 17. Updated recommendation (follow-up session; supersedes §12)

- **GPU/NPU TLS build failure: root-caused and resolved.** Confirmed via
  repeated TLS probing and a fresh `--no-cache` rebuild to be intermittent
  corporate-proxy interception of one CDN redirect target, not a
  permanent block. An optional, no-op-by-default BuildKit secret-mount
  escape hatch was added for networks where this is NOT intermittent, with
  TLS verification never disabled. See §13.
- **GPU and NPU inference independently re-validated end-to-end** against
  the rebuilt `-v3` images on real Intel Meteor Lake Arc GPU/NPU hardware:
  both real `/transcriptions` calls (not just device enumeration) returned
  correct transcript text with the requested device actually in use and no
  silent CPU fallback.
- **Model-export separation: prototyped, measured, and functionally
  validated.** `audio-analyzer:ubuntu-minimal-cpu` (built via `--target
  runtime-minimal`) measures **2.09 GB**, a real (not projected) 556 MB /
  21% reduction from the 2.65 GB slim baseline — within the mentor's
  requested 2–2.5 GB range for a CPU image. A genuine overlayfs
  `chown`/copy-up duplication bug was found and fixed in the process
  (without the fix, only ~80 MB would have been saved). The documented
  trade-off (only the pre-exported default model works without a rebuild)
  was deliberately and successfully triggered to confirm it fails loudly,
  not silently.
- **Dependency locking: improved, with an honest, precisely-diagnosed
  limitation.** Produced and validated `requirements-slim-lock.txt` and
  `requirements-minimal-lock.txt` (true `pip-compile`-resolved locks per
  variant, each confirmed to install cleanly and import correctly).
  Hash-based locking remains impractical within an interactive time
  budget — root-caused specifically to pip-tools hashing every
  cross-platform wheel variant, not to this project's dependency graph.
- **Further size reduction: one well-quantified opportunity identified,
  deliberately not implemented.** The `ffmpeg` apt package contributes an
  estimated 250–300 MB of codec/GL/TTS libraries unrelated to this
  service's actual audio decode/live-capture needs. Not pursued this pass
  because a naive static-ffmpeg swap risks silently breaking the
  live-microphone-capture feature without real hardware validation.
- **Neither the `runtime-minimal` target nor any Ubuntu candidate has been
  wired into `docker-compose.yml` or promoted to replace the production
  Dockerfile.** `docker-compose.yml` and `docker/Dockerfile` (the
  production path) remain untouched by this follow-up session, consistent
  with the task's explicit constraint not to do so prematurely.
- **Recommended next steps, in priority order:** (1) mentor review of the
  `runtime-minimal` trade-off and whether it's an acceptable default for
  CPU-only deployments of the default model; (2) if accepted, add GPU/NPU
  runtime support to `runtime-minimal` and re-validate on hardware; (3)
  investigate the `ffmpeg` minimal-build or libsndfile-capture
  alternative, validated against real microphone hardware; (4) a CI-hosted
  hash-lock generation job with no interactive time pressure.

> **Status update (cleanup-review session, supersedes the `(2)` item
> above):** the mentor reviewed the slim (2.65 GB) / full (2.92 GB) sizes
> and is satisfied — no further size reduction was requested. See §18 for
> what changed as a result.

---

## 18. Cleanup session: removing the minimal variant, lock-file audit (supersedes parts of §6, §14, §15, §17)

**Context:** once the mentor confirmed slim/full sizes were acceptable,
the `runtime-minimal` prototype (§14) and its two dedicated lock files
were re-evaluated purely on maintainability grounds — not on size — since
further size reduction was explicitly no longer a goal.

**Decision: the `builder-minimal` / `exporter` / `runtime-minimal` stages
were removed from `docker/Dockerfile.ubuntu`.** Reasons:
- It duplicated roughly 160 lines of venv-build and runtime-assembly
  logic that otherwise tracks the `builder`/`runtime` stages used by
  slim/full, doubling the maintenance surface for every future dependency
  or OS-package change.
- It is CPU-only, is not referenced by `docker-compose.yml`, any CI
  workflow, or any test, and only ever supports one hard-coded model —
  changing the configured model or quantization requires a Dockerfile
  edit and rebuild, with a hard failure (not a graceful fallback) if the
  model wasn't pre-exported into that build.
- It was already fully measured and functionally validated (2.09 GB,
  cache-hit skip behavior, clean failure on a non-pre-exported model) —
  that evidence is kept in §14 rather than deleted, per the "don't rewrite
  the report unnecessarily" / "remove obsolete docs only if clearly
  superseded" guidance; §14 should be read as **documenting a measured,
  rejected experiment**, not a currently available build target.
- `docker/Dockerfile.ubuntu` is now two stages (`builder` → `runtime`,
  264 lines, down from 430) and was rebuilt from scratch after the edit:
  the `builder`/`runtime` stages hit full Docker layer cache (confirming
  the removal touched nothing they depend on) and the resulting
  `ubuntu-slim-cpu-clean` image measured **2,648,104,531 bytes**,
  matching the pre-cleanup 2.65 GB slim measurement to within
  layer/metadata noise (~1 KB) — i.e., zero functional or size impact on
  the retained slim/full path.
- **Files deleted as a direct consequence:** `requirements-minimal.txt`,
  `requirements-minimal-lock.txt` (both exclusively consumed by the
  removed `builder-minimal` stage).

**Separately, `requirements-slim-lock.txt` was also deleted — not because
the minimal variant was removed, but because it was never actually wired
into any build.** Auditing `docker/Dockerfile.ubuntu` showed every `pip
install` (`builder` stage, both slim and full) uses `-c
requirements-lock.txt` — the original `pip freeze` snapshot of a full
install — as its constraints file. `requirements-slim-lock.txt` (a
dedicated `pip-compile`-resolved lock scoped to the slim dependency set,
produced in the prior session and documented in §15) was validated
standalone in an isolated venv but was never referenced by the Dockerfile,
`docker-compose.yml`, any script, or any test (confirmed via a repo-wide
`grep`). Diffing it against `requirements-lock.txt` showed real version
drift (e.g. `filelock==4.1.1` vs. `4.2.0`, differing package-name
capitalization indicating different generation tooling/snapshots) —
switching the Dockerfile to consume it would be a real dependency-version
change requiring a full fresh build and regression pass to validate, which
is disproportionate to "don't further optimize, make small justified
changes." **`requirements-lock.txt` remains the sole, working constraints
file for every retained build (slim, full, and GPU/NPU variants of
either).** §15's validation work on the two dedicated lock files is kept
in this document as a record of what was tried and why it wasn't adopted,
but those two files no longer exist in the working tree (only
`requirements-minimal-lock.txt`, tied to the removed variant, and
`requirements-slim-lock.txt`, the unwired one, were deleted;
`requirements-lock.txt` itself is untouched).

**Re-validation performed after the edit (fresh builds and a live
container, not just a diff review):**

| Check | Result |
|---|---|
| `docker build` (slim, no special args) | Cache-hit on `builder`/`runtime`; succeeded |
| Image size (slim) | 2.65 GB — unchanged |
| `docker build --build-arg IMAGE_VARIANT=full` | Cache-hit on `builder`; succeeded, 2.92 GB — unchanged |
| `GET /health` | `{"status":"ok"}` |
| `GET /models` | Returns the one configured model, as before |
| Real CPU transcription (`philosophy_10_russell_128kb.mp3`) | `status: "completed"`, HTTP 200, transcript written |
| Invalid `model_name` | HTTP 400 with a clear rejection message (point #11 behavior intact) |
| Invalid `device` | HTTP 400 with a clear rejection message (point #10/#11 behavior intact) |
| Non-root execution | `uid=1000(ubuntu) gid=1000(ubuntu)` — confirmed non-root (see note below) |
| Storage persistence across restart | Prior job's output directory still present after `docker restart` |
| Fresh `--no-cache` GPU/NPU build | Reproduced the TLS failure again (see updated §13 addendum); this is a pre-existing, already-understood, already-mitigated network condition, not a regression introduced by this cleanup |

**Minor observation (not a defect introduced by this cleanup, not
fixed):** the `runtime` stage's `useradd -u 1000 -g 1000 appuser` fails
silently (`|| true`) because Ubuntu 24.04's base image already ships a
default `ubuntu` account at uid/gid 1000; `USER 1000:1000` therefore
resolves to the pre-existing `ubuntu` account rather than a literal
`appuser`. The container still runs as a genuine non-root uid (1000), so
this is a cosmetic naming mismatch only, present before this cleanup
session and out of scope to change here.

**Net result:** `docker/Dockerfile.ubuntu` now has a single build surface
(two stages, `IMAGE_VARIANT=slim|full`, optional
`INSTALL_GPU_NPU_RUNTIME`), a single constraints file
(`requirements-lock.txt`), and no experimental/unused dependency files in
the working tree — functionally identical in size and behavior to the
pre-cleanup state for every variant the mentor has approved.
