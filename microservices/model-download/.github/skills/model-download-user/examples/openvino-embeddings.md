# Example: Embedding Model → OpenVINO for OVMS

## Scenario

Convert `sentence-transformers/all-MiniLM-L6-v2` to OpenVINO embeddings format for
deployment with OVMS in a RAG (Retrieval Augmented Generation) pipeline.

---

## Step 1 — Set Up Service

```bash
cd edge-ai-libraries/microservices/model-download

export HUGGINGFACEHUB_API_TOKEN=hf_your_token_here  # may not be needed for public models
export REGISTRY="intel/"
export TAG=latest

source scripts/run_service.sh up --plugins huggingface,openvino --model-path $PWD/models
```

---

## Step 2 — Convert Embedding Model

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=embedding-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "hub": "openvino",
        "type": "embeddings",
        "config": {
          "precision": "int8",
          "device": "CPU"
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

Output path: `$PWD/models/openvino_models/CPU/int8/`

---

## Reranker Model Conversion

For reranker models used in RAG re-ranking stages:

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=reranker-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "hub": "openvino",
        "type": "rerank",
        "config": {
          "precision": "int8",
          "device": "CPU"
        }
      }
    ]
  }'
```

---

## Common Embedding Models

| Model | HuggingFace ID | Dimensions |
|-------|----------------|------------|
| MiniLM-L6-v2 | `sentence-transformers/all-MiniLM-L6-v2` | 384 |
| BGE-small-en | `BAAI/bge-small-en-v1.5` | 384 |
| BGE-large-en | `BAAI/bge-large-en-v1.5` | 1024 |
| E5-small | `intfloat/e5-small-v2` | 384 |

---

## Additional Embedding Parameters

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=embedding-advanced" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "BAAI/bge-large-en-v1.5",
        "hub": "openvino",
        "type": "embeddings",
        "config": {
          "precision": "int8",
          "device": "CPU",
          "normalize": true,
          "truncate": true,
          "num_streams": 2
        }
      }
    ]
  }'
```

| Config field | Effect |
|-------------|--------|
| `normalize` | Normalize embeddings (skip if model does it internally) |
| `truncate` | Truncate input to max sequence length |
| `num_streams` | Parallel inference streams |
