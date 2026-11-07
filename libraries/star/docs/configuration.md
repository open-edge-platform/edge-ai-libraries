<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Configuration

This document explains all possible options, knobs and enviromental variables that could be configured in STAR.

## 1. CLI reference (`python -m semantic_img_comp.main`)

This chapter shows all possible flags that can be configured on encoder/decoder application or container.

| Argument | Type / choices | Default | Applies to | Description |
| --- | --- | --- | --- | --- |
| `--role` | `encoder` \| `decoder` | **required** | both | Which side of the pipeline to run. Each role starts the legacy batch TCP mode and the REST service concurrently. |
| `--config` | path | `configs/default.yaml` | both | YAML config file. In the container the default is `/app/configs/default.yaml`. |
| `--input` | path | `io.input_dir` | encoder | Input image directory **or** a `.yml`/`.yaml` catalog file listing several directories. Validated at startup for the encoder only. |
| `--output` | path | `io.output_dir` | both | Output root for logs, reconstructions, and masks. |
| `--host` | string | `0.0.0.0` | both | Encoder: hostname of the decoder to connect to. Decoder: bind address. |
| `--port` | int `1..65535` | `5000` | both | TCP port. |
| `--fps` | float ≥ 0 | `0.0` | encoder | Target send rate in frames/s; `0` disables send throttling. |
| `--target-input-rate-mbps` | float ≥ 0 | `image_feeder.target_input_rate_mbps` | encoder | Emulated input source data rate in Mbps. |
| `--run-duration-sec` | float ≥ 0 | `image_feeder.run_duration_sec` | encoder | Hard-stop the image feeder after this many seconds. |
| `--annot_file` | path | `io.annot_file` | encoder | Annotations JSON file. |
| `--annot_dir` | path | `io.annot_dir` | encoder | Directory of YOLO-style `.txt` labels (one per image); bypasses YOLO detection. |
| `--skip-obj-detection` | flag (alias `--skip-obj-detction`) | off | encoder | Encode background only; also forces `obj_budget_ratio = 0`. |
| `--canny-mode` | `old` \| `new` | `img_process.canny_mode` | encoder | Edge detector used by mask-aware codecs. |
| `--decoder-url` | URL | none | encoder | Base URL of the decoder's REST service to forward encoded payloads to, e.g. `http://decoder:8000`. Falls back to the `DECODER_URL` env var. **Required** for `--role encoder`. |
| `--service-host` | string | `0.0.0.0` | both | Bind address for the REST service side. |
| `--service-port` | int `1..65535` | `8000` | both | Bind port for the REST service side. |
| `--stream-buffer-size` | int | `200` | decoder | Max decoded frames retained per stream (REST service side) before the oldest is evicted. |

CLI values always override the corresponding YAML keys. Exit codes: `0` success, `2` bad
arguments / missing paths, `1` runtime error or interrupt.

## 2. Multi-directory input catalogs

