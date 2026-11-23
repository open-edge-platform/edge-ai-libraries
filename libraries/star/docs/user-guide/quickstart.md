<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

<!--hide_directive
```{eval-rst}
.. meta::
   :description: Deploy the Semantic Compression Toolbox with Adaptive Rate (STAR) encoder and decoder locally, with or without Docker, feed images, and assess encoder performance.
   :keywords: STAR, quick start, Docker, encoder, decoder, image feeder, AVIF, avifenc, summarize_logs, OpenVINO.
```
hide_directive-->

# Quick Start

This library supports three types of deployment, depending on the use case:

1. Deployment of both the encoder and the decoder on the same bare-metal machine. Recommended
   only for development. See [documentation](#run-locally-without-docker).
2. Deployment of both the encoder and the decoder in containers on the machine. Recommended
   for demo scenarios and for getting familiar with the Semantic Compression Toolbox with
   Adaptive Rate (STAR) library. See [documentation](#run-locally-in-containers).
3. Deployment of the encoder on one machine and the decoder on another machine. Recommended
   for end users. In general, the steps are identical to the previous point; the only
   difference is that the commands should be executed on different machines, which is denoted
   by a comment in the [documentation](#run-locally-in-containers).

## Prerequisites

- Docker (recommended), **or** Python ≥ 3.9 with `pip install -r requirements.txt` and the
  `libavif` command-line tools (`avifenc` / `avifdec`) on `PATH` — see
  [Make `avifenc` / `avifdec` available](#make-avifenc--avifdec-available-required-for-av1-image-file-format-codecs);
  on Linux/macOS, install them via your package manager
  (for example `sudo apt-get install libavif-bin`).
- The repository uses an INT8 OpenVINO™ detection model under
  `models/obj_det_models/yolov8m_int8_openvino_model`, which is the default referenced by
  `configs/default.yaml`. Run `make pull-model` to (re)download and export it from Hugging
  Face.

## Run Locally Without Docker

Local (non-Docker) invocation uses a **src layout**: the package lives in
`src/semantic_img_comp/`, not at the repository root. It must therefore be installed (or put
on `PYTHONPATH`) before `python -m semantic_img_comp.main` can find it. Install once, then run
everything from the repository root:

```bash
pip install -r requirements.txt
pip install -e .                  # required: makes `semantic_img_comp` importable from anywhere

cd /path/to/semantic-img-comp     # data/output/model paths inside the config are CWD-relative
```

### Download Model

By default, the repository does not include the detection model. Download it manually by
running the following command in the root of the repository:

```shell
make pull-model
```

This command downloads the model, converts it to OpenVINO™ format, and places it in the
default directory.

### Make `avifenc` / `avifdec` Available (Required for AV1 Image File Format Codecs)

The AV1 Image File Format (AVIF) codecs invoke the external `avifenc` and `avifdec` binaries
and look them up on `PATH`. The Docker image installs them via `libavif-bin`, but a local run
does not, so you will see:

```text
The 'avifenc' executable was not found on PATH.
Install libavif tools or make avifenc available before using AVIF encoders.
```

This matters because `configs/default.yaml` selects `mono-avif-*` codecs for the background at
compression level 1 and for objects at both levels — without these binaries those codecs fail
and the encoder falls back to the remaining low-bit codecs.

**Linux / macOS / Windows Subsystem for Linux (WSL).** Install the libavif tools with your
package manager:

```bash
sudo apt-get install libavif-bin      # Debian / Ubuntu / WSL
sudo dnf install libavif-tools        # Fedora / RHEL
sudo apk add libavif-apps             # Alpine
brew install libavif                  # macOS
conda install -c conda-forge libavif  # any OS, inside a conda env
```

**Verify** — this must print a libavif version such as `1.4.1`:

```bash
avifenc --version
avifdec --version
```

If `avifenc --version` works in your shell but the pipeline still reports the binary as
missing, you are almost certainly launching Python from a different shell/session than the one
where you set `PATH`, or from an IDE that does not inherit that variable.

The configuration *file* itself is always found automatically, because `DEFAULT_CONFIG_PATH`
is derived from the package location, not from the current working directory (CWD). You can
override it with `--config` or the `CONFIG_PATH` environment variable. The paths *inside* it —
`io.input_dir: "./data"`, `io.output_dir: "./output"`, and `model.enc_yolo_model_path` — are
relative, so they resolve against wherever you launch from.

### Run STAR

The encoder and decoder are two separate processes, so use **two terminals** and
**start the decoder first** — the encoder needs something to connect to.

```bash
# Terminal 1 — decoder (listens for frames, writes reconstructions)
python -m semantic_img_comp.main --role decoder --port 5000

# Terminal 2 — encoder (reads ./data, encodes, sends to the decoder)
python -m semantic_img_comp.main --role encoder --host 127.0.0.1 --port 5000 --input data --decoder-url http://127.0.0.1:8000
```

Note the asymmetry in `--host`: on the **decoder** it is the *bind* address (`0.0.0.0`, the
default), while on the **encoder** it is the *decoder's address to connect to* — `127.0.0.1`
when both run on the same machine. Both roles also start a REST service concurrently
(`--service-host`/`--service-port`, default `0.0.0.0:8000`). The `--decoder-url` option is
required on the encoder so that its REST side knows where to forward encoded payloads.

Useful variants for the encoder:

```bash
# Stop feeding images after 60 s (bounded test run)
python -m semantic_img_comp.main --role encoder --host 127.0.0.1 --port 5000 --decoder-url http://127.0.0.1:8000 --run-duration-sec 60

# Fast smoke test: background only, no YOLO inference
python -m semantic_img_comp.main --role encoder --host 127.0.0.1 --port 5000 --decoder-url http://127.0.0.1:8000 --skip-obj-detection

# Emulate a bandwidth-constrained source
python -m semantic_img_comp.main --role encoder --host 127.0.0.1 --port 5000 --decoder-url http://127.0.0.1:8000 --target-input-rate-mbps 1.1

# Keep encoder and decoder logs in separate folders
python -m semantic_img_comp.main --role encoder --host 127.0.0.1 --port 5000 --decoder-url http://127.0.0.1:8000 --output output_enc
```

`--input data` is optional (`io.input_dir` already defaults to `./data`), but being explicit
is safer. Add `--fps N` to throttle the send rate to N frames/s; by default there is no send
throttling. Stop either process with `Ctrl+C`.

## Run Locally in Containers

### 1. Build the Docker Image

```bash
make pull-model image
```

> [!NOTE]
> If you are running on two or more machines, either run that command on each of them so
> that the image is present on every machine, or use a combination of
> `docker save/scp/docker load` commands to distribute the image to all machines.

The image entrypoint is `python -m semantic_img_comp.main`, so every argument set in a
[`docker-compose.yml`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/docker-compose.yml) file `command:` section is passed straight to
the container. The command pulls the YOLO model that is needed for object detection and
classification and builds the container.

### 2. Networking

`make decoder` / `make encoder` run using Docker Compose
([`docker-compose.yml`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/docker-compose.yml)), which creates its own project network
automatically and lets every container reach the others by service name (`decoder`,
`encoder`, `dlstreamer-pipeline-server`, ...) — there is **no manual
`docker network create` step**.

The project network is named `<project>_default`, where `<project>` defaults to the repository
folder's name — `star_image_default` for a checkout at `star_image/`. A few sections further
down pass CLI flags the fixed Makefile targets do not expose and fall back to raw
`docker run`; join that same network (`--network star_image_default`) so they can still
resolve `decoder` by hostname, e.g.:

### 3. Run the Container as a Decoder

Run it before starting the encoder.

```bash
make decoder
```

The decoder listens for incoming frames on ports 5000 and 8000 and writes the decoded results
to `./output` on your machine.

### 4. Run the Container as an Encoder

```bash
make encoder
```

This command runs the container with
`--role encoder --host decoder --port 5000 --fps 1 --decoder-url http://decoder:8000`.
Note that this throttles sending to 1 frame/s by default, unlike the unthrottled bare-CLI
invocation in [Run Locally Without Docker](#run-locally-without-docker). To change or remove
options, modify the `command` section of `docker-compose.yml`.

> [!NOTE]
> For the multi-machine use case, you can either run Docker Swarm to reuse the existing steps
> or use the plain IP address of the machine.

By default, the container reads the configuration from `/app/configs/default.yaml`, with:

- input images: `/app/data`
- output directory: `/app/output`

If `model.detector_backend` is set to `dlstreamer` in
[`configs/default.yaml`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/configs/default.yaml#L31), also start the Deep Learning
Streamer Pipeline Server (DL Streamer Pipeline Server), which performs inference.

The variants below pass CLI flags that modify the behavior of the STAR image. Apply them to
the `docker-compose.yml` file before running the corresponding Makefile target.

**Explicit input directory:**

```bash
encoder:
    volumes:
    - "$(pwd)/data/:/app/data"
    ...
    command: "--role encoder --input /app/data --host decoder --port 5000 --decoder-url http://decoder:8000"
```

**Explicit configuration file:**

```bash
encoder:
    volumes:
    - "$(pwd)/data/:/app/data"
    ...
    command: "--role encoder --config /app/configs/default.yaml --host decoder --port 5000 --decoder-url http://decoder:8000"
```

**Run the YOLO backend on the Neural Processing Unit (NPU):**

If an NPU is present on the system, it is mounted to the containers. Depending on the backend
type, change the following configuration files:

1. If the YOLO backend is used, as configured in
   [`configs/default.yaml`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/configs/default.yaml#L32), change
   [`configs/default.yaml`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/configs/default.yaml#L7) manually to `intel:npu` and
   rebuild the image by running `make image`.
2. If DL Streamer is used, Docker Compose automatically uses the
   [`DLStreamer config`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/configs/dlstreamer/config.json). Select the pipeline that
   DL Streamer uses by setting the `dlstreamer_pipeline_name` field in
   [`configs/default.yaml`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/configs/default.yaml#L34).

**Annotations instead of live detection:**

You can write detections to a file instead of performing live detection. To do so, change the
`command` field as follows:

```bash
# Annotations JSON
command: --role encoder --annot_file /app/data/annotations.json --host decoder --port 5000 --decoder-url http://decoder:8000

# Directory of YOLO-style .txt labels (skips YOLO inference)
command: --role encoder --annot_dir /app/data/labels --host decoder --port 5000 --decoder-url http://decoder:8000

# No objects at all — background-only encoding
command: --role encoder --skip-obj-detection --host decoder --port 5000 --decoder-url http://decoder:8000
```

For all available options, see the [configuration](./configuration.md) file.

## Image Feeder

The image feeder is an agnostic tool that allows reading local files and sending them to the
encoder via TCP or HTTP. By default, it runs as a separate thread in the
[encoder](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/src/semantic_img_comp/main.py#L404), which can be configured via the
[configuration file](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/configs/default.yaml). To use it, create the `data` directories
using the make target:

```shell
make dirs
```

Copy the images to that folder:

```shell
sudo cp /path/to/images/* data/
```

Then rerun the make command so that the images have the correct permissions. The containers
run as a dedicated user and cannot access images copied by the root/current user:

```shell
make dirs
```

After that, deploying the encoder (via Python or Docker) starts the image feeder, which sends
the local images to the encoder.

## Output Layout

Once the encoder and decoder have processed the images, the results are written under the
output directory (`io.output_dir`, `./output` by default):

```text
output/
├── log/
│   ├── encoder_log.json
│   └── decoder_log.json
└── recon_images/
    ├── mystream_1.jpeg
    └── ...
```

> [!NOTE]
>
> - `encoder_log.json` and `decoder_log.json` are Newline-Delimited JSON (NDJSON) structured
>   logs, one JSON object per line, consumed by `summarize_logs` (disable with
>   `io.write_json_logs: false`)
> - reconstructed decoder outputs are written under `output/recon_images/`, and **only when
>   `io.save_visualizations: true`** — otherwise the pipeline runs normally but writes no images
> - reconstructions are named `<client_id>_<frame>.jpeg` (`mystream_1.jpeg`, `mystream_2.jpeg`,
>   … with the `app.client_id` shipped in `configs/default.yaml`); if `io.annot_file` is set,
>   the original image filenames are used instead
> - with Docker Compose, [`docker-compose.yml`](https://github.com/open-edge-platform/edge-ai-libraries/blob/main/libraries/star/docker-compose.yml) mounts `./log` over
>   `/app/output/log`, so the log files are written to `./log/` on the host instead of
>   `./output/log/`

## Assess and Plot Encoder Performance with `summarize_logs`

Use `src/semantic_img_comp/utils/summarize_logs.py` to convert `encoder_log.json` (NDJSON)
into per-frame summary metrics and optional plots:

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
| `--output` | Write per-entry summary dictionaries as NDJSON to this file. |
| `--plots` | Generate plots (requires matplotlib). |
| `--save-plots-dir` | Save plots into this directory instead of showing interactive windows. |
| `--skip-bad-json` | Skip malformed JSON lines instead of failing. |

The summary gives you the following metrics for encoder analysis:

- compression metrics: `comp_rate`, `orig_jpeg_bytes`, `total_payload_bytes`
- payload split: `bg_payload_ratio`, `obj_payload_ratio`, `bg_origjpeg_ratio`,
  `obj_origjpeg_ratio`
- scene/object content: `num_detected_objs`, `obj_orig_pixels_ratio`
- runtime metrics: `runtime_yolo_ms`, `runtime_enc_total_ms`

Saved plot files under `output/log/plots/` include `scatter_comp_vs_orig_bytes.png`,
`scatter_comp_vs_payload_bytes.png`, `scatter_comp_vs_num_pixels.png`, `histograms.png`,
`cdf_plots.png`, and `runtime_cdf_plots.png`.
