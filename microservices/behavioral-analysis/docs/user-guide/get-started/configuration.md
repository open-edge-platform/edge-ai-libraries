# Configuration

The Behavioral Analysis Service is configured through two complementary mechanisms:

1. **Environment variables** — loaded via Pydantic `Settings` (from `src/config.py`).
2. **`config/patterns.yaml`** — defines behavioral patterns and VLM settings; can override some VLM env vars.

---

## Environment Variables

All variables are case-insensitive. Set them in your shell, in a `.env` file (for Docker Compose), or as container environment variables.

### Service Settings

| Variable | Default | Description |
|---|---|---|
| `DEBUG` | `false` | Enable debug mode |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Pose Model Settings

| Variable | Default | Description |
|---|---|---|
| `YOLO_POSE_MODEL` | `/models/yolo_models/yolo26n-pose/yolo26n-pose.xml` | Path to the YOLO-Pose OpenVINO IR model file (`.xml`) |
| `GST_INFERENCE_DEVICE` | `CPU` | OpenVINO inference device: `CPU`, `GPU`, or `NPU` |
| `POSE_CONFIDENCE_THRESHOLD` | `0.5` | Minimum mean keypoint confidence to accept a pose; frames below this threshold are discarded |

### Frame Analysis Settings

| Variable | Default | Description |
|---|---|---|
| `MIN_FRAMES_FOR_DETECTION` | `8` | Minimum number of frames required before analysis runs |
| `MAX_FRAMES_TO_FETCH` | `30` | Maximum frames to fetch from SeaweedFS per request |
| `POSE_FRAMES_COUNT` | `20` | Number of most-recent frames used for pose scoring (tail of the fetched list) |

> In Docker Compose, these are exposed via the `.env` variables `BA_MIN_FRAMES`, `BA_MAX_FRAMES`, and `BA_POSE_FRAMES`.

### SeaweedFS Settings

| Variable | Default | Description |
|---|---|---|
| `SEAWEEDFS_ENDPOINT` | `http://localhost:8333` | SeaweedFS S3-compatible endpoint URL |
| `SEAWEEDFS_BUCKET` | `behavioral-frames` | Bucket name for frame storage |
| `SEAWEEDFS_ACCESS_KEY` | _(empty)_ | S3 access key (omit for anonymous access) |
| `SEAWEEDFS_SECRET_KEY` | _(empty)_ | S3 secret key (omit for anonymous access) |

### VLM Settings

VLM settings can be set via environment variables **or** overridden in `config/patterns.yaml` under `vlm_settings`. The YAML values take precedence over environment variables when present.

| Variable | Default | Description |
|---|---|---|
| `VLM_ENABLED` | `true` | Enable VLM visual confirmation after pose match |
| `VLM_ENDPOINT` | `http://ovms-vlm:8001` | OpenAI-compatible VLM endpoint URL |
| `VLM_MODEL_NAME` | `Qwen/Qwen2.5-VL-7B-Instruct` | Model name passed in the VLM API request |
| `VLM_TIMEOUT` | `300.0` | HTTP request timeout in seconds for VLM calls |
| `VLM_MAX_TOKENS` | `50` | Maximum tokens in VLM response |
| `VLM_TEMPERATURE` | `0.1` | Sampling temperature for VLM generation |
| `VLM_MAX_IMAGE_SIZE` | `256` | Maximum image dimension (px) before resizing frames for VLM |
| `VLM_MAX_CONCURRENCY` | `1` | Maximum concurrent in-flight VLM requests |

### MQTT Settings

| Variable | Default | Description |
|---|---|---|
| `MQTT_HOST` | `broker.scenescape.intel.com` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `BA_REQUEST_TOPIC` | `ba/requests` | MQTT topic the service subscribes to for incoming requests |
| `BA_RESULT_TOPIC` | `ba/results` | MQTT topic the service publishes results to |

### Pattern Configuration

| Variable | Default | Description |
|---|---|---|
| `PATTERN_CONFIG_PATH` | `/app/config/patterns.yaml` | Path to the pattern YAML config file inside the container |

---

## `.env` File (Docker Compose)

The `.env` file at the project root provides default values for Docker Compose variable substitution. Copy it to customize:

```bash
cp .env .env.local
```

```dotenv
# Release
RELEASE_TAG=latest

# SeaweedFS
SEAWEEDFS_ENDPOINT=http://seaweedfs:8333
SEAWEEDFS_BUCKET=behavioral-frames

# VLM
VLM_ENDPOINT=http://ovms-vlm:8001

# MQTT
MQTT_HOST=broker.scenescape.intel.com
MQTT_PORT=1883

# Behavioral Analysis service
BA_SERVICE_PORT=8085
BA_MIN_FRAMES=3
BA_MAX_FRAMES=120
BA_POSE_FRAMES=60
BA_CONFIDENCE=0.5
BA_GST_DEVICE=CPU
VLM_ENABLED=true
BA_REQUEST_TOPIC=ba/requests
BA_RESULT_TOPIC=ba/results
DOWNLOADED_MODEL_PATH=../../../models
```

