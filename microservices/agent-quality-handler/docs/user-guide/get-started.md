# Get Started

The Agent Quality Handler is a standalone, configuration-driven agent service. It reads detections from an external storage API and runs the Policy, Analysis, Evidence, and Ticketing agents.

## Prerequisites

- Docker 24.0 or later with Docker Compose 2.20 or later

## Start

### 1. Clone the Microservice
Go to the target directory of your choice and clone the microservice. If you want to clone a specific release branch, replace main with the desired tag. To learn more on partial cloning, check the [Repository Cloning guide](https://docs.openedgeplatform.intel.com/dev/OEP-articles/contribution-guide.html#repository-cloning-partial-cloning).

```bash
git clone --filter=blob:none --sparse --branch main https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/
git sparse-checkout set microservices/agent-quality-handler/
cd microservices/agent-quality-handler/
```

### 2. Configure the environment variables

```bash
export REGISTRY="intel/"
export TAG=2026.2.0-rc1  
export STORAGE_SERVICE_URL=<storage-wrapper-service-url>    #Check mock service url below for validation
```

## Start in Fallback Mode

```bash
docker compose -f docker/compose.yaml up -d
```

Fallback mode is the default. It starts:

| Service | Purpose | Host exposure |
|---|---|---|
| `aqh-agent` | Agent REST API | Port `5002` |
| `mqtt-broker` | Batch-complete event transport | Private Compose network only |

The storage service is not bundled. `STORAGE_SERVICE_URL` defaults to `http://host.docker.internal:5001` and must point to the required external API.

Verify startup:

```bash
curl http://localhost:5002/health
docker compose -f docker/compose.yaml ps
```

## Start in LLM Mode

LLM mode must set both the environment mode and the Compose profile:

```bash
export LLM_MODE=llm
docker compose -f docker/compose.yaml --profile llm up -d
```

The `llm` profile additionally starts `aqh-ovms` and `model-download`. Starting the profile without `LLM_MODE=llm` leaves the agent in fallback mode; setting `LLM_MODE=llm` without the profile does not start the bundled OVMS dependency.

### LLM Model Settings

| Variable | Purpose | Default |
|---|---|---|
| `LLM_MODEL_NAME` | Model name passed to the model-download service | `Phi-4-mini-instruct` |
| `LLM_DEVICE` | Target inference device (`GPU`, `CPU`) | `GPU` |
| `LLM_PRECISION` | Model quantization precision (`int8`, `int4`, `fp16`, …) | `int8` |
| `USE_CASE_MODELS_DIR` | Optional host directory shared by model-download and OVMS | `aqh_model_cache` volume |
| `MODEL_DOWNLOAD_TIMEOUT_SECONDS` | Maximum wait for model provisioning. Increase this for larger models | `3600` |

## Configure Batch Events

The bundled broker is private and intended for container-network traffic. Configure a secured external broker with:

| Variable | Purpose |
|---|---|
| `MQTT_HOST`, `MQTT_PORT` | Broker address |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | Optional authentication |
| `MQTT_BATCH_TOPIC` | Batch-complete subscription; defaults to `apm/batch-complete` |
| `MQTT_BATCH_CLIENT_ID` | Stable, unique subscriber identity |
| `MQTT_QOS` | Subscription QoS (`0`, `1`, or `2`) |
| `MQTT_KEEPALIVE`, `MQTT_MAX_PAYLOAD_BYTES` | Connection and input limits |

Detection Service must persist a batch before publishing its terminal event.
Completed events queue reasoning over `(start_id, end_id]`; error events are
recorded without running agents.

## Configure Agent Assets

Agent assets are supplied by the downstream application. Set the downstream asset directory paths before startup:

```bash
export USE_CASE_CONFIGS_DIR=/absolute/path/to/config
export USE_CASE_PROMPTS_DIR=/absolute/path/to/prompts
```

The config directory must contain `agents.yaml` and `policy_fallback.json`. In LLM mode, the prompts directory must contain `<use_case_id>.txt`, where `use_case_id` comes from `agents.yaml`. Invalid URLs, modes, ports, credentials, certificates, or required assets cause startup to fail rather than running with a partial configuration.

## Run the Pipeline

```bash
RUN_ID=$(curl -s -X POST http://localhost:5002/agents/run \
  -H "Content-Type: application/json" \
  -d '{"min_id": 100, "max_id": 250}' |
  python3 -c "import json,sys; print(json.load(sys.stdin)['run_id'])")

curl "http://localhost:5002/agents/status/$RUN_ID"
curl "http://localhost:5002/agents/results/$RUN_ID"
curl "http://localhost:5002/agents/outputs/analysis/$RUN_ID"
```

Terminal outputs are also retained as per-agent JSON files in the
`aqh_agent_output` named volume. `OUTPUT_DIR` defaults to `/app/output` in
Compose. See the [API Reference](./api-reference.md) for the file schema and
all routes.

## Validate Standalone with the Mock Storage Service

The `dev` Compose profile starts a mock storage service with canned detection
data, removing the need for a real storage backend.

```bash
export STORAGE_SERVICE_URL=http://mock-storage:5001
docker compose -f docker/compose.yaml --profile dev up --build -d
```

Verify all services are healthy:

```bash
docker compose -f docker/compose.yaml --profile dev ps
curl http://localhost:5001/detections
```

Then follow [Run the Pipeline](#run-the-pipeline) above to trigger and inspect
a run against the mock data.

### Run unit tests

```bash
uv run pytest
```

Tear down when finished:

```bash
docker compose -f docker/compose.yaml --profile dev down
```

## Stop

```bash
docker compose -f docker/compose.yaml down
```

<!--hide_directive
:::{toctree}
:hidden:

get-started/system-requirements
:::
hide_directive-->