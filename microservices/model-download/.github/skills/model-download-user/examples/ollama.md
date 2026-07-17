# Example: Download an Ollama Model

## Scenario

Pull `llama3.2:3b` through the model-download REST API.

For Ollama, the tag goes in `revision`, not in `name`.

---

## Step 1 — Start the Service

```bash
cd edge-ai-libraries/microservices/model-download
export REGISTRY="intel/"
export TAG=latest

source scripts/run_service.sh up --plugins ollama --model-path $PWD/models
curl -s http://localhost:8200/api/v1/health
```

---

## Step 2 — Submit the Download Job

```bash
JOB_RESPONSE=$(curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=ollama-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "hub": "ollama",
        "name": "llama3.2",
        "revision": "3b"
      }
    ]
  }')

echo "$JOB_RESPONSE"
JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)[\"job_ids\"][0])")
```

**Important field mapping:**

- `hub` must be `ollama`
- `name` is the base model family, for example `llama3.2`
- `revision` is the tag, for example `3b`

Do **not** send:

```json
{"name": "llama3.2:3b"}
```

---

## Step 3 — Poll the Job

```bash
curl -s "http://localhost:8200/api/v1/jobs/$JOB_ID" | python3 -m json.tool
```

Typical job flow:

`queued` → `downloading` → `completed`

Ollama pulls can take several minutes depending on model size and network speed.

---

## Step 4 — Where the Model Is Stored

The job result points to the Ollama model store managed by the service. In a local setup,
you will typically see artifacts under a path like:

`$PWD/models/ollama/llama3.2/3b/`

---

## Variant — Pull the Default Tag

If you omit `revision`, Ollama pulls `latest`:

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=ollama-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "hub": "ollama",
        "name": "mistral"
      }
    ]
  }'
```

---

## Note on Parallel Requests

Ollama downloads are serialized inside the service. If you queue multiple Ollama jobs,
they run one at a time to avoid conflicts with the embedded Ollama server.
