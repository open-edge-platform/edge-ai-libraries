# API Reference

**Version: 1.0.0**

<!--hide_directive```{eval-rst}
.. swagger-plugin:: ./_assets/openapi.yaml
```hide_directive-->

When running the service, you can access the Swagger UI documentation at:

```bash
http://{service-ip}:8192/docs
```

## 1. Health API
**GET /v1/health**

**Description:**
Health check endpoint.

**Response:**
A response indicating the service status, version and a descriptive message.

**Response Example Value**

```json
{
  "message": "Service is running smoothly.",
  "status": "healthy",
  "version": "1.0.0"
}
```

## 2. Models API

**GET /v1/models**

**Description:**
Get a list of available Whisper model variants that can be used for summarization.

This endpoint returns all the llm & vlm models that are configured in the service and available for summarization requests, along with detailed information including display names, descriptions, and the default model that is used when no specific model is requested.

**Response:**
A response with the list of available models with their details and the default model

**Response Example Value**

```json
{
  "llms": [
    {
      "base_url": "http://localhost:41090/v1",
      "description": "Large Language Models for summarization",
      "display_name": "Qwen/Qwen3-32B-AWQ",
      "model_id": "Qwen/Qwen3-32B-AWQ"
    }
  ],
  "vlms": [
    {
      "base_url": "http://localhost:41091/v1",
      "description": "Vision and Language Models for summarization",
      "display_name": "Qwen/Qwen2.5-VL-7B-Instruct",
      "model_id": "Qwen/Qwen2.5-VL-7B-Instruct"
    }
  ]
}
```

## 3. Summarization API

**POST /v1/summary**

**Description:**
Generate a summary text from a video file to describe its content.

The endpoint accepts three input combinations:

- **Video only** — normal VLM captioning per chunk, then hierarchical LLM summary.
- **Video + subtitles** — VLM captioning with the matching subtitle text injected into each chunk prompt as extra context.
- **Subtitles only (caption-only)** — set `video` to `"none"` and provide `video_subtitles`; the VLM is skipped and each subtitle segment becomes a chunk description, then the LLM produces the summary/report. Useful for aggregating pre-built event logs (e.g. a day of motion events) into a report.

**Request Parameters**
Request parameters for the summarization endpoint

- **video**: *Required.*. Path to the video file, support 'file:/', 'http://', 'https://' and local path. Set to the string `"none"` for caption-only mode (requires `video_subtitles`).
- **video_subtitles**: *Optional*. Subtitles in SubRip (.srt) format, as one of `{"url": "https://..."}`, `{"text": "<srt>"}`, or `{"b64gzip": "<base64 of gzipped srt>"}`. Required when `video` is `"none"`. Inline/`b64gzip` inputs are capped by `MAX_SUBTITLE_BYTES`.
- **task**: *Optional*. Prompt task selecting the summarization flavor. Built-in values: `"summary"` (English, default) and `"summary_zh"` (Chinese). Any other value must be a dynamic task registered via the Prompt Tasks API (see section 4); unknown names are rejected.
- **prompt**: *Optional*. User prompt to guide summarization details.
- **method**: *Optional*. Summarization method, choices: ["SIMPLE", "USE_VLM_T-1", "USE_LLM_T-1", "USE_ALL_T-1"]. Default as *"USE_ALL_T-1"*. Each method definition:
  - **SIMPLE**: Simple summarization, do not incorporate time dependency between consecutive chunks
  - **USE_VLM_T-1**: Incorporate time dependency between consecutive chunks for VLM inference.
  - **USE_LLM_T-1**: Incorporate time dependency between consecutive chunks for LLM inference.
  - **USE_ALL_T-1**: Incorporate time dependency between consecutive chunks for both VLM and LLM inference.
