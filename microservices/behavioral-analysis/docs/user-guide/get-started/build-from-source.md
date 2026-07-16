# Build from Source

## Prerequisites

- Git
- Docker Engine 24.0+ (for container build)
- Python 3.12+ (for standalone build)
- Access to `docker.io/intel/dlstreamer:2026.1.0-ubuntu24` (base image)

---

## Repository Structure

```
behavioral-analysis/
├── Dockerfile                  # Root Dockerfile (used for standalone builds)
├── docker/
│   └── Dockerfile              # Docker Compose build target
├── pyproject.toml              # Project metadata (version 1.0.0, Python >=3.10)
├── requirements.txt            # Python dependencies
├── config/
│   └── patterns.yaml           # Pattern and VLM configuration
└── src/                        # Application source code
```

---

## Build the Docker Image

The Docker Compose configuration builds from `docker/Dockerfile`. To build the image directly:

```bash
# From the behavioral-analysis/ directory
docker build -f docker/Dockerfile -t intel/behavioral-analysis:latest .
```

To build with a specific release tag:

```bash
docker build -f docker/Dockerfile -t intel/behavioral-analysis:1.0.0 .
```

To build using the root Dockerfile:

```bash
docker build -f Dockerfile -t intel/behavioral-analysis:latest .
```

### What the Build Does

1. Starts from `intel/dlstreamer:2026.1.0-ubuntu24` (provides Python 3.12, OpenVINO, GStreamer).
2. Copies `requirements.txt` and installs Python dependencies (layer-cached if unchanged).
3. Removes `__pycache__`, test directories, and strips `.so` files to reduce layer size.
4. Copies `src/` and `config/` into `/app/`.
5. Sets `PYTHONPATH` to include `/app/src`.
6. Exposes port `8080`.
7. Sets the default command to: `python3 -m uvicorn main:app --host 0.0.0.0 --port 8080`.

---

## Standalone Local Setup

For standalone local setup, follow [Run Standalone](./run-standalone.md).

---

## Run Tests

Tests use `pytest` with `pytest-asyncio`:

```bash
# From the behavioral-analysis/ directory
source .venv/bin/activate
PYTHONPATH=src pytest tests/
```

To run with verbose output:

```bash
PYTHONPATH=src pytest tests/ -v
```

The test suite is located in `tests/test_pose_analyzer.py` and covers `PoseAnalyzer`, `Pose` keypoint properties, midpoint calculations, and pattern detection logic.

---

## Build Verification

After building the Docker image, verify it starts correctly:

```bash
docker run --rm -p 8085:8080 \
  -e SEAWEEDFS_ENDPOINT=http://host.docker.internal:8333 \
  -e MQTT_HOST=host.docker.internal \
  intel/behavioral-analysis:latest
```

Then check the health endpoint:

```bash
curl http://localhost:8085/health
```

---

## Common Build Issues

### `pip install` fails on `git+https://` dependency

**Cause:** Git is not installed or network access to GitHub is blocked.

**Resolution:**
```bash
apt-get install -y git
# or set http_proxy/https_proxy if behind a corporate proxy
```

### Base image pull fails

**Cause:** No access to `docker.io/intel/dlstreamer:2026.1.0-ubuntu24`.

**Resolution:** Configure Docker to use your organization's registry mirror, or set `HTTP_PROXY`/`HTTPS_PROXY` for Docker daemon.

### `openvino` import error at runtime

**Cause:** Running outside the base image without OpenVINO installed.

**Resolution:** OpenVINO is provided by `intel/dlstreamer:2026.1.0-ubuntu24`. For standalone use, install OpenVINO Runtime separately or use the container.

### `ModuleNotFoundError` for `gstgva`

**Cause:** `gstgva` is part of the DL Streamer base image and is not available in standalone Python environments.

**Resolution:** This module is only used indirectly via the GStreamer pipeline. For standalone use without GStreamer hardware acceleration, the `YOLOPoseOV` OpenVINO wrapper is used directly and does not require `gstgva`.
