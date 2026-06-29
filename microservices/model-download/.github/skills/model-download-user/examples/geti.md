# Example: Download from Intel Geti

## Scenario

Download a trained object detection model from an Intel Geti server in optimized
OpenVINO IR format.

---

## Step 1 — Set Up Environment and Service

Get these values from your Geti server (Settings → API Access):

```bash
export GETI_HOST=https://geti.example.com
export GETI_TOKEN=<your-api-token>
export GETI_WORKSPACE_ID=<your-workspace-id>
export GETI_SERVER_SSL_VERIFY=False   # if using a self-signed cert
export REGISTRY="intel/"
export TAG=latest

cd edge-ai-libraries/microservices/model-download
source scripts/run_service.sh up --plugins geti --model-path $PWD/models
```

---

## Step 2 — Submit Download Job

### Download Latest Optimized Model

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=geti-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "my-detection-project",
        "hub": "geti",
        "config": {
          "export_type": "optimized"
        }
      }
    ]
  }'
```

### Download Base (PyTorch) Model

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=geti-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "my-detection-project",
        "hub": "geti",
        "config": {
          "export_type": "base"
        }
      }
    ]
  }'
```

### Download Specific Model Version

If you know the model group and optimized model IDs from the Geti API:

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=geti-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "my-detection-project",
        "hub": "geti",
        "config": {
          "export_type": "optimized",
          "model_group_id": "<model-group-uuid>",
          "optimized_model_id": "<optimized-model-uuid>",
          "model_only": true
        }
      }
    ]
  }'
```

---

## Step 3 — Poll and Verify

```bash
JOB_ID=<uuid>
curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool
```

Output path: `$PWD/models/geti/<project-id>/<model-id>/`

Downloaded artifacts are typically in OpenVINO IR format (`.xml` + `.bin` files).

---

## Export Type Reference

| `export_type` | What you get |
|--------------|-------------|
| `optimized` | OpenVINO IR model (INT8 or FP16 depending on your Geti training setup) |
| `base` | Base framework model (PyTorch `.pth` format) |

Use `optimized` for OVMS deployment; use `base` if you need to fine-tune further.

---

## Finding Model IDs via Geti API

```bash
# List projects in your workspace
curl -s -H "Authorization: Bearer $GETI_TOKEN" \
  "$GETI_HOST/api/v1/workspaces/$GETI_WORKSPACE_ID/projects"

# List models in a project
curl -s -H "Authorization: Bearer $GETI_TOKEN" \
  "$GETI_HOST/api/v1/workspaces/$GETI_WORKSPACE_ID/projects/<project-id>/model_groups"
```
