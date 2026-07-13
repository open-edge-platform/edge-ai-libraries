# API Reference

<!--hide_directive```{eval-rst}
.. swagger-plugin:: api-docs/openapi.yaml
```hide_directive-->

Base URL: `http://localhost:8000` (default; configurable via `EMBEDDING_SERVER_PORT`).

All endpoints return JSON. The `POST /embeddings` endpoint accepts a JSON body describing the input modality and returns a vector embedding.

## `GET /health`

Health check endpoint.

**Response:**

- 200 OK:

  ```json
  {
      "status": "healthy"
  }
  ```

- 500 Internal Server Error:

  ```json
  {
      "detail": "Model is not healthy"
  }
  ```

## `GET /models`

List all available models and their configurations.

**Response:**

- 200 OK:

  ```json
  {
      "current_model": "CLIP/clip-vit-b-16",
      "available_models": {
          "MobileCLIP": ["mobileclip_s0", "mobileclip_s1", "mobileclip_s2", "mobileclip_b", "mobileclip_blt"],
          "CLIP": ["clip-vit-b-32", "clip-vit-b-16", "clip-vit-l-14", "clip-vit-h-14"],
          "CN-CLIP": ["cn-clip-vit-b-16", "cn-clip-vit-l-14", "cn-clip-vit-h-14"],
          "SigLIP": ["siglip2-vit-b-16", "siglip2-vit-l-16", "siglip2-so400m-patch16-384"],
          "Blip2": ["blip2_transformers"],
          "QwenText": ["qwen3-embedding-0.6b", "qwen3-embedding-4b", "qwen3-embedding-8b"]
      },
      "total_models": 19
  }
  ```

- 500 Internal Server Error:

  ```json
  {
      "detail": "Error listing models: <error_message>"
  }
  ```

## `GET /model/current`

Returns the name and runtime configuration of the currently loaded model.

**Response:**

- 200 OK:

  ```json
  {
      "model": "CLIP/clip-vit-b-16",
      "device": "CPU",
      "use_openvino": false
  }
  ```

## `GET /model/capabilities`

Returns the supported input modalities of the currently loaded model.

**Response:**

- 200 OK:

  ```json
  {
      "model": "CLIP/clip-vit-b-16",
      "modalities": ["text", "image"],
      "supports_text": true,
      "supports_image": true,
      "supports_video": false
  }
  ```

- 503 Service Unavailable:

  ```json
  {
      "detail": "Model is not initialized"
  }
  ```

## `POST /embeddings`

Generates an embedding vector for the provided input. The `input` field is a typed union — set `type` to select the input modality.

**Request Body:**

```json
{
    "model": "<model_name>",
    "input": { "<input_object>" },
    "encoding_format": "float"
}
```

| Field             | Required | Description                                                    |
| ----------------- | -------- | -------------------------------------------------------------- |
| `model`           | Yes      | Must match the currently loaded model (e.g. `CLIP/clip-vit-b-16`). |
| `input`           | Yes      | Typed input object; see input types below.                     |
| `encoding_format` | Yes      | Encoding format for the returned vector (e.g. `float`).        |

### Input Types

#### Text (`type: "text"`)

Embed a single string or a batch of strings.

```json
{
    "type": "text",
    "text": "A photo of a cat"
}
```

```json
{
    "type": "text",
    "text": ["A photo of a cat", "A photo of a dog"]
}
```

| Field  | Required | Description                           |
| ------ | -------- | ------------------------------------- |
| `type` | Yes      | `"text"`                              |
| `text` | Yes      | A single string or a list of strings. |

#### Image URL (`type: "image_url"`)

Download and embed an image from a URL.

```json
{
    "type": "image_url",
    "image_url": "https://example.com/photo.jpg"
}
```

| Field       | Required | Description        |
| ----------- | -------- | ------------------ |
| `type`      | Yes      | `"image_url"`      |
| `image_url` | Yes      | URL of the image.  |

