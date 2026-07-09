# Example: Healthcare AI Models (HLS Plugin)

## Scenario

Download pre-converted OpenVINO IR models for Intel Health & Life Sciences (HLS) demos:
3D pose estimation, remote photoplethysmography (rPPG), and AI-ECG.

---

## Supported Model Types

| Type | Model(s) | Application |
|------|----------|-------------|
| `3d-pose` | `human-pose-estimation-3d-0001` | 3D human body pose estimation |
| `rppg` | `mtts_can` | Heart rate estimation from video (rPPG) |
| `ai-ecg` | `ecg_17920_ir10_fp16`, `ecg_8960_ir10_fp16` | ECG signal classification |

---

## Step 1 — Set Up Service

```bash
cd edge-ai-libraries/microservices/model-download
export REGISTRY="intel/"
export TAG=latest

source scripts/run_service.sh up --plugins hls --model-path $PWD/models
```

> **First run:** The HLS plugin builds a dedicated Python virtual environment on first use.
> This takes 10–30 minutes and installs `openvino`, `torch`, `torchvision`, and `tensorflow`.
> Subsequent runs reuse the cached venv.

---

## Step 2 — Download 3D Pose Models

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=hls-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "hls-3d-pose",
        "hub": "hls",
        "type": "3d-pose"
      }
    ]
  }'
```

---

## Step 3 — Download rPPG Models

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=hls-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "hls-rppg",
        "hub": "hls",
        "type": "rppg"
      }
    ]
  }'
```

---

## Step 4 — Download AI-ECG Models

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=hls-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "hls-ai-ecg",
        "hub": "hls",
        "type": "ai-ecg"
      }
    ]
  }'
```

---

## Step 5 — Monitor Progress

```bash
JOB_ID=<uuid>
curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool
```

Output paths:
- 3D pose: `$PWD/models/hls/3d-pose/`
- rPPG: `$PWD/models/hls/rppg/`
- AI-ECG: `$PWD/models/hls/ai-ecg/`

---

## Download All Three in One Request

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=hls-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {"name": "hls-3d-pose", "hub": "hls", "type": "3d-pose"},
      {"name": "hls-rppg",    "hub": "hls", "type": "rppg"},
      {"name": "hls-ai-ecg",  "hub": "hls", "type": "ai-ecg"}
    ]
  }'
```

This returns three job IDs and downloads run in parallel (venv is shared after first creation).
