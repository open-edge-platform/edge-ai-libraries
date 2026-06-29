# Example: Pipeline Zoo Models

## Scenario

Download DL Streamer pipeline-zoo models for use with Intel DL Streamer pipelines.

---

## Step 1 — Set Up Service

```bash
cd edge-ai-libraries/microservices/model-download
export REGISTRY="intel/"
export TAG=latest

source scripts/run_service.sh up --plugins pipeline-zoo-models --model-path $PWD/models
```

---

## Step 2 — Download a Single Model

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=pipeline-zoo" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "person-vehicle-bike-detection-2004",
        "hub": "pipeline-zoo-models"
      }
    ]
  }'
```

---

## Download Multiple Models

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=pipeline-zoo" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "person-vehicle-bike-detection-2004,vehicle-license-plate-detection-barrier-0106",
        "hub": "pipeline-zoo-models"
      }
    ]
  }'
```

---

## Download All Pipeline Zoo Models

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=pipeline-zoo" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "all",
        "hub": "pipeline-zoo-models"
      }
    ]
  }'
```

---

## Step 3 — Poll Status

```bash
JOB_ID=<uuid>
curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool
```

First download fetches the pipeline-zoo-models repository archive from GitHub and caches it.
Subsequent downloads reuse the cache.

Output path: `$PWD/models/pipeline-zoo-models/<model-name>/`

---

## Common Pipeline Zoo Models

| Model name | Task |
|------------|------|
| `person-vehicle-bike-detection-2004` | Person/vehicle/bike detection |
| `vehicle-license-plate-detection-barrier-0106` | License plate detection |
| `age-gender-recognition-retail-0013` | Age and gender recognition |
| `emotions-recognition-retail-0003` | Facial emotion recognition |
| `face-detection-retail-0004` | Face detection |
| `pedestrian-detection-adas-0002` | Pedestrian detection |
| `road-segmentation-adas-0001` | Road segmentation |

All models are in OpenVINO IR format, ready for DL Streamer pipelines.
