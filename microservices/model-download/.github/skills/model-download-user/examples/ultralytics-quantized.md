# Example: Ultralytics YOLO Models + INT8 Quantization

## Scenario

Download `yolov8n` from Ultralytics with INT8 quantization using the COCO128 dataset.

---

## Step 1 — Set Up Service

```bash
cd edge-ai-libraries/microservices/model-download
export REGISTRY="intel/"
export TAG=latest

source scripts/run_service.sh up --plugins ultralytics --model-path $PWD/models
```

---

## Step 2 — Download with INT8 Quantization

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=yolo-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "yolov8n",
        "hub": "ultralytics",
        "config": {
          "quantize": "coco128"
        }
      }
    ]
  }'
```

The `quantize` field specifies the calibration dataset for INT8 PTQ (Post-Training Quantization).

---

## Step 3 — Poll Status

```bash
JOB_ID=<uuid>
curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool
```

Output path: `$PWD/models/ultralytics/yolov8n/`

---

## Download Without Quantization

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=yolo-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "yolov8n",
        "hub": "ultralytics"
      }
    ]
  }'
```

---

## Common YOLO Model Names

| Model | Description |
|-------|-------------|
| `yolov8n` | YOLOv8 Nano (fastest, smallest) |
| `yolov8s` | YOLOv8 Small |
| `yolov8m` | YOLOv8 Medium |
| `yolov8l` | YOLOv8 Large |
| `yolov8x` | YOLOv8 Extra-large (most accurate) |
| `yolov9c` | YOLOv9 C variant |
| `yolov10n` | YOLOv10 Nano |
| `yolo_all` | All YOLO variants |
| `all` | All supported models |

---

## INT8 Quantization Rules

- `quantize` accepts a dataset name (e.g. `coco`, `coco128`)
- **Single model only** — `quantize` cannot be combined with `all`, `yolo_all`, or comma-separated names
- If INT8 artifacts are not generated (model doesn't support quantization), the job fails

---

## Batch Download (No Quantization)

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=yolo-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "yolov8n,yolov8s,yolov8m",
        "hub": "ultralytics"
      }
    ]
  }'
```
