# Build from Source

This guide explains how to build the Behavioral Analysis image and run it with the latest deployment behavior.

## Prerequisites

- Git
- Docker Engine 24.0+
- Docker Compose v2.x (recommended for runtime verification)
- Python 3.10+ for local source-based execution (`pyproject.toml` requires `>=3.10`)
- Access to `docker.io/intel/dlstreamer:2026.1.0-ubuntu24` (base image)

Model prerequisites:

- YOLO-Pose OpenVINO IR model files (`.xml` and `.bin`) under `./models/yolo_models/yolo26n-pose/`
- If VLM is enabled, VLM model files under `./models/vlm_models/` (including OVMS model config)

## Repository Structure

```text
behavioral-analysis/
├── Dockerfile
├── docker/
│   └── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── .env
├── config/
│   └── patterns.yaml
├── src/
└── tests/
```

## Deployment Modes (Build-Time Awareness)

Runtime behavior is controlled by `DEPLOYMENT_MODE`:

- `standalone+api` (default in `.env`): direct REST API mode (`POST /api/v1/analyze/batch`)
- `seaweedfs+mqtt`: storage-backed asynchronous processing mode

In Docker Compose, `ovms-vlm` is started by default and `behavioral-analysis` depends on it being healthy.

## Build the Docker Image

Build using the compose-target Dockerfile:

```bash
docker build -f docker/Dockerfile -t intel/behavioral-analysis:latest .
```

Build with a specific tag:

```bash
docker build -f docker/Dockerfile -t intel/behavioral-analysis:1.0.0 .
```

Optional: build from root Dockerfile:

```bash
docker build -f Dockerfile -t intel/behavioral-analysis:latest .
```

## Verify in Docker Compose (Recommended)

1. Prepare environment values (the default mode is already `standalone+api`):

   ```bash
   cp .env .env.local
   ```

2. Ensure model paths are populated:

   - `${DOWNLOADED_MODEL_PATH}/yolo_models/yolo26n-pose/` exists
   - `${DOWNLOADED_MODEL_PATH}/vlm_models/` exists if `VLM_ENABLED=true`

3. Build and start:

   ```bash
   docker compose --env-file .env.local build behavioral-analysis
   docker compose --env-file .env.local up -d
   ```

4. Verify health:

   ```bash
   curl http://localhost:8085/health
   ```

5. Verify that the batch endpoint is reachable (`standalone+api` mode):

   ```bash
   curl -X POST "http://localhost:8085/api/v1/analyze/batch" \
     -F "entity_id=build_check_001" \
     -F "pattern_id=shelf_to_waist" \
     -F "frames=@tests/test_frames/frame_000_0.0s.jpg"
   ```

## Local Source Execution (Host)

For host execution without Docker, use the instructions to
[Run Standalone](./run-standalone.md).

## Run Tests

```bash
source .venv/bin/activate
PYTHONPATH=src pytest tests/ -v
```

Useful subsets:

```bash
PYTHONPATH=src pytest tests/test_pose_analyzer.py -v
PYTHONPATH=src pytest tests/test_api_v1_direct.py -v
```

## Common Build and Startup Issues

### pip install fails on git+https dependency

Cause: Git is missing or GitHub is unreachable.

Resolution:

```bash
apt-get install -y git
```

If you are behind a proxy, configure `http_proxy` and `https_proxy`.

### Base image pull fails

Cause: Cannot pull `intel/dlstreamer:2026.1.0-ubuntu24`.

Resolution: Configure Docker registry access or mirror/proxy.

### OVMS fails to become healthy

Cause: VLM model files/config are missing under `${DOWNLOADED_MODEL_PATH}/vlm_models`.

Resolution: Download the VLM model artifacts first, verify mount path, then restart compose.

### Health endpoint is up but analysis fails

Cause: Missing model files or mismatched runtime config.

Resolution: Verify:

- YOLO model path exists (`/models/yolo_models/yolo26n-pose/...`)
- VLM endpoint and model config are valid when VLM is enabled
- `DEPLOYMENT_MODE` matches intended flow (`standalone+api` or `seaweedfs+mqtt`)
