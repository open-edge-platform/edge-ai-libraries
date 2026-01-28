# GPU Ingestion & Telemetry Game Plan

> Living document that captures the proposed upgrades for VDMS DataPrep to reach DL Streamer-class GPU utilization. Update this file as features land.

## 1. Objectives

- Remove redundant CPU preprocessing and memory copies by decoding + preprocessing directly on GPU.
- Align OpenVINO pipeline knobs (streams, batching, tiles) with DataPrep worker settings for predictable throughput.
- Provide observability (telemetry, profiling) to prove GPU path wins before rollout.
- Keep API mode and SDK mode behavior compatible while offering request-level overrides.

## 2. Workstreams & Tasks

### 2.1 GPU-Native Decode & Zero-Copy Frames

- Swap the current python-side decode/resize path for VAAPI/oneVPL (via GStreamer or FFmpeg) that outputs NV12 surfaces on the GPU.
- Export VA handles (`VADisplay`, surface IDs) to Python so we can build OpenVINO remote contexts.
- Implement a feature flag `use_gpu_ingest` (env + request DTO) to guard-rollout this code path.
- Fallback to the existing CPU/NumPy path when the GPU stack is unavailable.

### 2.2 Remote Context + Remote Tensor Wiring

- Derive `ov::intel_gpu::ocl::VAContext` (or `ClContext`) from the decoder handles and pass it to `core.compile_model` in `sdk_embedding_helper.py`.
- Wrap NV12 planes with `create_tensor_nv12` and feed them into `infer_request.set_tensor(...)` instead of copying into host memory.
- Cache compiled models + contexts per device/tile (e.g., `GPU.0`, `GPU.0.1`) so multiple workers reuse the same queues and weights.
- Extend settings to include `target_gpu_device`/`target_gpu_tile` for pinning ingestion jobs.

### 2.3 Async Streams, Batching, and Scheduling

- Map `MAX_PARALLEL_WORKERS` to `ov::hint::num_requests`/`ov::num_streams` and set `ov::hint::performance_mode = THROUGHPUT` when GPU ingest is on.
- Pre-create async infer requests (one per worker) and switch to `start_async()`/`wait()` loops, enabling decode/upload/infer overlap.
- Expose config for automatic batching (`BATCH:GPU` or throughput hint) and document how it interacts with `EMBEDDING_BATCH_SIZE`.
- Support multi-tile/multi-GPU deployments by allowing scheduler to pick `GPU.X` or `GPU.X.Y` strings.
- Query `ov::optimal_number_of_infer_requests` / `ov::optimal_batch_size` at runtime and size the CLIP + YOLOX request pools + batch chunks automatically, while keeping env overrides for experimenters.

### 2.4 Telemetry, Profiling, and APIs

- Add telemetry fields: `use_gpu_ingest`, `gpu_device_id`, `gpu_tile`, `remote_tensor_path` (NV12 vs host), `ov_num_streams`, `ov_optimal_batch`.
- Update `scripts/profile_dataprep.py` so it can toggle GPU ingest, capture new metrics, and compare CPU vs GPU runs automatically.
- Extend `/videos/minio` DTO with optional overrides (`use_gpu_ingest`, `target_tile`, `override_workers`, `override_batch`) while keeping env defaults.
- Document operational steps (drivers, `/dev/dri` mounts, env vars) for GPU ingestion in README/deployment guides.

## 3. Milestones / Ordering

1. **Prototype GPU decode + remote tensor path** (single worker, manual toggle) and validate functional parity.
2. **Integrate remote context caching + OpenVINO hints** with feature flag still off by default.
3. **Expand telemetry/profiling + request overrides** to prove gains and allow experimentation without rebuilds.
4. **Flip default to GPU ingest** once stability + throughput targets are met, keeping CPU path as fallback.

## 4. Acceptance Criteria

- GPU ingest path processes a video end-to-end with zero host copies (confirmed via telemetry and profiling).
- Throughput scales with workers/streams similarly to DL Streamer baseline on the same hardware.
- Telemetry dashboard shows GPU-specific metrics and profiling script can auto-compare CPU vs GPU runs.
- Request-level overrides work without service restarts, and documentation explains how to enable GPU ingest in production.


## 5. Progress Update – 2025-12-19

### Auto-Sized OpenVINO Async Pools

- **What changed:** The CLIP and YOLOX handlers now query `optimal_number_of_infer_requests` and `optimal_batch_size` at runtime and size their async request pools/chunks accordingly. When the device skips `optimal_batch_size`, we fall back to `optimal_number_of_infer_requests` and expose env overrides (`OV_IMAGE_ASYNC_REQUESTS`, `OV_TEXT_ASYNC_REQUESTS`, `OV_IMAGE_ASYNC_CHUNK`, `OV_TEXT_ASYNC_CHUNK`) so perf engineers can pin exact queue depths.
- **Why:** This keeps the inference side in lock-step with the GPU driver's capabilities, avoids over/under-utilization, and removes the need to rebuild containers when experimenting with different queue depths.
- **Operational note:** Top-level batching is still governed by `EMBEDDING_BATCH_SIZE`. The handler splits each logical batch into OpenVINO-sized chunks, so setting the env overrides above is the right way to force 32-wide GPU chunks.

### Warmup Stability + Remote Tensor Prep

- **What changed:** All NumPy batches are wrapped in `ov.Tensor` objects before being submitted to `set_tensor(...)`. Warmup logs now show clean startup with four async requests per encoder and no type-mismatch errors.
- **Why:** The GPU runtime rejected bare NumPy arrays when we reused infer requests during warmup, leading to startup failures. Wrapping tensors keeps the request pool reusable and is a prerequisite for the upcoming remote-tensor (VA surface) integration.

### Telemetry & Worker Configuration Hygiene

- **What changed:** Telemetry now records per-stage timings (extraction, detection, embedding, storage), throughput, batch statistics, and request IDs. The settings validator also treats blank `MAX_PARALLEL_WORKERS` env values as “unset,” letting compose files leave the field empty without tripping validation.
- **Why:** These metrics prove that the GPU path delivers the promised throughput and make regressions obvious. The validator tweak prevents deployment scripts from failing when the env is intentionally blank so the auto-sizing logic can take control.

### Outstanding Actions

- Surface the new `OV_*` chunk/request overrides in every compose file that runs VDMS DataPrep in SDK mode so operators can flip between device-guided and fixed queue sizes without rebuilding images.
- Document (in README/deployment notes) how `EMBEDDING_BATCH_SIZE` interacts with the OpenVINO chunk size for anyone cross-checking batch math in telemetry.