- **processor_kwargs**: *Optional*. Summarization processing parameters. Currently supported items:
  - **process_fps**: Extract frames at process_fps for input video. Default as *1*.
  - **levels**: Specify total levels for hierarchical summarization. Default as *3*.
  - **level_sizes**: Specify chunk group size for each level, must match with `levels`. Default as *[1, 6, -1]*, -1 means using single group at the level.
  - **chunking_method**: video chunking algorithm, choices: ["pelt", "uniform"], Default as *"pelt"*. Call video-chunking-utils with specific method, pelt with scene-switch based video chunking; uniform with 15s duration for video chunking.

**Response**
A response with the processing status and summary output.

**Response Example Value**

- Successful Response. Code: 200

```json
{
  "status": "completed",
  "summary": "string",
  "message": "string",
  "job_id": "string",
  "video_name": "string",
  "video_duration": 0,
  "usage": {
    "prompt_tokens": 0,
    "image_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

- Bad Request. Code: 400

```json
{
  "details": "Invalid file format",
  "error_message": "Summarization failed!"
}
```

- Internal Server Error. Code: 500

```json
{
    "details":"An error occurred during Summarization. Please check logs for details.",
    "error_message":"Summarization failed!"
}
```

## 4. Prompt Tasks API

A **task** bundles the four prompt sections used across the summarization hierarchy:

- `GLOBAL_PROMPT` — final whole-video summary / report.
- `MACRO_CHUNK_PROMPT` — mid-level aggregation over a time range.
- `LOCAL_PROMPT` — per-chunk (per-clip) description.
- `T_MINUS_1_PROMPT` — previous-chunk context for temporal coherence.

Only two tasks are **built-in**: `summary` (English) and `summary_zh` (Chinese). Any other task is **dynamic** — registered at runtime through the endpoints below and persisted under the service cache directory (`VIDEO_SUMMARY_CACHE`, default `~/.cache/.multilevel-video-understanding/tasks/`). Built-in tasks cannot be modified or deleted.

**GET /v1/tasks** — list all tasks (built-in + dynamic).

```json
{
  "tasks": [
    {"name": "summary", "source": "builtin", "description": "General-purpose video summarization ..."},
    {"name": "summary_zh", "source": "builtin", "description": "General-purpose video summarization (Chinese prompts)."},
    {"name": "refrigerator_monitor_en", "source": "dynamic", "description": "Fridge monitor + daily report (EN)."}
  ]
}
```

**GET /v1/tasks/{name}** — return the four prompt sections for a task as a single anchor-style `content` string (round-trip safe: it can be re-submitted as `content.text`). Works for built-in and dynamic tasks.

**POST /v1/tasks** — register a new dynamic task. `task_name` must be lowercase ascii (`^[a-z][a-z0-9_]{1,63}$`) and must not collide with a built-in.

- `mode: "full"` — supply the four anchors yourself via `content`:

```json
{
  "task_name": "refrigerator_monitor_en",
  "mode": "full",
  "content": {
    "text": "GLOBAL_PROMPT = '''...'''\n\nMACRO_CHUNK_PROMPT = '''...{st_tm}...{end_tm}...'''\n\nLOCAL_PROMPT = '''...{st_tm}...{end_tm}...'''\n\nT_MINUS_1_PROMPT = '''...{dur}...{st_tm}...{end_tm}...{past_summary}...'''"
  }
}
```

  `content` may instead be `{"url": "https://.../task.txt"}` (HTTPS only, ≤ 256 KB, SSRF-protected). Required placeholders are auto-scaffolded when omitted, then the sections are render-validated before persisting.

- `mode: "autogen"` — the service's own LLM drafts all four sections from a natural-language `description`:

```json
{"task_name": "playground_safety", "mode": "autogen", "description": "Detect unsafe playground behavior for toddlers."}
```

Success returns `201` with the task detail (same shape as GET `/{name}`). Conflicts return `409` (`builtin_conflict` / `already_registered`); malformed content returns `400`/`422`.

**PATCH /v1/tasks/{name}** — rename (`new_task_name`), change `description`, and/or regenerate sections (`mode` + `description`/`content`). At least one field required. Built-ins return `403 builtin_immutable`.

**DELETE /v1/tasks/{name}** — delete a dynamic task (`204`). Built-ins return `403 builtin_immutable`; unknown names return `404`.
