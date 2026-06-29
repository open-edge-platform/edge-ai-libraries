# Example: VLM → OpenVINO Conversion

## Scenario

Convert a Vision Language Model (VLM) such as `llava-hf/llava-1.5-7b-hf` to OpenVINO IR
format for OVMS deployment.

---

## Step 1 — Set Up Service

```bash
cd edge-ai-libraries/microservices/model-download

export HUGGINGFACEHUB_API_TOKEN=hf_your_token_here
export REGISTRY="intel/"
export TAG=latest

source scripts/run_service.sh up --plugins huggingface,openvino --model-path $PWD/models
```

---

## Step 2 — Submit VLM Conversion Job

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=vlm-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "llava-hf/llava-1.5-7b-hf",
        "hub": "openvino",
        "type": "vlm",
        "config": {
          "precision": "int4",
          "device": "CPU",
          "cache_size": 8,
          "pipeline_type": "VLM_CB"
        }
      }
    ]
  }'
```

---

## Pipeline Type Options for VLMs

| `pipeline_type` | Use case |
|-----------------|---------|
| `VLM` | Standard VLM pipeline |
| `VLM_CB` | Continuous Batching (higher throughput, requires more memory) |
| `AUTO` | Let OVMS choose the best pipeline |

---

## Step 3 — Monitor and Verify

```bash
JOB_ID=<uuid>
watch -n 30 "curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool"
```

VLM conversions are memory-intensive. If the job fails with OOM:
- Reduce `cache_size`
- Switch to `int4` precision
- Try a smaller model

---

## Other Supported VLMs

| Model | HuggingFace ID |
|-------|----------------|
| InternVL | `OpenGVLab/InternVL2-2B` |
| Phi-3-Vision | `microsoft/Phi-3-vision-128k-instruct` |
| LLaVA-Next | `llava-hf/llava-v1.6-mistral-7b-hf` |

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=vlm-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "microsoft/Phi-3-vision-128k-instruct",
        "hub": "openvino",
        "type": "vlm",
        "config": {
          "precision": "int4",
          "device": "CPU"
        }
      }
    ]
  }'
```
