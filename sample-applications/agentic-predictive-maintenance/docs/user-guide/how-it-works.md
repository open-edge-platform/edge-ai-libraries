# How It Works

This page describes the end-to-end flow of the Agentic Predictive Maintenance Blueprint so you can verify and debug each stage independently.

---

## System Overview

```
Video File
    │
    ▼
DL Streamer (YOLO inference)
    │  MQTT: dlstreamer/detections
    ▼
Agent Service (MQTT subscriber)
    │  REST: POST /detections
    ▼
Storage Service (SQLite)
    │  REST: GET /detections
    ▼
Meta-Agent (LangGraph)
 ├─ Policy Agent
 ├─ Analysis Agent
 ├─ Evidence Agent
 └─ Ticketing Agent
    │
    ▼
UI (Nginx → UI Service)
```

---

## Stage 1 — Startup

Run the setup script with a use case:

```bash
source setup.sh --use-case pipeline-defect-detection
```

- Validates the environment and resolves `USE_CASE_*` paths from `apps/<use-case>/`
- Sources `.env_<use-case>` for model/device/mode settings
- Runs `docker compose up -d` for all services

Services started:

| Container | Role |
|-----------|------|
| `apm-mqtt-broker` | Mosquitto MQTT broker |
| `apm-model-download` | Downloads detection model on first run |
| `apm-dlstreamer` | Video inference (DL Streamer + YOLO) |
| `apm-storage` | SQLite REST API for detections |
| `apm-agent` | Multi-agent orchestrator |
| `apm-ui` | Web dashboard |
| `apm-nginx` | Reverse proxy (`localhost:8080`) |
| `apm-vlm` *(LLM mode only)* | LLM service for agent reasoning |

**Verify all containers are running:**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

---

## Stage 2 — Video Inference (DL Streamer → MQTT)

DL Streamer runs a YOLO model against `sample.mp4` and publishes detections to MQTT.

**Start the pipeline** (done automatically by `setup.sh` if `sample.mp4` exists):

```bash
curl -X POST http://localhost:8554/pipelines/user_defined_pipelines/pipeline_defect_detection \
  -H "Content-Type: application/json" -d '{}'
```

**Verify inference is running:**

```bash
docker logs -f apm-dlstreamer
```

**Verify MQTT messages are flowing:**

```bash
docker exec apm-mqtt-broker mosquitto_sub -t 'dlstreamer/detections'
```

Each message is a JSON payload with `label`, `confidence`, `bbox`, `frame_id`, and `timestamp`.

---

## Stage 3 — Detection Storage (MQTT → SQLite)

The agent service subscribes to `dlstreamer/detections` on startup and writes every detection to the storage service.

**Verify detections are being stored:**

```bash
# Recent detections
curl http://localhost:5001/detections?limit=5

# Aggregate stats
curl http://localhost:5001/stats
```

Expected `stats` response:

```json
{
  "total": 120,
  "by_class": {"Rupture": 30, "Deformation": 55, "Disconnect": 10, "Obstacle": 25},
  "avg_confidence": 0.74
}
```

---

## Stage 4 — Triggering the Agent Pipeline

The multi-agent pipeline can be triggered in two ways:

### Manual trigger (recommended for testing)

```bash
curl -X POST http://localhost:8080/api/agents/runs \
  -H "Content-Type: application/json" -d '{}'
```

Returns:

```json
{"run_id": "abc123", "status": "started"}
```

### Auto-trigger

Set `AUTO_RUN_ON_DETECTION=true` in the use-case `.env` file. The agent pipeline fires automatically after each MQTT detection batch is saved.

---

## Stage 5 — Multi-Agent Reasoning (LangGraph)

The meta-agent runs four agents **sequentially** via a LangGraph state machine. All agents read from the storage service.

### Agent 1 — Policy Agent

Reads `agents.yaml` thresholds and the latest detections. Determines which defect classes triggered policy violations.

- `Rupture` or `Disconnect` above threshold → **HIGH** priority alert
- Uses `policy_fallback.json` rules in fallback mode (no LLM call)

### Agent 2 — Analysis Agent

Filters detections by `min_confidence` (default `0.5`). Produces:
- Dominant defect class and counts
- Confidence distribution
- Temporal trend across frame IDs
- Clustering of bounding box regions

### Agent 3 — Evidence Agent

Builds a formal audit trail:
- Total frames inspected vs. frames with detections
- Per-class counts and confidence statistics
- Top-5 highest-confidence detections per class
- Compliance status: **PASS** / **FAIL**

### Agent 4 — Ticketing Agent

Synthesises outputs from Policy and Analysis agents. Produces a structured JSON maintenance ticket:

```json
{
  "priority": "HIGH",
  "title": "Rupture detected in pipeline segment A3",
  "description": "...",
  "affected_component": "segment-A3",
  "recommended_action": "HALT_PIPELINE",
  "estimated_resolution_time": "4 hours",
  "tags": "Rupture, Disconnect"
}
```

### LLM vs. Fallback Mode

| Mode | How agents reason |
|------|-------------------|
| `LLM_MODE=llm` | Agents send prompts to the VLM/LLM service; responses are LLM-generated |
| `LLM_MODE=fallback` | Agents apply rule-based logic from `policy_fallback.json`; no LLM service needed |

Set the mode when starting:

```bash
# Fallback (rule-based, no GPU/LLM required)
LLM_MODE=fallback source setup.sh --use-case pipeline-defect-detection

# LLM mode (requires VLM service)
source setup.sh --use-case pipeline-defect-detection
```

---

## Stage 6 — Viewing Results

### Check a specific run

```bash
# List all runs
curl http://localhost:8080/api/agents/runs

# Get a specific run result
curl http://localhost:8080/api/agents/runs/<run_id>
```

### Web UI

Open `http://localhost:8080` in a browser. The dashboard shows:
- Live detection feed
- Run history with status
- Generated maintenance tickets

---

## Quick Verification Checklist

Run these commands in order after startup to verify each stage:

```bash
# 1. All containers healthy?
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. Detections stored?
curl http://localhost:5001/stats

# 3. Agent service reachable?
curl http://localhost:8080/api/agents/runs

# 4. Trigger one agent run
RUN_ID=$(curl -s -X POST http://localhost:8080/api/agents/runs \
  -H "Content-Type: application/json" -d '{}' | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
echo "Run ID: $RUN_ID"

# 5. Check run result (wait ~10s for completion)
sleep 10
curl http://localhost:8080/api/agents/runs/$RUN_ID

# 6. View ticket in result JSON
curl http://localhost:8080/api/agents/runs/$RUN_ID | python3 -m json.tool
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| No detections in storage | `docker logs apm-dlstreamer` — is pipeline running? Is `sample.mp4` present? |
| Agent run stays `in_progress` | `docker logs apm-agent` |
| UI shows no runs | `curl http://localhost:8080/api/agents/runs` — nginx proxy OK? |
| VLM service unhealthy | Use `LLM_MODE=fallback` to bypass VLM for testing |
| `apm-storage` unhealthy | `docker logs apm-storage` — check port 5001 |

For data preparation (creating `sample.mp4`):

```bash
python scripts/download_and_prep_data.py <dataset_url> --use-case pipeline-defect-detection
```
