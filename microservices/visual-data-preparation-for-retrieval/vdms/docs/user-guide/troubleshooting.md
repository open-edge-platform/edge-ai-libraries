# Troubleshooting

- **Startup fails with “model name must be provided”:** Set `EMBEDDING_MODEL_NAME` before launching Docker (required for both SDK and API modes).
- **Object detection disabled unexpectedly:** Check logs for YOLOX download failures. Ensure the `YOLOX_MODELS_VOLUME_NAME` volume exists and the host has outbound network access during first run.
- **API mode returns 502:** Verify the multimodal embedding service is healthy at `MULTIMODAL_EMBEDDING_ENDPOINT` (see `docker compose -f docker/compose-with-embedding.yaml ps`).
- **Uploads rejected:** Files larger than 500 MB are not accepted by the FastAPI upload endpoint. Stage the video directly in MinIO and use `/videos/minio` instead.
- **GPU acceleration inactive:** Confirm `/dev/dri/*` is mapped into the container, set the relevant device variable (`VDMS_DATAPREP_DEVICE`, `EMBEDDING_DEVICE`, or `DETECTION_DEVICE`) to `GPU`, and keep `SDK_USE_OPENVINO=true`.
- **NPU acceleration inactive:** Confirm `/dev/accel/accel0` is available on the host and mapped into the container, set the relevant device variable (`VDMS_DATAPREP_DEVICE`, `EMBEDDING_DEVICE`, or `DETECTION_DEVICE`) to `NPU`, and keep `SDK_USE_OPENVINO=true`. Verify the selected model supports NPU inference via the [OpenVINO Supported Models](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-models.html) page.
- **First NPU run is slow (one-time model compilation):** The first time a model runs on NPU, OpenVINO compiles it to an NPU-specific blob, which takes noticeably longer than CPU/GPU startup. This is expected and happens once per model/configuration. The compiled blob is cached on the `OV_MODELS_DIR` mount (default `/app/ov_models`), so subsequent runs reuse it and start quickly — persist this volume to retain the cache across container restarts.

## 4K/8K frames overflow the shared-memory block (worker timeout)

**Symptom.** Ingesting a high-resolution (4K/8K) video stalls and the DataPrep
worker is killed and rebooted by Gunicorn. The pipeline stage workers log that
their queues never fill, then the worker aborts with signal `134` (SIGABRT) and
leaks shared-memory objects:

```text
WARNING: | detection_worker | [DETECTION QUEUE EMPTY] WAITING...
WARNING: | store_worker      | [STORE_WORKER] Queue empty, waiting...
WARNING: | embed_worker      | [EMBED_WORKER] Queue empty, waiting...
WARNING: | process_result_worker | [RESULT WORKER] Queue empty, waiting...
[CRITICAL] WORKER TIMEOUT (pid:8)
[ERROR] Worker (pid:8) was sent code 134!
UserWarning: resource_tracker: There appear to be 1024 leaked shared_memory objects to clean up at shutdown
```

**Why it happens.** In SDK mode the decoder transports each frame through a
pre-allocated pool of fixed-size shared-memory blocks
(`SharedMemoryPool` in `src/core/embedding/decoder.py`). Every decoded frame is
written into **one** block as a raw RGB buffer of exactly `width × height × 3`
bytes. The block size is controlled by `SDK_VIDEO_SHM_BLOCK_SIZE`, which defaults
to `6220800 = 1920 × 1080 × 3` (1080p). When a frame is larger than the block,
the write into the too-small buffer fails inside the decode worker; the frame is
never enqueued, so every downstream stage (detection → embed → store → result)
sits on an empty queue and eventually the whole worker hits the Gunicorn timeout
and is force-killed, orphaning the shared-memory blocks it had acquired.

**Fix.** Set `SDK_VIDEO_SHM_BLOCK_SIZE` to at least `width × height × 3` for your
highest-resolution source **before** sourcing the setup script (or bring the
stack down and back up so the new value is applied):

| Source resolution | Pixels (W × H) | Minimum `SDK_VIDEO_SHM_BLOCK_SIZE` (`W × H × 3`) |
|---|---|---|
| 1080p (default) | 1920 × 1080 | `6220800` |
| 4K UHD | 3840 × 2160 | `24883200` |
| DCI 4K | 4096 × 2160 | `26542080` |
| 8K UHD | 7680 × 4320 | `99532800` |

```bash
# Example: enable 4K ingestion (3840 x 2160 x 3 = 24883200 bytes per block)
export SDK_VIDEO_SHM_BLOCK_SIZE=24883200
source ./setup.sh          # or: source ./setup.sh --down && source ./setup.sh
```

**Also budget the total shared memory.** The pool pre-allocates
`SDK_VIDEO_SHM_MAX_BLOCKS × SDK_VIDEO_SHM_BLOCK_SIZE` bytes in the host `/dev/shm`
(the container runs with `ipc: host`). With the default `512` blocks, 4K needs
≈ `12.7 GB` and 8K needs ≈ `51 GB` of `/dev/shm`. If the host cannot spare that
much, lower `SDK_VIDEO_SHM_MAX_BLOCKS` to keep the product within your available
`/dev/shm` (check with `df -h /dev/shm`), for example:

```bash
export SDK_VIDEO_SHM_BLOCK_SIZE=24883200   # 4K frame size
export SDK_VIDEO_SHM_MAX_BLOCKS=128        # 128 x 24883200 ≈ 3.2 GB of /dev/shm
```

> **Tip:** Pick the block size from the **largest** resolution you will ingest.
> A larger-than-needed block size is safe (it only wastes memory); a smaller one
> triggers the failure above. If you mix resolutions, size for the largest.
