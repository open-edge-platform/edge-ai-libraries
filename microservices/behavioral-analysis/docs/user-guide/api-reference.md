# API Reference

This section documents the REST API endpoint for batch frame analysis.

## 1. Endpoint Overview

The batch analysis endpoint accepts multiple uploaded image frames in a single request, runs pose extraction and pattern detection, and optionally runs VLM confirmation for matched suspicious behavior.

## 2. HTTP Method and URL

- Method: `POST`
- URL: `/api/v1/analyze/batch`
- Content-Type: `multipart/form-data`

## 3. Headers

| Header | Required | Value | Description |
|---|---|---|---|
| `Content-Type` | Yes | `multipart/form-data` | Required for form fields and image file uploads |
| `Accept` | No | `application/json` | Recommended response content type |

## 4. Request Body

The request body must be sent as multipart form-data.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_id` | `string` | Yes | - | Unique entity identifier |
| `pattern_id` | `string` | No | `shelf_to_waist` | Pattern to detect |
| `vlm_enabled` | `boolean` | No | `null` | Optional override for global VLM enable setting |
| `request_id` | `string` | No | Auto-generated | Optional request tracking ID for logs |
| `frames` | `file[]` | Yes | - | One or more image frames (JPEG/PNG/WebP). Max 5 MB per file |

Validation notes:

- At least one frame file is required.
- If no valid images can be decoded, the request fails.

## 5. Request Example

### cURL example

```bash
curl -X POST "http://localhost:8085/api/v1/analyze/batch" \
  -H "Accept: application/json" \
  -F "entity_id=entity_001" \
  -F "pattern_id=shelf_to_waist" \
  -F "vlm_enabled=true" \
  -F "request_id=req_entity_001_001" \
  -F "frames=@frame_000_0.0s.jpg" \
  -F "frames=@frame_001_1.0s.jpg" \
  -F "frames=@frame_002_2.0s.jpg"
```

## 6. Response

On success, the endpoint returns an `AnalyzeDirectResponse` JSON object.

| Field | Type | Nullable | Description |
| --- | --- | --- | --- |
| `entity_id` | `string` | No | Entity identifier from request |
| `status` | `string` | No | Analysis result status |
| `pose_detected` | `boolean` | No | Whether pose extraction produced at least one pose |
| `frames_submitted` | `integer` | No | Number of valid decoded frames used for analysis |
| `confidence` | `number` | Yes | Pattern confidence score |
| `message` | `string` | No | Human-readable result detail |
| `vlm_confirmed` | `boolean` | Yes | VLM confirmation result when VLM path is used |
| `vlm_reasoning` | `string` | Yes | Reasoning text returned from VLM when available |

Possible `status` values:

- `pose_not_detected` (used when no poses are detected from submitted frames)
- `no_match`
- `suspicious`

## 7. Response Example

### Suspicious example

```json
{
  "entity_id": "entity_001",
  "status": "suspicious",
  "pose_detected": true,
  "frames_submitted": 24,
  "confidence": 0.78,
  "message": "[left] Phase 'arm_handling_near_body': 12/24 frames matched",
  "vlm_confirmed": true,
  "vlm_reasoning": "The person appears to place an item near the waist area."
}
```

### No match example

```json
{
  "entity_id": "entity_001",
  "status": "no_match",
  "pose_detected": true,
  "frames_submitted": 6,
  "confidence": 0.0,
  "message": "No suspicious pattern detected",
  "vlm_confirmed": null,
  "vlm_reasoning": null
}
```

## 8. HTTP Status Codes

| Status Code | Meaning | When Returned |
|---|---|---|
| `200` | OK | Request processed successfully (includes `suspicious`, `no_match`, or `pose_not_detected` response statuses) |
| `400` | Bad Request | No frames provided |
| `422` | Unprocessable Entity | All uploaded frames invalid or undecodable |
| `500` | Internal Server Error | Unexpected analysis/runtime failure |

## 9. Error Response Format

Errors from this endpoint are returned in FastAPI HTTPException format with a `detail` payload.

General error shape:

```json
{
  "detail": {
    "error_code": "STRING_CODE",
    "message": "Human-readable message",
    "invalid_frames": [
      [0, "Frame 0 exceeds 5MB limit"],
      [1, "Frame 1 is not a valid image format"]
    ]
  }
}
```

Field behavior:

- `error_code`: Machine-readable error category
- `message`: Human-readable error summary
- `invalid_frames`: Present only for invalid frame decode/validation cases

### Error example: no frames provided (`400`)

```json
{
  "detail": {
    "error_code": "NO_FRAMES_PROVIDED",
    "message": "At least 1 frame required"
  }
}
```

### Error example: no valid frames (`422`)

```json
{
  "detail": {
    "error_code": "INVALID_FRAMES",
    "message": "No valid frames could be decoded",
    "invalid_frames": [
      [0, "Frame 0 is not a valid image format"]
    ]
  }
}
```

### Error example: internal error (`500`)

```json
{
  "detail": {
    "error_code": "INTERNAL_ERROR",
    "message": "Analysis failed: <error summary>"
  }
}
```