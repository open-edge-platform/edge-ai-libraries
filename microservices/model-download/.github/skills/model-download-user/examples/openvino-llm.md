# Example: LLM → OpenVINO Conversion

## Scenario

Download `meta-llama/Llama-3.2-1B` and convert it into an OVMS-ready OpenVINO model:

- `hub: "openvino"`
- `type: "llm"`
- `is_ovms: true`
- `precision: "int4"`
- `device: "CPU"`
- `cache_size: 4`

This is the recommended request shape for the current `/models/download` flow when the
user wants an OpenVINO / OVMS artifact.

---

## Step 1 — Start the Service

```bash
cd edge-ai-libraries/microservices/model-download

export REGISTRY="intel/"
export TAG=latest
export HUGGINGFACEHUB_API_TOKEN=hf_your_token_here

source scripts/run_service.sh up --plugins huggingface,openvino --model-path $PWD/models
curl -s http://localhost:8200/api/v1/health
```

Plugins are required:
- `openvino` for conversion

---

## Step 2 — Submit the Conversion Job

```bash
JOB_RESPONSE=$(curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=llm-converted" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.2-1B",
        "hub": "openvino",
        "type": "llm",
        "is_ovms": true,
        "config": {
          "precision": "int4",
          "device": "CPU",
          "cache_size": 4
        }
      }
    ]
  }')

echo "$JOB_RESPONSE"
JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)[\"job_ids\"][0])")
```

---

## Step 3 — Watch Progress

```bash
watch -n 30 "curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool"
```

Typical flow:

`queued` → `converting` → `completed`

Large LLM conversions can take a while. That is expected.

---

## Step 4 — Verify the Output

```bash
curl -s "http://localhost:8200/api/v1/jobs/$JOB_ID" | python3 -m json.tool
```

On success, the converted model is typically stored under:

`$PWD/models/openvino_models/CPU/int4/`

The job result includes a host-visible `conversion_path` you can mount into OVMS.

> Even though the OpenVINO plugin performs the conversion, the request should currently be sent as
> a HuggingFace model with `is_ovms: true`.

---

## Precision Notes

| Precision | Typical use |
|-----------|-------------|
| `int4` | Smallest footprint, common choice for LLM deployment |
| `int8` | Balance of size and quality |
| `fp16` | Higher fidelity, larger model |
| `fp32` | Largest and slowest, rarely preferred for edge deployment |

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
        "is_ovms": true,
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
        "is_ovms": true,
        "config": {
          "precision": "int4",
          "device": "NPU"
        }
      }
    ]
  }'
```

## NPU Note

If the user targets `NPU`, the service forces `int4` automatically.