#### Image Base64 (`type: "image_base64"`)

Embed an image provided as a base64-encoded string.

```json
{
    "type": "image_base64",
    "image_base64": "<base64_encoded_image>"
}
```

| Field          | Required | Description                    |
| -------------- | -------- | ------------------------------ |
| `type`         | Yes      | `"image_base64"`               |
| `image_base64` | Yes      | Base64-encoded image data.     |

#### Video Frames (`type: "video_frames"`)

Embed a video represented as an ordered list of individual frames. Each frame is either an image URL or a base64-encoded image.

```json
{
    "type": "video_frames",
    "video_frames": [
        {"type": "image_url", "image_url": "https://example.com/frame1.jpg"},
        {"type": "image_base64", "image_base64": "<base64_frame>"}
    ]
}
```

| Field         | Required | Description                                                        |
| ------------- | -------- | ------------------------------------------------------------------ |
| `type`        | Yes      | `"video_frames"`                                                   |
| `video_frames`| Yes      | List of frame objects, each typed `image_url` or `image_base64`.   |

#### Video URL (`type: "video_url"`)

Download and embed a video from a URL with frame extraction settings.

```json
{
    "type": "video_url",
    "video_url": "https://example.com/video.mp4",
    "segment_config": {
        "startOffsetSec": 0,
        "clip_duration": -1,
        "num_frames": 64
    }
}
```

| Field            | Required | Description                                    |
| ---------------- | -------- | ---------------------------------------------- |
| `type`           | Yes      | `"video_url"`                                  |
| `video_url`      | Yes      | URL of the video.                              |
| `segment_config` | Yes      | Dictionary controlling frame extraction (see `segment_config` keys below). |

#### Video Base64 (`type: "video_base64"`)

Embed a video provided as a base64-encoded string.

```json
{
    "type": "video_base64",
    "video_base64": "<base64_encoded_video>",
    "segment_config": {
        "startOffsetSec": 0,
        "clip_duration": -1,
        "num_frames": 64
    }
}
```

| Field            | Required | Description                              |
| ---------------- | -------- | ---------------------------------------- |
| `type`           | Yes      | `"video_base64"`                         |
| `video_base64`   | Yes      | Base64-encoded video data.               |
| `segment_config` | Yes      | Dictionary controlling frame extraction (see `segment_config` keys below). |

#### Video File (`type: "video_file"`)

Embed a local video file by its path on the server.
Place the video file in `/tmp/videoQnA/` directory.

```json
{
    "type": "video_file",
    "video_path": "<file_name>.mp4",
    "segment_config": {
        "startOffsetSec": 0,
        "clip_duration": -1,
        "num_frames": 64
    }
}
```

| Field            | Required | Description                              |
| ---------------- | -------- | ---------------------------------------- |
| `type`           | Yes      | `"video_file"`                           |
| `video_path`     | Yes      | Absolute path to the video file.         |
| `segment_config` | Yes      | Dictionary controlling frame extraction (see `segment_config` keys below). |

#### `segment_config` Keys

The `segment_config` dictionary controls how frames are extracted from video inputs. All keys are optional.

| Key               | Type              | Default | Description                                                                 |
| ----------------- | ----------------- | ------- | --------------------------------------------------------------------------- |
| `startOffsetSec`  | integer           | `0`     | Start offset in seconds from the beginning of the video.                   |
| `clip_duration`   | integer           | `-1`    | Duration in seconds to extract. `-1` processes the full video.             |
| `num_frames`      | integer           | `64`    | Number of frames to uniformly sample (lowest priority).                    |
| `extraction_fps`  | float             | `null`  | Extract frames at this rate (frames per second). Takes priority over `num_frames`. |
| `frame_indexes`   | array of integers | `null`  | Explicit list of frame indices to extract (highest priority).              |

Priority order when multiple keys are set: `frame_indexes` > `extraction_fps` > `num_frames`.

