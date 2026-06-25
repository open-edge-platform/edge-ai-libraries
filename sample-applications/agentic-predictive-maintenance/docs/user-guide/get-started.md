# Get Started

The Agentic Predictive Maintenance (APM) blueprint lets you deploy an end-to-end industrial defect detection pipeline with AI-driven analysis on Intel edge hardware. This guide walks you through setting up, configuring, and running the application.

## Prerequisites

Before you start, make sure the following are in place:

- Docker ≥ 24.0 and Docker Compose ≥ 2.20
- Intel CPU with at least 16 GB RAM (32 GB recommended for LLM mode)
- Python 3.10 or later (only needed to prepare sample data)
- `opencv-python` Python package (only needed for the data preparation script)
- A Hugging Face account and API token if you plan to use a gated model such as `microsoft/Phi-4-mini-instruct`

Verify your system meets all [hardware and software requirements](./get-started/system-requirements.md) before continuing.

## Project Structure

```text
agentic-predictive-maintenance/
├── apps/
│   └── pipeline-defect-detection/     # Use-case configuration directory
│       ├── configs/
│       │   ├── agents.yaml            # Agent pipeline settings and defect thresholds
│       │   ├── pipeline-server-config.json  # DL Streamer pipeline and model paths
│       │   └── policy_fallback.json   # Rule-based fallback logic
│       ├── prompts/
│       │   └── pipeline-defect-detection.txt  # LLM prompt sections per agent
│       ├── models/                    # Model artifacts directory
│       └── resources/
│           └── videos/                # Input video files (place sample.mp4 here)
├── docker/                            # Docker Compose files
│   ├── compose.base.yaml              # Core services (nginx, storage, DL Streamer, MQTT)
│   ├── compose.agents.yaml            # Agent service
│   ├── compose.llm.yaml               # VLM/LLM inference service
│   ├── compose.ui.yaml                # Web dashboard
│   └── compose.telemetry.yaml         # Prometheus metrics collection
├── services/                          # Source code for the three new microservices
│   ├── storage-service/
│   ├── agent-service/
│   └── ui-service/
├── scripts/                           # Helper scripts
├── config/                            # Nginx and MQTT broker configuration
├── docs/                              # Documentation
├── .env_pipeline-defect-detection     # Environment configuration for the default use case
├── Makefile                           # Build and test targets
└── setup.sh                           # Main deployment script
```

## Step 1 — Clone the Repository

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/sample-applications/agentic-predictive-maintenance
```

## Step 2 — Configure the Environment

Open the use-case environment file and review the settings:

```bash
vi apps/pipeline-defect-detection/.env_pipeline-defect-detection
```

The most important variables are:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODE` | `llm` | Set to `fallback` to run without an LLM (rule-based mode) |
| `LLM_MODEL_NAME` | `microsoft/Phi-4-mini-instruct` | Language model used by the agent pipeline |
| `LLM_DEVICE` | `CPU` | Inference device: `CPU`, `GPU`, or `NPU` |
| `LLM_WEIGHT_FORMAT` | `int4` | Model quantization format: `fp32`, `fp16`, `int8`, or `int4` |
| `AUTO_RUN_ON_DETECTION` | `false` | Automatically trigger the agent pipeline after `AUTO_RUN_THRESHOLD` detections |
| `AUTO_RUN_THRESHOLD` | `100` | Number of detections that triggers an automatic agent run |

If you are using a gated Hugging Face model, you must set your API token:

```bash
# In .env_pipeline-defect-detection, uncomment and set:
HUGGINGFACEHUB_API_TOKEN=hf_your_token_here
```

