# Example: Download a HuggingFace Model

## Scenario

Download `sentence-transformers/all-MiniLM-L6-v2` (public, no token required) and
`meta-llama/Llama-3.2-1B` (gated, requires HF token and license agreement).

---

## Step 1 — Set Up Service

```bash
cd edge-ai-libraries/microservices/model-download

# Public model: no token needed
# Gated model: token required
export HUGGINGFACEHUB_API_TOKEN=hf_your_token_here
export REGISTRY="intel/"
export TAG=latest

source scripts/run_service.sh up --plugins huggingface --model-path $PWD/models
```

Verify:
```bash
curl http://localhost:8200/api/v1/health
# {"status": "ok"}
```

---

## Step 2 — Download Public Model

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=embeddings" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "hub": "huggingface"
      }
    ]
  }'
```

**Response:**
```json
{"job_ids": ["<uuid>"]}
```

---

## Step 3 — Download Gated Model (Llama)

First, accept the license at https://huggingface.co/meta-llama/Llama-3.2-1B.

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=llm" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.2-1B",
        "hub": "huggingface"
      }
    ]
  }'
```

---

## Step 4 — Poll Job Status

```bash
JOB_ID=<uuid-from-response>
curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool
```

**Completed response:**
```json
{
  "job_id": "<uuid>",
  "model_name": "sentence-transformers/all-MiniLM-L6-v2",
  "status": "completed",
  "result": {
    "source": "huggingface",
    "download_path": "models/huggingface/",
    "success": true
  }
}
```

---

## Result

Model files are stored at:
- `$PWD/models/huggingface/sentence-transformers_all-MiniLM-L6-v2/`
- `$PWD/models/huggingface/meta-llama_Llama-3.2-1B/`

---

## Pinning a Specific Revision

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=pinned" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "hub": "huggingface",
        "revision": "main"
      }
    ]
  }'
```
