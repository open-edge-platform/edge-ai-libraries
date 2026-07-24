# Example: Download a HuggingFace Model

## Scenario

Use the service for two common HuggingFace cases:

- a **public** embeddings model: `sentence-transformers/all-MiniLM-L6-v2`
- a **gated** Llama model: `meta-llama/Llama-3.2-1B`

The request shape is the same for both. The main difference is whether you need a token.

---

## Step 1 — Start the Service

```bash
cd edge-ai-libraries/microservices/model-download

export REGISTRY="intel/"
export TAG=latest

# Needed for gated models. Public models can omit this.
export HUGGINGFACEHUB_API_TOKEN=hf_your_token_here

source scripts/run_service.sh up --plugins huggingface --model-path $PWD/models
```

Health check:

```bash
curl -s http://localhost:8200/api/v1/health
```

**Token note:**

- For the standard Docker Compose startup path, export `HUGGINGFACEHUB_API_TOKEN`
- Docker maps that host variable into the container as `HF_TOKEN`
- public models do **not** require a token
- gated models like Llama require both a token and accepted license terms on Hugging Face

---

## Step 2 — Download a Public Model

```bash
JOB_RESPONSE=$(curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=embeddings" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "hub": "huggingface"
      }
    ]
  }')

echo "$JOB_RESPONSE"
JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)[\"job_ids\"][0])")
```

---

## Step 3 — Download a Gated Model

First, accept the license at:
`https://huggingface.co/meta-llama/Llama-3.2-1B`

```bash
JOB_RESPONSE=$(curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=llm" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.2-1B",
        "hub": "huggingface"
      }
    ]
  }')

echo "$JOB_RESPONSE"
JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)[\"job_ids\"][0])")
```

If the token is missing or the license was not accepted, the job usually ends in `failed`
with an auth-related error.

---

## Step 4 — Poll Job Status

```bash
curl -s "http://localhost:8200/api/v1/jobs/$JOB_ID" | python3 -m json.tool
```

Typical job flow:

`queued` → `downloading` → `completed`

Example completed result:

```json
{
  "job_id": "<uuid>",
  "model_name": "sentence-transformers/all-MiniLM-L6-v2",
  "status": "completed",
  "result": {
    "model_name": "sentence-transformers/all-MiniLM-L6-v2",
    "source": "huggingface",
    "download_path": "models/huggingface",
    "success": true
  }
}
```

---

## Step 5 — Where the Files Land

The returned `download_path` is the hub root. The actual model folder is created underneath it:

- `$PWD/models/huggingface/sentence-transformers_all-MiniLM-L6-v2/`
- `$PWD/models/huggingface/meta-llama_Llama-3.2-1B/`

---

## Variant — Pin a Specific Revision

Use `revision` when you want reproducible downloads in CI or automation:

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