> **Note**: Accept the model license agreement on the [Hugging Face model page](https://huggingface.co/microsoft/Phi-4-mini-instruct) before using gated models.

## Step 3 — Prepare Sample Data

The DL Streamer pipeline needs a video file to run. Use the included script to download the Kaggle pipeline-defect dataset and build a sample video automatically:

```bash
pip install opencv-python

python scripts/download_and_prep_data.py \
    "https://www.kaggle.com/api/v1/datasets/download/simplexitypipeline/pipeline-defect-dataset" \
    --use-case pipeline-defect-detection
```

This script:
- Downloads and extracts the dataset (~300 MB)
- Splits it into training and validation sets
- Builds `apps/pipeline-defect-detection/resources/videos/sample.mp4` for use by DL Streamer

> **Note**: Skip this step if you have your own video, or if you plan to run in `LLM_MODE=fallback` where no video or DL Streamer inference is required.

> **Disclaimer**: By running this script you acknowledge that you are solely responsible for the rights, permissions, and licenses associated with the dataset at the provided URL.

## Step 4 — Launch the Application

**LLM mode** (requires the VLM service; uses AI-generated analysis):

```bash
./setup.sh --use-case pipeline-defect-detection
```

**Fallback mode** (rule-based; no GPU or LLM service required):

```bash
LLM_MODE=fallback ./setup.sh --use-case pipeline-defect-detection
```

The setup script validates your environment, sources the use-case `.env` file, and starts all required services via Docker Compose.

### Verify the Deployment

Check that all containers started successfully:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

You should see the following containers running:

| Container | Role |
|-----------|------|
| `apm-nginx` | Reverse proxy |
| `apm-ui` | Web dashboard |
| `apm-agent` | Multi-agent orchestrator |
| `apm-storage` | Detection data store |
| `apm-dlstreamer` | Video inference |
| `apm-mqtt-broker` | MQTT broker |
| `apm-model-download` | Model download utility |
| `apm-vlm` | VLM/LLM service *(LLM mode only)* |

## Step 5 — Open the Dashboard

Navigate to `http://localhost:8080` in your browser. The dashboard displays:

- Live detection events from the video pipeline
- A log of all agent runs with status indicators
- Generated maintenance tickets with priority, description, and recommended action

## Stopping and Cleaning Up

Stop all running containers:

```bash
./setup.sh --stop
```

Stop containers and remove all stored detection data:

```bash
./setup.sh --clean-data
```

## Configuration Reference

All use-case behavior is controlled by four files in `apps/<use-case>/`:

| File | Purpose |
|------|---------|
| `configs/agents.yaml` | Agent pipeline settings, defect classes, confidence thresholds |
| `configs/pipeline-server-config.json` | DL Streamer pipeline definition and model paths |
| `configs/policy_fallback.json` | Rule-based fallback thresholds and escalation actions |
| `prompts/<use-case>.txt` | LLM prompt sections for each agent |

### agents.yaml

The `agents.yaml` file controls which defect classes are monitored and what confidence levels trigger alerts:

```yaml
use_case_id: pipeline-defect-detection   # must match the prompt file name
analysis:
  min_confidence: 0.5                    # detections below this threshold are filtered
policy:
  defect_classes: [Rupture, Deformation, Disconnect, Obstacle]
  alert_threshold: 0.7                   # confidence threshold for policy violations
  critical_classes: [Rupture, Disconnect]
```

### Prompt File Sections

LLM behavior is defined through prompt sections delimited by `[SECTION_NAME]` headers:

```
[SYSTEM]    — shared system role for all agents
[POLICY]    — instructions for the Policy Agent
[ANALYSIS]  — instructions for the Analysis Agent
[EVIDENCE]  — instructions for the Evidence Agent
[TICKETING] — instructions for the Ticketing Agent
```

## Creating a New Use Case

To adapt the blueprint to a different inspection scenario — for example, weld defect detection:

```bash
# Copy the existing use-case directory
cp -r apps/pipeline-defect-detection apps/weld-defect-detection

# Edit the four configuration files
vi apps/weld-defect-detection/configs/agents.yaml       # update use_case_id and defect classes
vi apps/weld-defect-detection/configs/policy_fallback.json
vi apps/weld-defect-detection/prompts/weld-defect-detection.txt

# Launch with the new use case
./setup.sh --use-case weld-defect-detection
```

No code changes are needed — the blueprint reads all behavior from the configuration files at startup.

<!--hide_directive
:::{toctree}
:hidden:

get-started/system-requirements
:::
hide_directive-->