`--input` can point to a YAML catalog file that lists several image directories. Sampling mode is
controlled by `io.input_catalog_sampling` (`uniform` by default; set `proportional` to weight by each
directory's remaining image count).

Example `input_catalog.yaml`:

```yaml
input_dirs:
  - /app/data/Ground EO Images
  - /app/data/Ground LWIR Images
  - /app/data/Helicopter Images
random_seed: 7
```

Then modify `docker-compose.yaml` encoder configuration to have:

```bash
volumes:
  - "$(pwd)/data/:/app/data"
...
  command: --role encoder --input /app/data/input_catalog.yaml --host decoder --port 5000 --decoder-url http://decoder:8000
```

### 3. Input data rate limiting (optional)

The encoder simulates a bandwidth-constrained image source by controlling how fast input images are
fed into the pipeline.

**Via CLI:**

```bash
  command: --role encoder --host decoder --port 5000 --decoder-url http://decoder:8000 --target-input-rate-mbps 1.1 --run-duration-sec 120
```

**Via config file (`configs/default.yaml`):**

```yaml
image_feeder:
  target_input_rate_mbps: 1.1  # null or omit to disable
  run_duration_sec: 120        # 2 minutes; null or omit to run until all images are sent
```

**How it works:** a dedicated **feeder thread** releases images into a queue at the configured rate,
fully decoupled from how long the encoder takes to process them:

```
Feeder Thread (producer)           Encoder Loop (consumer, main thread)
────────────────────────           ─────────────────────────────────────
Release image 1 immediately   →   get() → encode+send (may be slow)
Sleep (img1_bytes×8 / Mbps)        ...
Release image 2               →   get() → encode+send
Sleep (img2_bytes×8 / Mbps)        ...
[stop after run_duration_sec]      hard-stop: socket closed, queue dropped
```

- Sleep duration per image = `(file_bytes × 8) / (target_Mbps × 1e6)` seconds
- If the encoder is slower than the configured rate, images queue up (backlog grows), and the
  pipeline manager reacts to that backlog
- If the encoder is faster, it blocks on the queue waiting for the next image
- Encoder performance has **no effect** on the input arrival rate
- Once `run_duration_sec` expires the encoder **hard-stops**: the TCP socket is closed immediately
  and any images still waiting in the queue are dropped
- Set either key to `null` (or omit it) to disable the corresponding limit
- Set `image_feeder.log_feeder_events: true` to emit `feeder_rate_limited` and `feeder_enqueued` events (the
  latter includes the current `queue_backlog`); `frame_sent` events always include `queue_backlog`
  at send time, and `feeder_duration_limit_reached` / `duration_limit_forced_stop` report the
  released and dropped image counts


### 4. Thread tuning in Docker Compose (optional)

The image sets defaults for the CPU thread pools used by OpenMP/MKL/BLAS/NumExpr (and `AVIF_JOBS`).
You can override them at runtime without rebuilding the image:

```bash
environment:
  OMP_NUM_THREADS: 4
  MKL_NUM_THREADS: 4
  OPENBLAS_NUM_THREADS: 4
  NUMEXPR_NUM_THREADS: 4
```

Quick guidance:

- lower values (1–2): better for tight CPU limits / reduced contention
- higher values (4+): may improve throughput on larger CPUs
- tune per deployment by benchmarking your encoder/decoder workload

## Common configuration knobs

`configs/default.yaml` is the single source of truth for runtime behaviour. The codec and
pipeline-manager keys are covered above; the table below explains the everyday `app` and `io`
settings you are most likely to change. CLI flags always win over YAML values.

### Logging and console output

| Key | Default | What it does |
| --- | --- | --- |
| `app.log_level` | `INFO` | Verbosity of the Python logger: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, or `SILENT`. `SILENT` is a project-specific level set above `CRITICAL`, so it suppresses *all* logging **and** forces the progress bar and console output off, whatever the other flags say. |
| `io.print_runtime_logs` | `false` | Whether log records also go to the console. When `false`, logs still reach the files — the terminal just stays quiet. Set to `true` when debugging interactively. |
| `io.write_json_logs` | `true` | Controls **only** `encoder_log.json` / `decoder_log.json` (the structured NDJSON used by `summarize_logs`). Setting it to `false` does not affect `app_enc.log` / `app_dec.log`. |
| `image_feeder.log_feeder_events` | `false` | Adds per-image `feeder_rate_limited` and `feeder_enqueued` events (including `queue_backlog`) to the encoder log. Useful for diagnosing rate limiting and backlog behaviour; noisy otherwise. |

`app.log_level` and `io.print_runtime_logs` are independent: the level decides *what* is recorded,
`print_runtime_logs` decides *whether you also see it in the terminal*.

### Input feed and run duration

| Key | Default | What it does |
| --- | --- | --- |
| `image_feeder.target_input_rate_mbps` | `1.0` | Emulates a bandwidth-constrained image source. A feeder thread releases each image after `(file_bytes × 8) / (Mbps × 1e6)` seconds, independently of how fast the encoder works — so a slow encoder builds a queue backlog, which is exactly what the pipeline manager reacts to. Set to `null` for unlimited throughput. CLI: `--target-input-rate-mbps`. |
| `image_feeder.run_duration_sec` | `900` | Stops the feeder after N seconds, then **hard-stops**: the socket closes immediately and queued images are dropped. Handy for bounded benchmark runs. Set to `null` to run until every image is sent. CLI: `--run-duration-sec`. |
| `io.input_dir` | `./data` | Input image directory, or a YAML catalog listing several directories. Relative to the current working directory. CLI: `--input`. |
| `io.input_catalog_sampling` | `uniform` | Only used with a YAML catalog: `uniform` draws evenly across directories, `proportional` weights by each directory's remaining image count. |
| `io.annot_file` / `io.annot_dir` | empty | Supply existing detections instead of running YOLO. `annot_dir` (YOLO-style `.txt` per image) bypasses detection entirely; setting `annot_file` also makes reconstructions reuse the original image filenames. CLI: `--annot_file` / `--annot_dir`. |

### Outputs and visualisation

| Key | Default | What it does |
| --- | --- | --- |
| `io.output_dir` | `./output` | Root for `log/` and `recon_images/`. Relative to the current working directory. CLI: `--output`. |
| `io.save_visualizations` | `true` | **Gates whether the decoder writes reconstructed images at all.** With `false` the pipeline still encodes, transmits, decodes and logs normally, but `recon_images/` stays empty — a common source of "it ran but produced nothing". |
| `io.draw_bboxes` | `false` | Overlays detected object boxes on the saved reconstructions. Only has an effect when `save_visualizations` is `true` and the frame contains objects. Useful for inspection, but the boxes are burned into the pixels — keep it `false` for quality evaluation. |

### TCP client identity

| Key | Default | What it does |
| --- | --- | --- |
| `app.client_id` | `default` | **[encoder]** Sent to the decoder at the start of the TCP connection (one-time handshake) and used by the decoder for saved filenames (`recon_images/<client_id>_<frame>.jpeg`) and logs, so they stay stable across encoder reconnects. CLI: `--client-id`. Decoder falls back to the `default` if the handshake is missing or invalid. |

### Compute

| Key | Default | What it does |
| --- | --- | --- |
| `app.device` | `cpu` | Torch device for detection, e.g. `cpu` or `cuda:0`. The shipped default model is an INT8 OpenVINO model intended for CPU. |
| `performance.image_size` | `640` | YOLO inference resolution. Larger sees small objects better at higher cost; the pipeline manager may override tiling per image via `large_dim_tile_threshold_px`. |

## Codec methods supported by the app

The encoder/decoder pipeline mixes perceptual codecs, compact low-bit codecs, and symbolic codecs.
The names below are the ones used internally by the app and are exactly those declared in
`configs/default.yaml`.

| Codec | Used for | Notes |
| --- | --- | --- |
| `color-avif` | bg / obj | Full-color AVIF; highest fidelity, highest cost. Declared in `encoders_tag` but commented out in the active level maps. |
| `mono-avif-high` | background (level 1) | Monochrome AVIF at AVIF quality `0` (highest quality). |
| `mono-avif-mid` | background (level 1), objects (levels 1 and 2) | Monochrome AVIF at AVIF quality `32`. |
| `mono-avif-low` | available | Monochrome AVIF at AVIF quality `55` (strongest AVIF compression). |
| `mono-28bit` | available | Mask-aware 2/8-bit monochrome codec. |
| `mono-2bit` | background (level 2), objects (level 2) | Aggressive 2-bit monochrome codec for very small payload budgets. |
| `mono-mask-1bit` | available | Mask-aware 1-bit codec that transmits only edge/structure. |
| `mono-skel-v1` | available | Skeleton / line-segment codec (tuned by the `mono_skel_*` keys). |
| `mono-shape-v1` | available | Polygon-silhouette codec (tuned by the `mono_shape_*` keys). |
| `airplane-symbol-v1` | objects (level 2) | Symbolic codec: transmits a class symbol and pose instead of pixels, for categories listed in `model.symbol_category_ids`. |

AVIF quality for the three `mono-avif-*` variants is set by `encoder.avif_mono_quality_map`.

In practice:

- AVIF codecs preserve the most visual detail but cost the most bytes.
- Low-bit codecs (`mono-2bit`, `mono-mask-1bit`) are far more bandwidth-efficient, at the cost of texture.
- Mask/structure codecs (`mono-28bit`, `mono-mask-1bit`, `mono-skel-v1`, `mono-shape-v1`) are useful
  when preserving structure or edges matters more than photorealistic texture.
- `airplane-symbol-v1` is the cheapest option: a few bytes per object.

### Including or excluding codecs

Codec selection is **per compression level** and independent for background and objects, via the
`img_process.encoders_tag_{bg,objs}_level_{1,2}` maps. These are the only codec-selection inputs used
at runtime; the shared `img_process.encoders_tag` map is kept for backward compatibility and to define
the global codec-name → numeric-ID mapping carried in the payload.

Active configuration in `configs/default.yaml`:

```yaml
img_process:
  encoders_tag_bg_level_1:
    mono-avif-high: 1
    mono-avif-mid: 2

  encoders_tag_objs_level_1:
    mono-avif-mid: 2

  encoders_tag_bg_level_2:
    mono-2bit: 5

  encoders_tag_objs_level_2:
    mono-avif-mid: 2
    mono-2bit: 5
    airplane-symbol-v1: 10
```

How to use it:

- **Include a codec:** add its name (with its ID from `encoders_tag`) to the relevant level map.
- **Exclude a codec:** remove or comment out its entry.
- **Control fallback order:** codecs are tried in the order listed; the last configured codec acts as
  the final fallback if earlier ones do not meet the byte budget.
- **Keep IDs unique and stable:** the numeric ID is what the decoder reads from the payload, so the
  encoder and decoder must agree on the mapping.
- **Level selection:** `pipeline_manager.compression_level` (`1` → `level_1`, `2` → `level_2`) picks
  the active pair of maps; scaling ranges come from the matching `img_process.*_level_1` /
  `*_level_2` keys, and target rates from `encoder.compression_levels`.

## 5. OpenAPI HTTP spec

To get specification for HTTP endpoints, you can run following commands to get spec in JSON format.

```bash
curl -fsS http://localhost:8001/openapi.json -o encoder-openapi.json
curl -fsS http://localhost:8002/openapi.json -o decoder-openapi.json
```

To use HTTP endpoints, you have to create stream on encoder:

```bash
curl -X PUT http://localhost:8001/v1/streams/mystream \
  -H "Content-Type: application/json" \
  -d '{"compression_level": 2}'
```

and then send image to that stream:

```bash
$ curl -X POST    --data-binary @data/sample_001.jpeg  http://localhost:8001/v1/streams/mystream/frames
{"status":"accepted","stream_id":"mystream"}
```

To see metrics like processing time for each step and compression rate, check logs in encoder application/container.
To get compressed image, send following request to decoder:

```bash
curl http://localhost:8002/v1/streams/mystream/frames/1 -o frame1.jpg
```

## 6. Container health check

Both the encoder and decoder images expose a status endpoint on port `5999` (which by-default is not exposed and used only by the container), served in-process by
`semantic_img_comp.healthcheck.start_status_server()` (started once at startup in `main.py`):

```bash
curl http://localhost:5999/
# {"is_alive": true, "http_ready": true, "tcp_ready": true}
```

| Field | Meaning |
| --- | --- |
| `is_alive` | The status server itself is up and serving (process is running). |
| `http_ready` | The REST service (`encoder.service` / `decoder.service`) has finished initializing. Flipped once `EncoderService`/`DecoderService` is constructed. |
| `tcp_ready` | The legacy batch TCP listener (`encoder.runner` / `decoder.runner`) is accepting connections. Flipped once the socket is ready. |
