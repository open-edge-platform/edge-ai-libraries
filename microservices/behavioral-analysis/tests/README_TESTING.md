# API v1 Batch Test Guide

## Overview

This directory contains integration-style tests for the batch REST endpoint:

- Endpoint: `/api/v1/analyze/batch`
- Test file: `test_api_v1_direct.py`

Current automated API suite in `test_api_v1_direct.py` contains 3 main tests:

1. `test_01_vlm_confirmation_enabled`
2. `test_02_vlm_confirmation_disabled`
3. `test_03_no_match_non_suspicious_frames`

---

## Prerequisites

- Behavioral Analysis service running and reachable on `http://localhost:8085`
- Test frames available in `tests/test_frames/`
- Python environment with test dependencies installed (`pytest`, `requests`, `numpy`)

---

## 1) Prepare Test Frames

Prepare frames from a real video into `tests/test_frames`.

Example (extract every 1 second from 0s to 32s):

```bash
cd tests
# Use your preferred frame extraction tool/script
# and place output frames in tests/test_frames
```

Expected output naming pattern:

- `test_frames/frame_000_0.0s.jpg`
- `test_frames/frame_001_1.0s.jpg`
- ...

The test suite uses frame ranges:

- Suspicious path tests: frames `0..23`
- No-match test: frames `25..29` (Python slice end is exclusive)

---

## 2) Start the Service

For complete startup instructions (deployment modes, Docker Compose, and host run), follow the existing get-started docs:

- `docs/user-guide/get-started.md`
- `docs/user-guide/get-started/run-container.md`
- `docs/user-guide/get-started/run-standalone.md`

---

## 3) Run the Tests

```bash
cd tests
pytest test_api_v1_direct.py -v
```

Run a single test:

```bash
pytest test_api_v1_direct.py::TestAPI::test_01_vlm_confirmation_enabled -v -s
```

---

## Test Case Summary

| Test | Purpose | Expected Behavior |
|---|---|---|
| `test_01_vlm_confirmation_enabled` | Validate VLM path when pose pattern matches | HTTP 200, `status="suspicious"`, `vlm_confirmed` is boolean |
| `test_02_vlm_confirmation_disabled` | Validate pose-only path | HTTP 200, `vlm_confirmed is None`, status in `pose_not_detected/no_match/suspicious` |
| `test_03_no_match_non_suspicious_frames` | Negative test on non-concealment window | HTTP 200, `status="no_match"`, `frames_submitted` equals uploaded frame count |

---

## API Contract Used by Tests

### Request (multipart/form-data)

Required fields:

- `entity_id`
- `frames` (one or more image files)

Optional fields:

- `pattern_id` (default: `shelf_to_waist`)
- `vlm_enabled` (`true` or `false`)
- `request_id`

Example:

```bash
curl -X POST "http://localhost:8085/api/v1/analyze/batch" \
  -F "entity_id=test_person_001" \
  -F "pattern_id=shelf_to_waist" \
  -F "vlm_enabled=false" \
  -F "request_id=req_custom_001" \
  -F "frames=@test_frames/frame_000_0.0s.jpg" \
  -F "frames=@test_frames/frame_001_1.0s.jpg"
```

### Response Fields

The response contains:

- `entity_id`
- `status`
- `pose_detected`
- `frames_submitted`
- `confidence`
- `message`
- `vlm_confirmed`
- `vlm_reasoning`

Possible `status` values for this endpoint:

- `pose_not_detected`
- `no_match`
- `suspicious`

Example:

```json
{
  "entity_id": "test_person_001",
  "status": "no_match",
  "pose_detected": true,
  "frames_submitted": 2,
  "confidence": 0.0,
  "message": "No suspicious pattern detected",
  "vlm_confirmed": null,
  "vlm_reasoning": null
}
```

---

## Troubleshooting

### Service not reachable

Symptom:

- Tests skip/fail due to connection errors on `http://localhost:8085`

Fix:

```bash
python -m uvicorn src.main:app --host 0.0.0.0 --port 8085
```

### Test frames not found

Symptom:

- `test_frames` folder missing or empty

Fix:

```bash
cd tests
# Generate/extract frames into tests/test_frames using your preferred workflow
```

### Unexpected `pose_not_detected`

Reason:

- Uploaded frames did not yield reliable poses (quality, angle, occlusion, or model/runtime issues)

Fix:

- Use clearer person-centric frames
- Verify YOLO model mount/path and service health
- Increase frame count for the suspicious window

### VLM confirmation not populated in test_01

Reason:

- VLM service not reachable or VLM path not triggered by pose match

Fix:

- Ensure OVMS/VLM is up and reachable from BA service
- Confirm suspicious test frames actually match the configured pattern

---

## Notes

- This README reflects the current `test_api_v1_direct.py` test set and `/api/v1/analyze/batch` contract.