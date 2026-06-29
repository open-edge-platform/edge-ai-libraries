# Example: Download an Ollama Model

## Scenario

Pull `llama3.2:3b` from Ollama for local LLM inference.

---

## Step 1 — Set Up Service

```bash
cd edge-ai-libraries/microservices/model-download
export REGISTRY="intel/"
export TAG=latest

source scripts/run_service.sh up --plugins ollama --model-path $PWD/models
```

---

## Step 2 — Submit Download Job

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=ollama-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "llama3.2",
        "hub": "ollama",
        "revision": "3b"
      }
    ]
  }'
```

The `revision` field is appended as a tag: `llama3.2:3b`.

---

## Step 3 — Poll Status

```bash
JOB_ID=<uuid>
curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool
```

Download typically takes 5–20 minutes depending on model size and network speed.

Output path: `$PWD/models/ollama/llama3.2/3b/`

---

## Common Ollama Models

| Model name | `revision` | Notes |
|-----------|------------|-------|
| `llama3.2` | `3b`, `1b` | Meta Llama 3.2 |
| `llama3.1` | `8b`, `70b` | Meta Llama 3.1 |
| `mistral` | `latest`, `7b` | Mistral 7B |
| `codellama` | `7b`, `13b`, `34b` | Code-focused Llama |
| `phi3` | `mini`, `medium` | Microsoft Phi-3 |
| `gemma2` | `2b`, `9b` | Google Gemma 2 |

---

## Download Without a Specific Tag

Omit `revision` to pull the `latest` tag:

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=ollama-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "mistral",
        "hub": "ollama"
      }
    ]
  }'
```

---

## Note on Parallel Downloads

Ollama downloads are serialized — if you submit multiple Ollama jobs simultaneously,
they queue and execute one at a time. This is by design to avoid port conflicts with
the local Ollama server.
