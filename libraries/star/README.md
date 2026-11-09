<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# 📦 Semantic Compression Toolbox with Adaptive Rate (STAR): Image Pipeline

**A dockerized computer vision pipeline for semantic compression of images**

---

## Overview

This repository provides a complete, reproducible image-processing pipeline designed to run either
locally in Python or inside a Docker container. It decomposes each frame into *semantic objects* and
a *background*, encodes each part with the cheapest codec that still meets a byte budget, and
reconstructs a composite image on the receiving side.

The toolbox can be driven in **four different ways**:

1. **Direct path (file transfer).** `semantic_img_comp.main` runs as an `encoder` or a `decoder`
   process. The image feeder reads images from a mounted input directory (or a YAML catalog of
   directories) and sends them to encoder, that encodes them, and streams the muxed payloads over a TCP socket or HTTP endpoints. The decoder
   listens and writes reconstructed images, masks, and logs to the mounted output
   directory. This is the self-contained mode used for benchmarking and reproducible runs.

2. **Plugged-in external streaming source (semantic bridge).** `SemanticCodecBridge`
   (`src/semantic_img_comp/integration/semantic_codec_bridge.py`) exposes the same codec as a pure
   in-memory API — JPEG bytes in, muxed payload out, and payload in, PIL image out — with **no
   network or filesystem I/O of its own**. Any external transport or live stream can therefore be
   plugged into the pipeline by calling the bridge. `SemanticImageManager`
   (`src/semantic_img_comp/integration/semantic_image_manager.py`) is a ready-made adapter that
   wires the bridge, including per-frame logging,
   compression-level selection, and level-0 JPEG passthrough.

