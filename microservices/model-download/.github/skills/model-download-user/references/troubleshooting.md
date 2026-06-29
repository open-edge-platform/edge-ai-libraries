# Troubleshooting Guide

Common failures and how to diagnose them.

---

## Plugin Not Activated

**Symptom:** Job status `failed` with error like:
> `Plugin 'huggingface' was not activated during container startup. Active plugins: ollama`

**Cause:** The service was started without the required plugin enabled.

**Fix:** Restart the service with the correct `--plugins` flag:
```bash
source scripts/run_service.sh down
source scripts/run_service.sh up --plugins huggingface,openvino --model-path $PWD/models
```

To see which plugins are currently active:
```bash
curl -s http://localhost:8200/api/v1/plugins | python3 -m json.tool
```

---

## HuggingFace Authentication Errors

**Symptom:** Job fails with `401 Unauthorized` or `403 Forbidden` or:
> `Repository ... is gated`

**Fix:**
1. Create a HuggingFace token at https://huggingface.co/settings/tokens (read access is enough)
2. Accept the model's license agreement on the HF model page
3. Set the token before starting the service:
   ```bash
   export HUGGINGFACEHUB_API_TOKEN=hf_...
   source scripts/run_service.sh up --plugins huggingface --model-path $PWD/models
   ```

The token is picked up from the `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` environment variable.

---

## Job Stuck in "downloading" or "converting"

**Symptom:** Job status remains `downloading` or `converting` indefinitely.

**Diagnosis:**
```bash
# Check service logs
docker logs model-download 2>&1 | tail -50

# Verify the job status
curl -s http://localhost:8200/api/v1/jobs/<job-id> | python3 -m json.tool
```

**Common causes:**

| Cause | What to look for in logs |
|-------|--------------------------|
| Network timeout (large model) | No recent log output from plugin |
| Ollama server failed to start | `ollama serve` error in logs |
| OpenVINO conversion OOM | `Killed` or `MemoryError` in logs |
| Plugin venv not built | `ModuleNotFoundError` or venv-related errors |

**For OpenVINO OOM:** Reduce precision (try `int4` instead of `fp16`) or reduce `cache_size`.

**For Ollama stuck:** The Ollama plugin serializes downloads via a lock — if a previous job crashed mid-download, the lock may be held. Restart the container:
```bash
source scripts/run_service.sh down && source scripts/run_service.sh up --plugins ollama --model-path $PWD/models
```

---

## Job Status = "failed" — No Error Message

**Symptom:** `status: "failed"` but the `error` field is empty or generic.

**Fix:** Check the container logs for the full Python traceback:
```bash
docker logs model-download 2>&1 | grep -A 20 "ERROR\|Traceback\|Exception"
```

---

## OpenVINO Conversion Fails for NPU

**Symptom:** Conversion job fails when `device: "NPU"`.

**Cause:** NPU only supports `int4` precision. Other precisions are rejected.

**Fix:** Set `config.precision = "int4"`:
```json
{
  "name": "meta-llama/Llama-3.2-1B",
  "hub": "openvino",
  "type": "llm",
  "config": {
    "precision": "int4",
    "device": "NPU"
  }
}
```

---

## Geti Connection Errors

**Symptom:** Job fails with SSL error or `GETI_HOST not set`.

**Fix:**
1. Verify env vars are set before starting the service:
   ```bash
   echo $GETI_HOST $GETI_TOKEN $GETI_WORKSPACE_ID
   ```
2. If SSL verification is failing against a self-signed cert:
   ```bash
   export GETI_SERVER_SSL_VERIFY=False
   ```
3. Restart the service after setting env vars.

---

## HLS Plugin Slow on First Use

**Symptom:** HLS jobs take 10–30 minutes initially.

**Cause:** The HLS plugin builds a dedicated Python virtual environment (`/opt/hls_venv`) on first run,
installing `openvino`, `torch`, `torchvision`, `tensorflow`, and `tqdm`. Subsequent runs reuse the venv.

This is expected behavior — wait for completion.

---

## Ultralytics INT8 Fails / No Artifacts

**Symptom:** INT8 download completes but no INT8 artifacts found, job fails with:
> `INT8 export not supported for 'yolov8n' (dataset='coco128')`

**Common causes:**
- Dataset name is wrong (must match a valid YOLO calibration dataset)
- Model does not support INT8 quantization

**Fix:** Try with `coco` or `coco128` dataset. Only FP32 models can be quantized to INT8.
Remove the `quantize` field to download the default FP32/FP16 model instead.

---

## Port 8200 Already in Use

**Symptom:** Service fails to start with `address already in use`.

**Fix:**
```bash
# Find what's using port 8200
lsof -i :8200

# Stop the existing service
source scripts/run_service.sh down
```

---

## Model Already Exists / Partial Download

**Symptom:** Download completes instantly but the model seems incomplete.

**Cause:** A previous download may have left partial files.

**Fix for OpenVINO:** Set `config.overwrite_models: true` in the request:
```json
{
  "config": {
    "precision": "int8",
    "device": "CPU",
    "overwrite_models": true
  }
}
```

**Fix for other plugins:** Manually remove the directory and re-submit the job:
```bash
rm -rf $PWD/models/huggingface/model_name/
```

---

## Checking Service and Plugin Status

```bash
# Health
curl http://localhost:8200/api/v1/health

# Available plugins and their status
curl -s http://localhost:8200/api/v1/plugins | python3 -m json.tool

# All jobs (paginated)
curl -s http://localhost:8200/api/v1/jobs | python3 -m json.tool

# Specific job
curl -s http://localhost:8200/api/v1/jobs/<job-id> | python3 -m json.tool

# All completed models
curl -s http://localhost:8200/api/v1/models/results | python3 -m json.tool
```
