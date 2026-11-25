<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

<!--hide_directive
```{eval-rst}
.. meta::
   :description: Overview of the Semantic Compression Toolbox with Adaptive Rate (STAR), a dockerized computer vision pipeline for semantic compression of images.
   :keywords: STAR, semantic compression, image compression, adaptive rate, encoder, decoder, AVIF, YOLO, OpenVINO, Docker.
```
hide_directive-->

# Semantic Compression Toolbox with Adaptive Rate (STAR): Image Pipeline

<!--hide_directive
::::{container} component_header_row
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/libraries/star">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/README.md">
     Readme
  </a>
</div>
::::
hide_directive-->

Semantic Compression Toolbox with Adaptive Rate (STAR) is a dockerized computer vision pipeline
for semantic compression of images.
STAR provides a complete, reproducible image-processing pipeline that runs either
locally in Python or inside a Docker container. It decomposes each frame into *semantic objects* and
a *background*, encodes each part with the cheapest codec that still meets a byte budget, and
reconstructs a composite image on the receiving side.

You can use the toolbox in **four ways**:

1. **Direct path (file transfer).** `semantic_img_comp.main` runs as an `encoder` or a `decoder`
   process. The image feeder reads images from a mounted input directory (or a YAML catalog of
   directories) and sends them to the encoder, which encodes them and streams the
   multiplexed payloads over a TCP socket or HTTP endpoints. The decoder listens and writes
   reconstructed images, masks, and logs to the mounted output directory. This is the
   self-contained mode used for benchmarking and reproducible runs.

2. **Plugged-in external streaming source (semantic bridge).** `SemanticCodecBridge`
   (`src/semantic_img_comp/integration/semantic_codec_bridge.py`) exposes the same codec as a pure
   in-memory API — JPEG bytes in, multiplexed payload out, and payload in, PIL image out —
   with **no network or filesystem I/O of its own**. Any external transport or live stream
   can therefore be plugged into the pipeline by calling the bridge. `SemanticImageManager`
   (`src/semantic_img_comp/integration/semantic_image_manager.py`) is a ready-made adapter that
   wires the bridge, including per-frame logging,
   compression-level selection, and level-0 JPEG passthrough.

3. **HTTP-based service.** This service implements `SemanticCodecBridge` and exposes HTTP
   endpoints that allow users to send and receive images. See
   [configuration](./configuration.md#5-openapi-http-specification) for the HTTP API reference.

4. **TCP-based service.** This service implements `SemanticCodecBridge` and exposes a TCP socket
   that allows users to send and receive images. The socket supports multiple clients
   and can be used as a reference. See
   [configuration](./configuration.md#1-cli-reference-python--m-semantic_img_compmain) for the
   TCP API reference.

All paths share the same encoder, decoder, configuration, adaptive pipeline manager, and
log schema, so results obtained in direct-path mode carry over to a streamed deployment.

The pipeline performs:

- **Encoding:**
  1. Image loading (directory, YAML catalog, in-memory JPEG bytes, HTTP endpoints, or TCP socket)
  2. Preprocessing
  3. Model inference for semantic extraction (YOLO object detection, optionally tiled)
  4. Background and object compression using AV1 Image File Format (AVIF), low-bit, and
     symbolic encoders under a byte budget
  5. Metadata and payload generation (multiplexing)
  6. Payload emission — returned to the caller (semantic bridge)

- **Decoding:**
  1. Receiving frames and demultiplexing the payload
  2. Decompressing the background and objects
  3. Pasting objects back and forming the composite final decoded image

## Features

- Fully dockerized execution (no environment setup required)
- **Adaptive pipeline manager** that re-plans the encoding strategy for every frame. See
  [Pipeline manager](./configuration.md#pipeline-manager).
- **Two compression levels** (`level_1`, `level_2`), each with its own scaling ranges and codec sets
- **Byte-budget-driven codec fallback:** codecs are attempted in configured order until the target
  payload size is met
- Object/background budget split with binary scale search (`obj_budget_ratio`, `max_iter_bg`, `max_iter_obj`)
- Tiled YOLO inference with cross-tile non-maximum suppression (NMS) for large imagery, plus
  OpenVINO™ INT8 model support
- Optional bypass of detection entirely (`--skip-obj-detection`), or reuse of pre-computed
  annotations (`--annot_dir` / `--annot_file`)
- **Input data rate limiting** and **run duration limiting** to emulate a bandwidth-constrained source
- Structured Newline-Delimited JSON (NDJSON) logging plus an offline summarizer with plots
  (`summarize_logs`)
- Evaluation utilities: YOLO detection on reconstructions, semantic/cosine similarity metrics,
  and side-by-side composite viewers
- Detector fine-tuning and dataset split/remap helpers under `finetuning/`
- Mountable input and output folders; model checkpoint loading; modular utility/model separation

## Get Started

If you want to compress images semantically and reconstruct them on the receiving side,
start here with the basics:

- [Prerequisites](./quickstart.md#prerequisites)
  — set up Docker or a local Python environment, and download the detection model.
- [Run locally in containers](./quickstart.md#run-locally-in-containers)
  — build the image, then start the decoder and the encoder in just a few steps.

Once the pipeline is up and running, explore the full
[Quick Start guide](./quickstart.md) for running without Docker, feeding your
own images, the output layout, and assessing encoder performance with
`summarize_logs`.

## Next Steps

- [Configuration](./configuration.md) — CLI reference, multi-directory input
  catalogs, input data rate limiting, thread tuning, common configuration knobs,
  the HTTP API, and the container health check.
- [Pipeline manager](./configuration.md#pipeline-manager) — how the encoder
  re-plans the encoding strategy for every frame.
- [Codec methods](./configuration.md#codec-methods-supported-by-the-application) — the
  supported codecs and how to include or exclude them per compression level.

<!--hide_directive
:::{toctree}
:hidden:

quickstart
configuration
:::
hide_directive-->
