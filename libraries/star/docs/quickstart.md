<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Quick Start

This library supports 3 types of deployment, depending on the use-case:

1) Deployment of both encoder and decoder on same baremetal machine. Recommended only for development. See [documentation](#run-locally-without-docker).
2) Deployment of both encoder and decoder in containers on the machine. Recommended for demo scenarios and getting familiar with the STAR library. See [documentation](#run-locally-in-containers).
3) Deployment of encoder on one machine and decoder on another machine. Recommended for end-user. In general, steps are identical to previous point, the only difference is that command should be executed on different machines, which is denoted by comment in [documentation](#run-locally-in-containers).

## 0. Prerequisites

- Docker (recommended), **or** Python ≥ 3.9 with `pip install -r requirements.txt` and the `libavif`
  command-line tools (`avifenc` / `avifdec`) on `PATH` — see
  [Make `avifenc` / `avifdec` available](#make-avifenc--avifdec-available-required-for-avif-codecs);
  on Linux/macOS install them via your package manager
  (for example `sudo apt-get install libavif-bin`).
- The repository uses an INT8 OpenVINO detection model under
  `models/obj_det_models/yolov8m_int8_openvino_model`, which is the default referenced by
  `configs/default.yaml`. Run `make pull-model` to (re)download and export it from Hugging Face.

### Run locally without Docker

Local (non-Docker) invocation uses a **src layout**: the package lives in `src/semantic_img_comp/`,
not at the repository root. It must therefore be installed (or put on `PYTHONPATH`) before
`python -m semantic_img_comp.main` can find it. Install once, then run everything from the
repository root:

```bash
pip install -r requirements.txt
pip install -e .                  # required: makes `semantic_img_comp` importable from anywhere

cd /path/to/semantic-img-comp     # data/output/model paths inside the config are CWD-relative
```
#### Download model

By-default, repository doesn't includes model for detection and user has to download it manually by running following command in root of the repo:

```shell
make pull-model
```

which will download model, convert it to OpenVINO format and place in the default directory.

#### Make `avifenc` / `avifdec` available (required for AVIF codecs)

The AVIF codecs shell out to the external `avifenc` and `avifdec` binaries and look them up on
`PATH`. The Docker image installs them via `libavif-bin`, but a local run does not, so you will see:

```text
The 'avifenc' executable was not found on PATH.
Install libavif tools or make avifenc available before using AVIF encoders.
```

This matters because `configs/default.yaml` selects `mono-avif-*` codecs for the background at
compression level 1 and for objects at both levels — without these binaries those codecs fail and
the encoder falls back to the remaining low-bit codecs.

**Linux / macOS / WSL.** Install the libavif tools with your
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

If `avifenc --version` works in your shell but the pipeline still reports the binary as missing,
you are almost certainly launching Python from a different shell/session than the one where you set
`PATH`, or from an IDE that does not inherit it.

The config *file* itself is always found automatically (`DEFAULT_CONFIG_PATH` is derived from the
package location, not the CWD), and can be overridden with `--config` or the `CONFIG_PATH`
environment variable. The paths *inside* it — `io.input_dir: "./data"`, `io.output_dir: "./output"`,
and `model.enc_yolo_model_path` — are relative, so they resolve against wherever you launch from.

#### Run STAR

The encoder and decoder are two separate processes, so use **two terminals** and
**start the decoder first** — the encoder needs something to connect to.

```bash
# Terminal 1 — decoder (listens for frames, writes reconstructions)
python -m semantic_img_comp.main --role decoder --port 5000

# Terminal 2 — encoder (reads ./data, encodes, sends to the decoder)
python -m semantic_img_comp.main --role encoder --host 127.0.0.1 --port 5000 --input data --decoder-url http://127.0.0.1:8000
```

Note the asymmetry in `--host`: on the **decoder** it is the *bind* address (`0.0.0.0`, the default),
while on the **encoder** it is the *decoder's address to connect to* — `127.0.0.1` when both run on
the same machine. Both roles also start a REST service concurrently (`--service-host`/`--service-port`,
default `0.0.0.0:8000`) — `--decoder-url` is required on the encoder so its REST side knows where to
forward encoded payloads;

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

`--input data` is optional (`io.input_dir` already defaults to `./data`) but explicit is safer.
Add `--fps N` to throttle the send rate to N frames/s; by default there is no send throttling.
Stop either process with `Ctrl+C`.

## Run locally in containers
### 1. Build the Docker image

```bash
make pull-model image
```

[!NOTE] if you are running on 2 or more machines, make sure to either run that command on each of them to make sure that image is present on them or use combination of `docker save/scp/docker load` commands to distribute image to all machines.

The image entrypoint is `python -m semantic_img_comp.main`, so every argument set in a [`docker-compose.yml`](docker-compose.yml) file `command:` section is passed straight to container.
Command will pull YOLO model that is needed for object detection and classification and will build the container.

### 2. Networking

`make decoder` / `make encoder` run
using Docker Compose ([`docker-compose.yml`](docker-compose.yml)), which creates its own project
network automatically and lets every container reach the others by service name (`decoder`,
`encoder`, `dlstreamer-pipeline-server`, ...) — there is **no manual `docker network create` step**.

The project network is named `<project>_default`, where `<project>` defaults to the repository
folder's name — `star_image_default` for a checkout at `star_image/`. A few sections further down
pass CLI flags the fixed Makefile targets don't expose and fall back to raw `docker run`; join that
same network (`--network star_image_default`) so they can still resolve `decoder` by hostname, e.g.:

### 3. Run the container as a decoder (start this first)

```bash
make decoder
```

What this does:

1. Listens for incoming frames on ports 5000/8000.
2. Writes decoded results under `./output` on your machine.

### 4. Run the container as an encoder

```bash
make encoder
```

Runs the container with
`--role encoder --host decoder --port 5000 --fps 1 --decoder-url http://decoder:8000` — note this
throttles sending to 1 frame/s by
default, unlike the unthrottled bare-CLI invocation in
[Run locally without Docker](#run-locally-without-docker). Modify `command` section of `docker-compose.yml` to change or remove options.

[!NOTE] For multi-machine use-case, you might either run Docker Swarm to reuse existing steps or use plain IP address of machine.

By default the container reads config from `/app/configs/default.yaml`, with:

- input images: `/app/data`
- output directory: `/app/output`

If `model.detector_backend: dlstreamer` (see
[`configs/default.yaml`](configs/default.yaml#L31)), also start the DL Streamer Pipeline Server which performs inference. 

The variants below pass CLI flags that modify behaviour of star image. They should be applied to `docker-compose.yml` file before running corresponding target in Makefile.

**Explicit input directory:**

```bash
encoder:
    volumes:
    - "$(pwd)/data/:/app/data"
    ...
    command: "--role encoder --input /app/data --host decoder --port 5000 --decoder-url http://decoder:8000"
```

**Explicit config file:**

```bash
encoder:
    volumes:
    - "$(pwd)/data/:/app/data"
    ...
    command: "--role encoder --config /app/configs/default.yaml --host decoder --port 5000 --decoder-url http://decoder:8000"
```

**Run the YOLO backend on the NPU:**

If NPU is present on the system, then it will be mounted to containers. Depending on type of backend used, following configuration files have to be changed:

1) If YOLO backend is used [`configs/default.yaml`](../configs/default.yaml#L32), then [`configs/default.yaml`](../configs/default.yaml#L7) must be manually changed to `intel:npu` and the image should be rebuilt by running `make image`.
2) If DLStreamer is used, then [`DLStreamer config`](../configs/dlstreamer/config.json) will be automatically used by Docker Compose. User just has to select which pipeline will be used in DLStreamer by setting `dlstreamer_pipeline_name` field in config [`configs/default.yaml`](../configs/default.yaml#L34)

**Annotations instead of live detection:**

It is possible to write detections to file instead of live detection. To do it, change `command` field as following:
```bash
# Annotations JSON
command: --role encoder --annot_file /app/data/annotations.json --host decoder --port 5000 --decoder-url http://decoder:8000

# Directory of YOLO-style .txt labels (skips YOLO inference)
command: --role encoder --annot_dir /app/data/labels --host decoder --port 5000 --decoder-url http://decoder:8000

# No objects at all — background-only encoding
command: --role encoder --skip-obj-detection --host decoder --port 5000 --decoder-url http://decoder:8000
```

To see all possible options that could changed, see the [configuration](configuration.md) file.

## Image feeder

Image feeder is agnostic tool that allows to read local files and send them to encoder via TCP or HTTP. By default, it is running as separate thread in [encoder](../src/semantic_img_comp/main.py#L404), that could be configured via [config file](../configs/default.yaml). To use it, create `data` dirs using make target

```shell
make dirs
```

Copy images to that folder

```shell
sudo cp /path/to/images/* data/
```

And rerun make command to ensure that images have correct permissions, as containers are running as dedicated user and won't have access to images copied by root/current user.

```shell
make dirs
```

After that deployment (via Python or Docker) of encoder will start image-feeder that will send local images to encoder.
