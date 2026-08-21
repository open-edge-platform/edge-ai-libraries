# Configuration

The Behavioral Analysis Service is configured through two complementary mechanisms:

1. Environment variables (loaded through `Settings` in `src/config.py`)
2. `config/patterns.yaml` (pattern logic and VLM settings)

## Deployment Mode

The service supports two deployment modes controlled by `DEPLOYMENT_MODE`.

| Variable | Default | Supported values |
| --- | --- | --- |
| `DEPLOYMENT_MODE` | `standalone+api` | `seaweedfs+mqtt`, `standalone+api` |

Mode behavior:

| Mode | SeaweedFS | MQTT consumer | Primary request path | Typical use |
| --- | --- | --- | --- | --- |
| `seaweedfs+mqtt` | Enabled | Enabled | MQTT topic `ba/requests` | Async production-style pipeline |
| `standalone+api` | Disabled | Disabled | `POST /api/v1/analyze/batch` | Direct API integration and testing |

The default mode in the project `.env` file is `standalone+api`.

Mode-specific requirements:

- `seaweedfs+mqtt` mode:
  - Configure SeaweedFS and MQTT variables.
  - Use queue-based processing (`ba/requests` -> `ba/results`).
- `standalone+api` mode:
  - SeaweedFS and MQTT are not required for runtime analysis.
  - In Docker Compose, OVMS (`ovms-vlm`) starts by default and is used for VLM confirmation when enabled.
  - Download and place VLM model files before startup under `DOWNLOADED_MODEL_PATH/vlm_models`.
  - Use the REST batch endpoint `POST /api/v1/analyze/batch`.

## Environment Variables

All variables are case-insensitive.

### Service Settings

| Variable | Default | Description |
| --- | --- | --- |
| DEBUG | false | Enable debug mode |
| LOG_LEVEL | INFO | Logging level: DEBUG, INFO, WARNING, ERROR |
| DEPLOYMENT_MODE | standalone+api | Deployment mode switch |

### Pose Model and Inference

| Variable | Default | Description |
| --- | --- | --- |
| YOLO_POSE_MODEL | /models/yolo_models/yolo26n-pose/yolo26n-pose.xml | Path to YOLO-Pose OpenVINO IR model (.xml) |
| BA_GST_DEVICE | CPU | OpenVINO inference device: CPU, GPU. See the accelerator mapping requirement below. |
| BA_CONFIDENCE | 0.5 | Minimum keypoint confidence threshold |

Download YOLO26n-pose model:

Run this before `docker compose up` when using `standalone+api` mode.

```bash
cd download-model
./download_yolo_pose.sh
```

Expected output files:

- `models/yolo_models/yolo26n-pose/yolo26n-pose.xml`
- `models/yolo_models/yolo26n-pose/yolo26n-pose.bin`

The host must expose accelerator devices to Docker, and the relevant device entries must be mapped into the `behavioral-analysis` service,
because that container performs the YOLO-Pose OpenVINO inference. For example, `/dev/dri:/dev/dri` (GPU).

> **Note:** If `BA_GST_DEVICE=GPU` is used, the same accelerator device must be added to the
> `behavioral-analysis` service's `devices:` section. Do this using a Docker Compose override
> file instead of editing the tracked `docker-compose.yml` directly, so local device mappings
> survive project updates without merge conflicts.

GPU setup with `docker-compose.override.yml`:

1. Set the device in `.env`:

   ```bash
   BA_GST_DEVICE=GPU
   ```

2. Copy the provided GPU template to an override file (gitignored, never committed):

   ```bash
   cp docker-compose.override.yml.gpu-example docker-compose.override.yml
   ```

3. Run Docker Compose as usual; `docker-compose.override.yml` is merged automatically:

   ```bash
   docker compose up
   ```

The template (`docker-compose.override.yml.gpu-example`) contains:

```yaml
services:
  behavioral-analysis:
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - ${RENDERER_GROUP:-992}
```

### Frame Analysis

| Variable | Default in Settings | .env default (project) | Description |
| --- | --- | --- | --- |
| BA_MIN_FRAMES | 3 | 3 | Minimum frame threshold for v1 accumulation flow |
| BA_MAX_FRAMES | 20 | 30 | Maximum frames fetched in SeaweedFS flow |
| BA_POSE_FRAMES | 15 | 20 | Fallback/global frame count used in pose scoring |

### SeaweedFS (required only for seaweedfs+mqtt)

| Variable | Default | Description |
| --- | --- | --- |
| SEAWEEDFS_ENDPOINT | <http://localhost:8333> | SeaweedFS S3 endpoint |
| SEAWEEDFS_BUCKET | behavioral-frames | Bucket name for frames |
| SEAWEEDFS_ACCESS_KEY | (empty) | S3 access key |
| SEAWEEDFS_SECRET_KEY | (empty) | S3 secret key |

### MQTT (required only for seaweedfs+mqtt)

