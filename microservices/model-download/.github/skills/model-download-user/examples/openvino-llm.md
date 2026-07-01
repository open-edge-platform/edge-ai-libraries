# Example: LLM → OpenVINO Conversion

## Scenario

Download `meta-llama/Llama-3.2-1B` from HuggingFace and convert it to OpenVINO IR format
(INT4 precision, CPU target) for deployment with OpenVINO Model Server (OVMS).

---

## Step 1 — Set Up Service

```bash
cd edge-ai-libraries/microservices/model-download

export HUGGINGFACEHUB_API_TOKEN=hf_your_token_here
export REGISTRY="intel/"
export TAG=latest

# Both huggingface (download) and openvino (convert) plugins are required
source scripts/run_service.sh up --plugins huggingface,openvino --model-path $PWD/models
```

Verify health:
```bash
curl http://localhost:8200/api/v1/health
```

---

## Step 2 — Submit Conversion Job

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=llm-converted" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.2-1B",
        "hub": "openvino",
        "type": "llm",
        "config": {
          "precision": "int4",
          "device": "CPU",
          "cache_size": 4
        }
      }
    ]
  }'
```

**Alternative — Download + Convert in one request (using `is_ovms`):**
```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=llm-converted" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.2-1B",
        "hub": "huggingface",
        "type": "llm",
        "is_ovms": true,
        "config": {
          "precision": "int4",
          "device": "CPU",
          "cache_size": 4
        }
      }
    ]
  }'
```

---

## Step 3 — Monitor Progress

Conversion takes 10–30 minutes depending on model size and hardware.

```bash
JOB_ID=<uuid>
# Watch status every 30 seconds
watch -n 30 "curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool"
```

Status flow: `queued` → `converting` → `completed`

---

## Step 4 — Verify Output

```bash
curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool
```

Converted model location: `$PWD/models/openvino_models/CPU/int4/`

---

## Precision Options for LLMs

| Precision | Tradeoff |
|-----------|---------|
| `int4` | Smallest size, fastest inference, slight quality loss |
| `int8` | Good balance of size and quality |
| `fp16` | Near-original quality, 2× larger than int8 |
| `fp32` | Full precision, largest, slowest |

---

## Advanced: Custom Quantization Parameters

For more control over quantization (e.g., symmetric quantization, custom group size):

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=llm-custom" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.2-1B",
        "hub": "openvino",
        "type": "llm",
        "config": {
          "precision": "int4",
          "device": "CPU",
          "cache_size": 4,
          "extra_quantization_params": "--sym --group-size -1 --ratio 1.0 --awq"
        }
      }
    ]
  }'
```

---

## NPU Deployment

For NPU, `int4` is required and enforced automatically:

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=llm-npu" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.2-1B",
        "hub": "openvino",
        "type": "llm",
        "config": {
          "precision": "int4",
          "device": "NPU"
        }
      }
    ]
  }'
```