#### Frames Batch (`type: "frames_batch"`)

Embed pre-extracted frames described by a manifest JSON file. The manifest must conform to the `FramesManifest` schema — a list of `FrameInfo` objects each with `frame_number`, `timestamp`, `image_path`, and `type` fields.

```json
{
    "type": "frames_batch",
    "frames_manifest_path": "/data/manifests/frames.json"
}
```

| Field                  | Required | Description                                   |
| ---------------------- | -------- | --------------------------------------------- |
| `type`                 | Yes      | `"frames_batch"`                              |
| `frames_manifest_path` | Yes      | Absolute path to the frames manifest JSON.    |

### Responses

- 200 OK — text or image input returns a flat embedding vector:

  ```json
  {
      "embedding": [0.021, -0.134, 0.452, "..."]
  }
  ```

  Video inputs (`video_frames`, `video_url`, `video_base64`, `video_file`, `frames_batch`) return one embedding per extracted frame:

  ```json
  {
      "embedding": [
          [0.021, -0.134, 0.452, "..."],
          [0.011, -0.201, 0.318, "..."]
      ]
  }
  ```

- 400 Bad Request — model mismatch or unsupported modality:

  ```json
  {
      "detail": "Model mismatch: requested model 'X' does not match the currently loaded model 'Y'. Please use the correct model name or restart the server with the desired model."
  }
  ```

- 404 Not Found — video or manifest file not found:

  ```json
  {
      "detail": "File not found: <path>"
  }
  ```

- 422 Unprocessable Entity — invalid input data or failed validation:

  ```json
  {
      "detail": "Invalid input data: <error_message>"
  }
  ```

- 500 Internal Server Error:

  ```json
  {
      "detail": "Error creating embedding: <error_message>"
  }
  ```

- 503 Service Unavailable — model not yet initialized:

  ```json
  {
      "detail": "Model is not initialized"
  }
  ```

### Examples

**Text embedding:**

```bash
curl -X POST http://localhost:8000/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "CLIP/clip-vit-b-16",
    "input": {"type": "text", "text": "A photo of a cat"},
    "encoding_format": "float"
  }'
```

**Image embedding from URL:**

```bash
curl -X POST http://localhost:8000/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "CLIP/clip-vit-b-16",
    "input": {"type": "image_url", "image_url": "https://example.com/photo.jpg"},
    "encoding_format": "float"
  }'
```

**Video embedding from file:**

Place the video in `/tmp/videoQnA/` directory.

```bash
curl -X POST http://localhost:8000/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "CLIP/clip-vit-b-16",
    "input": {
      "type": "video_file",
      "video_path": "sample.mp4",
      "segment_config": {"num_frames": 64, "startOffsetSec": 0, "clip_duration": -1}
    },
    "encoding_format": "float"
  }'
```

## Interactive API Documentation

When the service is running, FastAPI provides interactive docs:

- **Swagger UI**: `http://<HOST_IP>:<EMBEDDING_SERVER_PORT>/docs`
- **ReDoc**: `http://<HOST_IP>:<EMBEDDING_SERVER_PORT>/redoc`
- **OpenAPI JSON**: `http://<HOST_IP>:<EMBEDDING_SERVER_PORT>/openapi.json`

With default settings:

```bash
http://<HOST_IP>:9777/docs
http://<HOST_IP>:9777/redoc
http://<HOST_IP>:9777/openapi.json
```

Replace `<HOST_IP>` with the hostname or IP of the machine running MME.

## Using the OpenAPI Spec with Bruno

For tooling and collection generation, import the checked-in spec:

- File: `docs/user-guide/api-docs/openapi.yaml`
- Bruno: **Collections → Import OpenAPI** and select the YAML file

This is the recommended source for reproducible API collections in CI/local workflows.

## Supporting Resources

- [Get Started](./get-started.md)
- [Supported models](./supported-models.md)