3. **HTTP-based service.** that implements `SemanticCodecBridge` and exposes HTTP endpoints to user that allow to send and receive images using HTTP. See [configuration](docs/configuration.md#5-openapi-http-spec) for the HTTP API reference.

4. **TCP-based service.** that implements `SemanticCodecBridge` and exposes TCP socket to user that allow to send and receive images using TCP. Socket support multiple clients and can be used as reference. See [configuration](docs/configuration.md#1-cli-reference-python--m-semantic_img_compmain) for the TCP API reference.

All paths share the exact same encoder, decoder, configuration, adaptive pipeline manager, and
log schema, so results obtained in direct-path mode carry over to a streamed deployment.

The pipeline performs:

- **Encoding:**
  1. Image loading (directory, YAML catalog, or in-memory JPEG bytes, HTTP endpoints, TCP socket)
  2. Preprocessing
  3. Model inference for semantic extraction (YOLO object detection, optionally tiled)
  4. Compressing background and objects using AVIF, low-bit, and symbolic encoders under a byte budget
  5. Metadata and payload generation (mux)
  6. Emitting the payload — returned to the caller (semantic bridge)

- **Decoding:**
  1. Receiving frames and demultiplexing the payload
  2. Decompressing the background and objects
  3. Pasting objects back and forming the composite final decoded image

---

## Features

- Fully dockerized execution (no environment setup required)
- **Adaptive pipeline manager** (see below) that re-plans the encoding strategy for every frame
- **Two compression levels** (`level_1`, `level_2`), each with its own scaling ranges and codec sets
- **Byte-budget-driven codec fallback:** codecs are attempted in configured order until the target
  payload size is met
- Object/background budget split with binary scale search (`obj_budget_ratio`, `max_iter_bg`, `max_iter_obj`)
- Tiled YOLO inference with cross-tile NMS for large imagery, plus OpenVINO INT8 model support
- Optional bypass of detection entirely (`--skip-obj-detection`), or reuse of pre-computed
  annotations (`--annot_dir` / `--annot_file`)
- **Input data rate limiting** and **run duration limiting** to emulate a bandwidth-constrained source
- Structured NDJSON logging plus an offline summarizer with plots (`summarize_logs`)
- Evaluation utilities: YOLO detection on reconstructions, semantic/cosine similarity metrics,
  and side-by-side composite viewers
- Detector fine-tuning and dataset split/remap helpers under `finetuning/`
- Mountable input and output folders; model checkpoint loading; modular utility/model separation

### Pipeline manager

`src/semantic_img_comp/encoder/pipeline_manager.py` (`EncoderPipelineManager`) is the adaptive
control loop of the encoder. It is consulted **once per image**, before encoding, and returns a
`PipelineContext` describing how that specific frame should be encoded. It is used by both the
direct path and the semantic bridge.

**1. Queue-pressure tiers.** The manager watches the backlog of the input queue and degrades the
pipeline gracefully as pressure builds (thresholds from
`pipeline_manager.queue_backlog_threshold_1/2/3`, defaults `5 / 10 / 15`):

| Queue backlog | Background | Objects |
| --- | --- | --- |
| `queue < t1` | normal | normal |
| `t1 ≤ queue < t2` | fast | normal |
| `t2 ≤ queue < t3` | fast | fast |
| `queue ≥ t3` | fast | object detection skipped |

**2. Hysteresis.** To avoid oscillating between tiers on a noisy queue, an entered state persists
until the backlog drops below a lower exit threshold — `skip_obj_hysteresis_exit` (default
`(t2+t3)/2`) for the skip-object state, and `fast_full_hysteresis_exit` (default `(t1+t2)/2`) for the
fast-background/fast-object state.

**3. Adaptive compression-rate tuning.** After a warmup period
(`adaptive_compression_rate_warmup_frames`), the manager compares the *aggregate* compression rate
achieved so far against the rate configured for the active compression level and nudges the per-frame
target accordingly. Averaging is either `moving_average` or `ema`
(`adaptive_compression_rate_method`, with `adaptive_compression_rate_ema_alpha`). The result is
clamped by `adaptive_compression_rate_target_margin_ratio` around the level-selected rate, hard-capped
by `adaptive_compression_rate_max`, and can be boosted with `adaptive_compression_rate_boost_factor`.

**4. Per-image tiling.** When detection is active and `max(image_dim) > large_dim_tile_threshold_px`
(default `1280`), the manager forces `tile_size=640` / `tile_overlap=10` for that frame only.

The manager applies its decisions with `apply_pipeline_config()` and always reverts them with
`restore_config()` after the frame, so config mutations never leak across frames.

---

### 10. Output layout

```text
output/
├── log/
│   ├── encoder_log.json
│   └── decoder_log.json
└── recon_images/
    ├── 1.jpeg
    └── ...
```

Notes:

- `encoder_log.json` and `decoder_log.json` are NDJSON structured logs, one JSON object per line, consumed by
  `summarize_logs` (disable with `io.write_json_logs: false`)
- reconstructed decoder outputs are written under `output/recon_images/`, and **only when
  `io.save_visualizations: true`** — otherwise the pipeline runs normally but writes no images
- reconstructions are named by frame counter (`1.jpeg`, `2.jpeg`, …); if `io.annot_file` is set the
  original image filenames are used instead

### 11. Assess and plot encoder performance with `summarize_logs`

Use `src/semantic_img_comp/utils/summarize_logs.py` to convert `encoder_log.json` (NDJSON) into
per-frame summary metrics and optional plots.

```bash
python -m semantic_img_comp.utils.summarize_logs \
  output/log/encoder_log.json \
  --output output/log/encoder_summary.ndjson \
  --plots \
  --save-plots-dir output/log/plots
```

| Argument | Description |
| --- | --- |
| `path` (positional) | NDJSON log file to summarize. |
| `--output` | Write per-entry summary dicts as NDJSON to this file. |
| `--plots` | Generate plots (requires matplotlib). |
| `--save-plots-dir` | Save plots into this directory instead of showing interactive windows. |
| `--skip-bad-json` | Skip malformed JSON lines instead of failing. |

What this gives you for encoder analysis:

- compression metrics: `comp_rate`, `orig_jpeg_bytes`, `total_payload_bytes`
- payload split: `bg_payload_ratio`, `obj_payload_ratio`, `bg_origjpeg_ratio`, `obj_origjpeg_ratio`
- scene/object content: `num_detected_objs`, `obj_orig_pixels_ratio`
- runtime metrics: `runtime_yolo_ms`, `runtime_enc_total_ms`

Saved plot files under `output/log/plots/` include `scatter_comp_vs_orig_bytes.png`,
`scatter_comp_vs_payload_bytes.png`, `scatter_comp_vs_num_pixels.png`, `histograms.png`,
`cdf_plots.png`, and `runtime_cdf_plots.png`.

---

## Repository organization

```text
semantic-img-comp/
├── Dockerfile                     # encoder/decoder image; entrypoint = semantic_img_comp.main
├── pyproject.toml                 # src-layout packaging
├── requirements.txt
├── configs/
|── dlstreamer/
|   |   └── config.json            # configuration file for DLStreamer backend, used only if that backend is selected.
│   └── default.yaml               # single source of truth: app/model/encoder/decoder/io settings
├── models/
│   └── obj_det_models/            # INT8 OpenVINO detection model referenced by default.yaml
├── finetuning/                    # detector fine-tuning + dataset split/remap helpers
│   ├── README.md
│   ├── finetune_det_model.py
│   └── split_remap_yolo_dataset.py
└── src/semantic_img_comp/
    ├── main.py                    # CLI entrypoint: --role encoder|decoder (each runs legacy TCP + REST concurrently)
    ├── core/                      # frame / object / background / payload data structures
    │   ├── frame.py               # ImgEncData & ImgDecData containers
    │   ├── object.py              # object crop extraction & budgeting
    │   ├── background.py          # background preparation & scaling
    │   └── payload.py             # payload assembly primitives
    ├── encoder/
    │   ├── runner.py              # TCP implementation of encoder with socket and client handling.
    │   ├── encoder.py             # codec dispatch, budget/scale search, codec fallback
    │   ├── codecs.py              # AVIF / low-bit / mask / symbolic encoders
    │   ├── mux.py                 # payload multiplexing
    │   ├── service.py             # HTTP implementation of encoder with streams and endpoint hhandling
    │   └── pipeline_manager.py    # adaptive per-frame pipeline decisions
    ├── decoder/
    │   ├── runner.py              # TCP decoder server loop
    │   ├── decoder.py             # per-part decoding + composition
    │   ├── demux.py               # payload demultiplexing
    │   ├── codecs.py              # matching decoder for each codec
    │   ├── service.py             # HTTP decoder server loop
    │   └── obj_icons/             # symbol assets used by the symbolic codecs
    ├── integration/               # <- plug an external streaming source in here
    │   ├── semantic_codec_bridge.py    # in-memory JPEG <-> payload <-> image API
    │   └── semantic_image_manager.py   # ImageManager adapter over the bridge
    │   └── dlstreamer_client.py        # Impementation of client to offload 
    inference to DLStreamer
    ├── image_feeder/
    │   └── feeder.py   # Implementation of ImageFeeder for direct file transfer
    ├── net/
    │   └── connection.py          # TCP framing / send / receive helpers
    └── utils/
        ├── config.py              # YAML -> typed config objects, defaults, validation
        ├── load.py / preprocessing.py / postprocessing.py / img_restorer.py
        ├── yolo_wrapper.py        # tiled inference + cross-tile NMS
        ├── logging_helpers.py / runtime.py
        ├── summarize_logs.py      # CLI: NDJSON log summary + plots
        ├── composite_image_viewer.py / run_composite_viewer.py
        └── visualization.py / coco.py
```

Input data (`data/`), reconstructions and logs (`output/`), and model caches are runtime mount points
and are not part of the repository.

---

## License Notes

The star-image library and its components is licensed under the [APACHE 2.0](./LICENSE) license, except for the following components:

| Component   | License   |
| Ultralytics | AGPL-3.0  |