| Variable | Default | Description |
| --- | --- | --- |
| MQTT_HOST | broker.scenescape.intel.com | MQTT broker host |
| MQTT_PORT | 1883 | MQTT broker port |
| BA_REQUEST_TOPIC | ba/requests | Incoming request topic |
| BA_RESULT_TOPIC | ba/results | Outgoing result topic |

### VLM

The global VLM switch is controlled exclusively by the environment variable `VLM_ENABLED`. The YAML `vlm_settings` block is used only for connection/model settings and does not control the global enable/disable state.

Important: VLM is disabled by default. Enable it explicitly when the environment is configured for VLM confirmation. Ensure model artifacts are downloaded before launch. In Docker Compose, `ovms-vlm` mounts models from `${DOWNLOADED_MODEL_PATH}/vlm_models` and expects the model configuration to be available there.

| Variable | Default | Description |
| --- | --- | --- |
| VLM_ENABLED | false | Global master switch for VLM confirmation after pose match |
| VLM_ENDPOINT | <http://ovms-vlm:8001> | OpenAI-compatible endpoint |
| VLM_MODEL_NAME | Qwen/Qwen2.5-VL-7B-Instruct | Model name for VLM request |
| VLM_TIMEOUT | 300.0 | Request timeout in seconds |
| VLM_MAX_TOKENS | 50 | Maximum tokens in VLM response |
| VLM_TEMPERATURE | 0.1 | Sampling temperature |
| VLM_MAX_IMAGE_SIZE | 256 | Maximum frame size for VLM |
| VLM_MAX_CONCURRENCY | 1 | Maximum concurrent VLM requests |

### Pattern Config Path

| Variable | Default | Description |
| --- | --- | --- |
| PATTERN_CONFIG_PATH | /app/config/patterns.yaml | Path to pattern config file |

## .env File (Docker Compose)

The project .env file controls Docker Compose substitution defaults.

```bash
# Release
RELEASE_TAG=latest

# Deployment mode
# Options: seaweedfs+mqtt, standalone+api
DEPLOYMENT_MODE=standalone+api
LOG_LEVEL=DEBUG

# SeaweedFS (required only for seaweedfs+mqtt mode)
SEAWEEDFS_ENDPOINT=http://seaweedfs:8333
SEAWEEDFS_BUCKET=behavioral-frames

# VLM
VLM_ENDPOINT=http://ovms-vlm:8001
VLM_ENABLED=false

# MQTT (required only for seaweedfs+mqtt mode)
MQTT_HOST=broker.scenescape.intel.com
MQTT_PORT=1883
BA_REQUEST_TOPIC=ba/requests
BA_RESULT_TOPIC=ba/results

# Behavioral Analysis service
BA_SERVICE_PORT=8085
BA_MIN_FRAMES=3
BA_MAX_FRAMES=30
BA_POSE_FRAMES=20
BA_CONFIDENCE=0.5
BA_GST_DEVICE=CPU
# For GPU, set BA_GST_DEVICE=GPU above and create a docker-compose.override.yml from
# docker-compose.override.yml.gpu-example to map host devices (e.g. /dev/dri) without
# editing docker-compose.yml.
DOWNLOADED_MODEL_PATH=./models
```

## Pattern Configuration (config/patterns.yaml)

Behavioral patterns are defined in YAML and loaded from `PATTERN_CONFIG_PATH`.

### VLM Settings Block

```yaml
vlm_settings:
  endpoint: "http://ovms-vlm:8001"
  model_name: "Qwen/Qwen2.5-VL-7B-Instruct"
  timeout: 30.0
  max_tokens: 50
  temperature: 0.1
  max_image_size: 256
  max_concurrency: 1
```

### Pattern Definition Structure

```yaml
patterns:
  <pattern_id>:
    description: "Human-readable description"
    enabled: true | false
    alert_type: <string>

    pose:
      per_side: true | false
      min_pose_confidence: 0.3
      min_confidence_for_alert: 0.30
      phases:
        - name: <phase_name>
          min_frames: <int>
          conditions:
            - subject: <keypoint_name>
              relation: <relation>
              reference: <keypoint_name> | <list> | <virtual_point>

    vlm:
      enabled: true | false
      num_frames: 4
      confidence_threshold: 0.7
      prompt: |
        <freeform prompt text>
      response_fields:
        - reasoning
        - suspicious
        - confidence
```

### Available Keypoint Names (COCO 17)

nose, left_eye, right_eye, left_ear, right_ear, left_shoulder, right_shoulder, left_elbow,
right_elbow, left_wrist, right_wrist, left_hip, right_hip, left_knee, right_knee, left_ankle, right_ankle

Virtual reference points: waist_midpoint, chest_midpoint, torso_center, head_center

Short names (when `per_side=true`): wrist, elbow, shoulder, hip, knee, ankle, eye, ear

## Volume Mount for Config

To customize patterns without rebuilding, mount configuration into `/app/config`.

Docker run example:

```bash
docker run ... -v ./config:/app/config:ro intel/behavioral-analysis:latest
```

Docker Compose already includes this mount in the project configuration.