---

## Pattern Configuration (`config/patterns.yaml`)

Behavioral patterns are defined in YAML. The service loads this file on startup from the path specified by `PATTERN_CONFIG_PATH`. The file can be updated and the container restarted without rebuilding the image.

### VLM Settings Block

```yaml
vlm_settings:
  endpoint: "http://ovms-vlm:8001"
  model_name: "Qwen/Qwen2.5-VL-7B-Instruct"
  enabled: true
  timeout: 30.0
  max_tokens: 50
  temperature: 0.1
  max_image_size: 256
  max_concurrency: 1
```

> Values set here override the corresponding environment variables at startup.

### Pattern Definition Structure

```yaml
patterns:
  <pattern_id>:
    description: "Human-readable description"
    enabled: true | false
    alert_type: <string>        # Metadata label for downstream consumers

    pose:
      per_side: true | false    # When true, conditions use left_/right_ variants
      min_pose_confidence: 0.3  # Per-pattern keypoint confidence override
      min_confidence_for_alert: 0.30  # Minimum pose match ratio to trigger alert
      phases:
        - name: <phase_name>
          min_frames: <int>     # Required matching frames in this phase
          conditions:
            - subject: <keypoint_name>
              relation: <relation>
              reference: <keypoint_name> | <list> | <virtual_point>
              # Additional relation-specific fields (min_angle, max_angle, threshold)

    vlm:
      enabled: true | false
      num_frames: 4             # Frames sampled for VLM
      confidence_threshold: 0.7
      prompt: |
        <freeform prompt text>
      response_fields:
        - reasoning
        - suspicious
        - confidence
```

### Available Keypoint Names (COCO 17)

`nose`, `left_eye`, `right_eye`, `left_ear`, `right_ear`, `left_shoulder`, `right_shoulder`, `left_elbow`, `right_elbow`, `left_wrist`, `right_wrist`, `left_hip`, `right_hip`, `left_knee`, `right_knee`, `left_ankle`, `right_ankle`

**Virtual reference points:** `waist_midpoint`, `chest_midpoint`, `torso_center`, `head_center`

**Short names (when `per_side: true`):** `wrist`, `elbow`, `shoulder`, `hip`, `knee`, `ankle`, `eye`, `ear` — evaluated for both `left_` and `right_` sides independently.

### Available Relations

| Relation | Description | Extra Fields |
|---|---|---|
| `above` | subject Y < reference Y | — |
| `below` | subject Y > reference Y | — |
| `left_of` | subject X < reference X | — |
| `right_of` | subject X > reference X | — |
| `near` | distance < `threshold` × torso length | `threshold: float` |
| `far` | distance > `threshold` × torso length | `threshold: float` |
| `moving_fast` | velocity between frames exceeds threshold | — |
| `stationary` | velocity between frames is below threshold | — |
| `bent` | joint angle at vertex within `[min_angle, max_angle]` degrees | `reference: [a, vertex, c]`, `min_angle`, `max_angle` |
| `straight` | joint angle outside `[min_angle, max_angle]` | same as `bent` |
| `not_<relation>` | negation of any relation above | — |

### Built-in Pattern: `shelf_to_waist`

```yaml
patterns:
  shelf_to_waist:
    description: "Hand takes item from shelf and conceals it against body"
    enabled: true
    alert_type: CONCEALMENT
    pose:
      per_side: true
      min_pose_confidence: 0.3
      min_confidence_for_alert: 0.30
      phases:
        - name: arm_handling_near_body
          min_frames: 20
          conditions:
            - subject: elbow
              relation: bent
              reference: [shoulder, wrist]
              min_angle: 20
              max_angle: 165
            - subject: wrist
              relation: near
              reference: waist_midpoint
              threshold: 0.40
    vlm:
      enabled: true
      num_frames: 4
      confidence_threshold: 0.7
      prompt: |
        You are a loss-prevention analyst. ...
      response_fields:
        - reasoning
        - suspicious
        - confidence
```

---

## Volume Mount for Config

To customize patterns without rebuilding the image, mount the config directory:

```bash
docker run ... -v ./config:/app/config:ro intel/behavioral-analysis:latest
```

In Docker Compose, this mount is already configured:

```yaml
volumes:
  - ./behavioral-analysis/config:/app/config:ro
```
