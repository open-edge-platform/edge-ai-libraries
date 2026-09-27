<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Public Object Detection Graph

This deployment exposes `publicDetection`, a MediaPipe graph that
uses the public OVMS calculators demonstrated in the OVMS 2026.1
`object_detection` example.

Each request runs SSD Lite object detection and returns the input image with
detected objects and labels rendered on it.

## Prepare and deploy

From this directory, download the public model artifacts:

```bash
bash prepare_models.sh
```

The parent OVMS configuration registers the graph under
`publicDetection`. Reload the service after downloading the
models:

```bash
docker compose up -d --force-recreate ovms
```

## Run one request

```bash
no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1 \
uv run --with opencv-python-headless --with 'tritonclient[grpc]' \
python client.py /path/to/image.jpg --grpc-address localhost:9000
```

The client writes `<image>-annotated.jpg` next to the input image.

## Validate gRPC streaming

The same graph supports OVMS `ModelStreamInfer`. The client opens one gRPC
stream and sends timestamped image requests; `--frames` repeats the supplied
image for a bounded local check.

```bash
no_proxy=localhost,127.0.0.1 NO_PROXY=localhost,127.0.0.1 \
uv run --with opencv-python-headless --with 'tritonclient[grpc]' \
python client.py /path/to/image.jpg --grpc-address localhost:9000 \
  --streaming --frames 3
```

Each response is written as `<image>-stream-<timestamp>.jpg`.