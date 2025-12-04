# API Reference

**Version: 1.0.0**

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

**Request Parameters**
Request parameters for the summarization endpoint

- **video**: *Required.*. Path to the video file, support 'file:/', 'http://', 'https://' and local path.
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
  "video_duration": 0
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
