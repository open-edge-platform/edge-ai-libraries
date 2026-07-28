# API v1 Test Guide

## Overview

This directory contains comprehensive tests for the `/api/v1/analyze/batch` endpoint:

- **`generate_test_video.py`**: Generates a 20-second synthetic video showing suspicious shelf-to-pocket concealment behavior
- **`test_api_v1_direct.py`**: Complete test suite with 10+ test cases covering success paths, error handling, and edge cases

## Quick Start

### 1. Generate Test Video and Frames

```bash
cd tests/
python generate_test_video.py
```

**Output:**
- `test_video_suspicious.mp4` - 20-second video file
- `test_frames/` directory with ~200 extracted frames (JPEG)

The video simulates:
- **0-5s**: Person standing in front of shelf
- **5-10s**: Person reaching up to shelf
- **10-15s**: Person picking item from shelf
- **15-20s**: Person concealing item and standing normally

### 2. Start the Behavioral Analysis Service

In a separate terminal:

```bash
cd /path/to/behavioral-analysis/

# Install dependencies (if not already done)
pip install -r requirements.txt

# Start the service
python -m uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

Wait for:
```
INFO:     Application startup complete
```

### 3. Run the Tests

```bash
cd tests/

# Install pytest if not already installed
pip install pytest requests

# Run all tests
pytest test_api_v1_direct.py -v

# Run specific test
pytest test_api_v1_direct.py::TestAPI::test_01_successful_suspicious_detection -v

# Run with detailed output
pytest test_api_v1_direct.py -v -s
```

## Test Cases

### TestAPI Class (10 test cases)

| Test | Purpose | Expected Result |
|------|---------|-----------------|
| `test_01_successful_suspicious_detection` | End-to-end suspicious activity detection | HTTP 200, status="suspicious" or "no_match" |
| `test_02_pose_detection` | Verify pose extraction from frames | HTTP 200, pose_detected=bool |
| `test_03_vlm_confirmation_enabled` | API behavior with VLM enabled | HTTP 200, vlm_confirmed present if matched |
| `test_04_vlm_confirmation_disabled` | API behavior with VLM disabled | HTTP 200, pose-only detection |
| `test_05_no_frames_error` | Error handling when no frames provided | HTTP 400/422 |
| `test_06_invalid_frame_format` | Error handling for corrupted frames | HTTP 422 |
| `test_07_request_id_tracking` | Request tracking with custom request_id | HTTP 200, logged with request_id prefix |
| `test_08_multiple_patterns` | Different pattern types | HTTP 200 for all patterns |
| `test_09_response_structure` | Response schema validation | All required fields present and typed correctly |
| `test_10_performance_benchmark` | Performance with varying frame counts | Response time logged for 3, 5, 10, 15 frames |

### TestIntegration Class (1 test case)

| Test | Purpose | Expected Result |
|------|---------|-----------------|
| `test_e2e_suspicious_activity_detection` | Full pipeline test | HTTP 200, complete response |

## API Endpoint Reference

**POST /api/v1/analyze/batch**

### Request (Multipart Form-Data)

```bash
curl -X POST http://localhost:8080/api/v1/analyze/batch \
  -F "entity_id=test_person_001" \
  -F "scene_id=test_scene" \
  -F "region_id=test_zone" \
  -F "pattern_id=shelf_to_waist" \
  -F "vlm_enabled=false" \
  -F "request_id=req_custom_001" \
  -F "frames=@test_frames/frame_000.jpg" \
  -F "frames=@test_frames/frame_001.jpg" \
  -F "frames=@test_frames/frame_002.jpg"
```

### Response (JSON)

```json
{
  "entity_id": "test_person_001",
  "scene_id": "test_scene",
  "status": "suspicious",
  "pose_detected": true,
  "frames_submitted": 3,
  "confidence": 0.85,
  "message": "Suspicious shelf-to-waist movement detected",
  "vlm_confirmed": null,
  "vlm_reasoning": null
}
```

## Expected Behavior

### Video Generation

The synthetic video shows a simple stick figure person:
1. Standing in front of a brown shelf with red items
2. Reaching up to the shelf (hand moves up)
3. Picking an item (hand at shelf level)
4. Bringing item down to waist/pocket level (**key suspicious phase**)
5. Concealing item and standing normally

### API Test Behavior

- **With pose detection**: `pose_detected=true`, analysis based on keypoint sequences
- **With pattern matching**: If pose sequence matches "shelf_to_waist", `status="suspicious"`
- **With VLM enabled**: If pattern matched, sends frames to Claude-vision for confirmation
- **With VLM disabled**: Skips LLM confirmation, uses only pose-based detection

## Troubleshooting

### Issue: "Service not running at http://localhost:8080"

**Solution**: Start the service in another terminal:
```bash
cd /path/to/behavioral-analysis/
python -m uvicorn src.main:app --host 0.0.0.0 --port 8080
```

### Issue: "Test frames not found"

**Solution**: Generate frames first:
```bash
cd tests/
python generate_test_video.py
```

### Issue: "Pose not detected"

**Reason**: Synthetic video may not contain realistic human pose keypoints detected by YOLO-Pose.

**Solution**: 
- Test framework will log `pose_detected=false` but continue with other test cases
- For production testing, use real video footage of actual shelf-to-pocket behavior
- Check YOLO-Pose model is loaded: `curl http://localhost:8080/health`

### Issue: Tests timeout after 60 seconds

**Solution**: Increase timeout or check service performance:
```bash
# Check service logs for errors
tail -f /var/log/behavioral-analysis.log

# Reduce frame count for quick test
pytest test_api_v1_direct.py::TestAPI::test_02_pose_detection -v
```

## File Structure

```
tests/
├── generate_test_video.py          # Synthetic video generator (20s)
├── test_api_v1_direct.py           # Comprehensive test suite
├── test_pose_analyzer.py           # Existing pose analyzer tests
└── test_frames/                    # Generated frames directory
    ├── frame_000.jpg
    ├── frame_001.jpg
    └── ...
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: API Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: pip install -r requirements.txt pytest requests
      
      - name: Generate test frames
        run: cd tests && python generate_test_video.py
      
      - name: Start service
        run: python -m uvicorn src.main:app --host 127.0.0.1 --port 8080 &
        timeout-minutes: 2
      
      - name: Run API tests
        run: pytest tests/test_api_v1_direct.py -v
```

## Performance Baseline

Expected response times (on typical hardware):
- 3 frames: 5-10 seconds
- 5 frames: 8-15 seconds
- 10 frames: 15-30 seconds
- 15 frames: 20-40 seconds

*(Depends on VLM enabled, model inference speed, frame resolution)*

## Next Steps

1. ✅ Run `python generate_test_video.py` to create synthetic test data
2. ✅ Start the BA service with the new v1 endpoint
3. ✅ Execute `pytest test_api_v1_direct.py -v` to run full test suite
4. 📊 Review test results and response times
5. 🔄 For real-world testing, replace synthetic video with actual shelf footage

---

**Questions?** Check the test file docstrings or review the main.py `/api/v1/analyze/batch` endpoint implementation.
