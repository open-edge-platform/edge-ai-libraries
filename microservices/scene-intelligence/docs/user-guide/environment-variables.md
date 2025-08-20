# Environment Variables

This document provides comprehensive information about all environment variables used by the Scene Intelligence microservice stack.

## Recommended Setup Method

**The preferred way to configure and deploy Scene Intelligence is using the provided setup script:**

```bash
# Complete setup with sensible defaults
source setup.sh --setup

# Or just set environment variables
source setup.sh --setenv
```

**The setup script automatically configures all required environment variables with production-ready defaults.** Manual environment variable configuration is only needed for advanced customization or when integrating with existing infrastructure.

## When to Use Manual Configuration

Manual environment variable configuration is recommended for:

- Integration with existing CI/CD pipelines
- Custom deployment environments
- Advanced performance tuning
- Development with specific configurations

For most users, **the setup script approach documented in [Get Started](./get-started.md) is sufficient**.

## Environment Variable Reference

## Core Stack Configuration

### Service Ports

#### SCENE_INTELLIGENCE_PORT

**Description**: External port for Scene Intelligence API service  
**Default**: `8081`  
**Example**: `export SCENE_INTELLIGENCE_PORT=8081`

#### VLM_SERVICE_PORT

**Description**: External port for VLM OpenVINO serving service  
**Default**: `9764`  
**Example**: `export VLM_SERVICE_PORT=9764`

#### SCENESCAPE_PORT

**Description**: External port for SceneScape web interface  
**Default**: `443`  
**Example**: `export SCENESCAPE_PORT=443`

#### MQTT_PORT

**Description**: External port for MQTT broker  
**Default**: `1883`  
**Example**: `export MQTT_PORT=1883`

#### DLSTREAMER_PORT

**Description**: External port for DL Streamer pipeline server  
**Default**: `8555`  
**Example**: `export DLSTREAMER_PORT=8555`

### VLM Configuration

#### VLM_BASE_URL

**Description**: Internal URL for VLM service communication  
**Default**: `http://vlm-openvino-serving:8000`  
**Example**: `export VLM_BASE_URL=http://vlm-openvino-serving:8000`

#### VLM_MODEL

**Description**: VLM model name for Scene Intelligence  
**Default**: `Qwen/Qwen2.5-VL-3B-Instruct`  
**Example**: `export VLM_MODEL=Qwen/Qwen2.5-VL-3B-Instruct`

#### VLM_MODEL_NAME

**Description**: VLM model name for OpenVINO serving  
**Default**: `Qwen/Qwen2.5-VL-3B-Instruct`  
**Example**: `export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct`

#### VLM_WORKERS

**Description**: Number of VLM worker processes  
**Default**: `4`  
**Example**: `export VLM_WORKERS=4`

#### HIGH_DENSITY_THRESHOLD

**Description**: Traffic density threshold for VLM analysis  
**Default**: `5.0`  
**Example**: `export HIGH_DENSITY_THRESHOLD=5.0`

#### VLM_TIMEOUT_SECONDS

**Description**: Timeout for VLM requests  
**Default**: `10`  
**Example**: `export VLM_TIMEOUT_SECONDS=10`

#### VLM_COOLDOWN_MINUTES

**Description**: Cooldown between VLM analyses  
**Default**: `1`  
**Example**: `export VLM_COOLDOWN_MINUTES=1`

### MQTT Configuration

#### MQTT_BROKER_HOST

**Description**: MQTT broker hostname  
**Default**: `broker.scenescape.intel.com`  
**Example**: `export MQTT_BROKER_HOST=broker.scenescape.intel.com`

#### MQTT_BROKER_PORT

**Description**: MQTT broker port  
**Default**: `1883`  
**Example**: `export MQTT_BROKER_PORT=1883`

### Container Registry

#### REGISTRY

**Description**: Container registry URL prefix  
**Default**: Empty (uses default registry)  
**Example**: `export REGISTRY=your-registry.com/`

#### TAG

**Description**: Container image tag  
**Default**: `latest`  
**Example**: `export TAG=v1.0.0`

## Additional VLM Parameters

#### VLM_MAX_COMPLETION_TOKENS

**Description**: Maximum tokens for VLM responses  
**Default**: `500`  
**Example**: `export VLM_MAX_COMPLETION_TOKENS=500`

#### VLM_TEMPERATURE

**Description**: VLM sampling temperature  
**Default**: `0.3`  
**Example**: `export VLM_TEMPERATURE=0.3`

#### VLM_TOP_P

**Description**: VLM nucleus sampling parameter  
**Default**: `0.9`  
**Example**: `export VLM_TOP_P=0.9`

#### VLM_DEVICE

**Description**: Device for VLM inference  
**Default**: `CPU`  
**Options**: `CPU`, `GPU`  
**Example**: `export VLM_DEVICE=GPU`

#### VLM_COMPRESSION_WEIGHT_FORMAT

**Description**: Model compression format  
**Default**: `int8`  
**Options**: `int8`, `int4`, `fp16`  
**Example**: `export VLM_COMPRESSION_WEIGHT_FORMAT=int8`

## Quick Setup Examples

### Using Setup Script (Recommended)

```bash
# Development setup with debug logging
export LOG_LEVEL=DEBUG
export VLM_WORKERS=2
source setup.sh --setup

# Production setup with performance tuning
export VLM_WORKERS=4
export HIGH_DENSITY_THRESHOLD=5.0
source setup.sh --setup

# Custom registry setup
export REGISTRY_URL=your-registry.com
export PROJECT_NAME=scene-intelligence
source setup.sh --setup
```

### Manual Configuration (Advanced)

### Manual Development Setup

```bash
export SCENE_INTELLIGENCE_PORT=8081
export VLM_SERVICE_PORT=9764
export VLM_WORKERS=2
export LOG_LEVEL=DEBUG
export HIGH_DENSITY_THRESHOLD=3.0
```

### Manual Production Setup

```bash
export SCENE_INTELLIGENCE_PORT=8081
export VLM_SERVICE_PORT=9764
export VLM_WORKERS=4
export LOG_LEVEL=INFO
export HIGH_DENSITY_THRESHOLD=5.0
export DATA_RETENTION_HOURS=168
```

### Manual High Performance Setup

```bash
export VLM_DEVICE=GPU
export VLM_WORKERS=8
export VLM_TIMEOUT_SECONDS=30
export TRAFFIC_BUFFER_DURATION=120
```

**Note**: After manually setting environment variables, you still need to run the Docker Compose stack manually. The setup script approach handles this automatically.

#### MQTT_BROKER_PORT

**Description**: MQTT broker port number.

**Default**: `1883`

**Examples**:

```bash
# Standard MQTT port
export MQTT_BROKER_PORT=1883

# Secure MQTT port
export MQTT_BROKER_PORT=8883

# Custom port
export MQTT_BROKER_PORT=1884
```

#### MQTT_USERNAME

**Description**: MQTT broker username for authentication.

**Default**: None (anonymous connection)

**Examples**:

```bash
export MQTT_USERNAME="scene_intelligence_user"
export MQTT_USERNAME="mqtt_client"
```

#### MQTT_PASSWORD

**Description**: MQTT broker password for authentication.

**Default**: None (anonymous connection)

**Examples**:

```bash
export MQTT_PASSWORD="secure_password123"
export MQTT_PASSWORD="${MQTT_SECRET}"
```

#### MQTT_KEEPALIVE

**Description**: MQTT keepalive interval in seconds.

**Default**: `60`

**Examples**:

```bash
export MQTT_KEEPALIVE=60
export MQTT_KEEPALIVE=30
```

### VLM Service Configuration

#### VLM_BASE_URL

**Description**: Base URL for the VLM service API.

**Default**: `http://localhost:8000`

**Examples**:

```bash
export VLM_BASE_URL="http://vlm-service:8000"
export VLM_BASE_URL="http://192.168.1.101:8000"
export VLM_BASE_URL="https://vlm.example.com"
```

#### VLM_MODEL

**Description**: VLM model name to use for analysis.

**Default**: From configuration file

**Examples**:

```bash
export VLM_MODEL="Qwen/Qwen2.5-VL-3B-Instruct"
export VLM_MODEL="microsoft/Phi-3.5-vision-instruct"
```

#### VLM_WORKERS

**Description**: Number of concurrent VLM workers.

**Default**: `3`

**Range**: 1-10

**Examples**:

```bash
# Low resource usage
export VLM_WORKERS=1

# Balanced performance
export VLM_WORKERS=3

# High throughput
export VLM_WORKERS=6
```

#### VLM_TIMEOUT_SECONDS

**Description**: VLM API request timeout in seconds.

**Default**: `30`

**Examples**:

```bash
export VLM_TIMEOUT_SECONDS=30
export VLM_TIMEOUT_SECONDS=60
export VLM_TIMEOUT_SECONDS=10
```

### Traffic Analysis Configuration

#### HIGH_DENSITY_THRESHOLD

**Description**: Traffic density threshold for triggering VLM analysis.

**Default**: `5.0`

**Examples**:

```bash
# Conservative threshold
export HIGH_DENSITY_THRESHOLD=3.0

# Default threshold
export HIGH_DENSITY_THRESHOLD=5.0

# High threshold for busy areas
export HIGH_DENSITY_THRESHOLD=8.0
```

#### VLM_COOLDOWN_MINUTES

**Description**: Cooldown period between VLM analyses for the same intersection.

**Default**: `1`

**Examples**:

```bash
export VLM_COOLDOWN_MINUTES=1
export VLM_COOLDOWN_MINUTES=5
export VLM_COOLDOWN_MINUTES=15
```

#### MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS

**Description**: Minimum duration of sustained high traffic before triggering VLM analysis.

**Default**: `30`

**Examples**:

```bash
export MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS=30
export MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS=60
export MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS=15
```

### VLM Model Parameters

#### VLM_MAX_COMPLETION_TOKENS

**Description**: Maximum number of tokens in VLM response.

**Default**: `500`

**Examples**:

```bash
export VLM_MAX_COMPLETION_TOKENS=500
export VLM_MAX_COMPLETION_TOKENS=1000
export VLM_MAX_COMPLETION_TOKENS=200
```

#### VLM_TEMPERATURE

**Description**: Temperature parameter for VLM model (creativity).

**Default**: `0.3`

**Range**: 0.0-2.0

**Examples**:

```bash
# More deterministic
export VLM_TEMPERATURE=0.1

# Balanced
export VLM_TEMPERATURE=0.3

# More creative
export VLM_TEMPERATURE=0.7
```

#### VLM_TOP_P

**Description**: Top-p parameter for VLM model (nucleus sampling).

**Default**: `0.9`

**Range**: 0.0-1.0

**Examples**:

```bash
export VLM_TOP_P=0.9
export VLM_TOP_P=0.95
export VLM_TOP_P=0.8
```

### Custom Prompts

#### VLM_TRAFFIC_ANALYSIS_PROMPT

**Description**: Custom prompt for VLM traffic analysis.

**Default**: From configuration file

**Examples**:

```bash
export VLM_TRAFFIC_ANALYSIS_PROMPT="Analyze the traffic situation in these intersection images and provide insights."
```

#### VLM_SYSTEM_PROMPT

**Description**: System prompt for VLM model.

**Default**: From configuration file

**Examples**:

```bash
export VLM_SYSTEM_PROMPT="You are an expert traffic analyst with computer vision capabilities."
```

### Service Configuration

#### SERVICE_PORT

**Description**: Port number for the HTTP API server.

**Default**: `8001`

**Examples**:

```bash
export SERVICE_PORT=8001
export SERVICE_PORT=8080
export SERVICE_PORT=3000
```

#### LOG_LEVEL

**Description**: Logging level for the service.

**Default**: `INFO`

**Supported Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

**Examples**:

```bash
# Development
export LOG_LEVEL=DEBUG

# Production
export LOG_LEVEL=INFO

# Quiet production
export LOG_LEVEL=WARNING
```

#### DATABASE_URL

**Description**: Database connection URL (optional).

**Default**: SQLite in-memory database

**Examples**:

```bash
# SQLite file
export DATABASE_URL="sqlite:///data/scene_intelligence.db"

# PostgreSQL
export DATABASE_URL="postgresql://user:password@localhost:5432/scene_intelligence"
```

## Configuration File Variables

The following variables can be overridden by environment variables but are typically set in configuration files:

### Traffic Analysis Window Configuration

- **Traffic Window Duration**: 15 seconds (hardcoded)
- **Sustained Threshold**: 3 seconds (hardcoded)
- **Analysis Display Duration**: 20 minutes (hardcoded)

### Image Service Configuration

- **Max Images Per Camera**: Configurable in service initialization
- **Image Freshness Window**: 3-5 minutes for API responses

## Environment Variable Precedence

Environment variables take precedence over configuration file values in the following order:

1. **Environment Variables** (highest precedence)
2. **Configuration Files** (VLM config, Scene Intelligence config)
3. **Default Values** (lowest precedence)

## Examples by Use Case

### Development Environment

```bash
export SCENE_INTELLIGENCE_CONFIG_PATH="./config/scene_intelligence_config.json"
export VLM_CONFIG_PATH="./config/vlm_config.json"
export MQTT_BROKER_HOST="localhost"
export MQTT_BROKER_PORT=1883
export VLM_BASE_URL="http://localhost:8000"
export LOG_LEVEL=DEBUG
export VLM_WORKERS=1
```

### Production Environment

```bash
export SCENE_INTELLIGENCE_CONFIG_PATH="/app/config/scene_intelligence_config.json"
export VLM_CONFIG_PATH="/app/config/vlm_config.json"
export MQTT_BROKER_HOST="mqtt-broker.production.com"
export MQTT_BROKER_PORT=1883
export MQTT_USERNAME="scene_intelligence_prod"
export MQTT_PASSWORD="${MQTT_PROD_PASSWORD}"
export VLM_BASE_URL="http://vlm-service:8000"
export LOG_LEVEL=INFO
export VLM_WORKERS=3
export HIGH_DENSITY_THRESHOLD=5.0
export VLM_TIMEOUT_SECONDS=30
```

### High-Performance Environment

```bash
export VLM_WORKERS=6
export VLM_TIMEOUT_SECONDS=60
export HIGH_DENSITY_THRESHOLD=3.0
export VLM_COOLDOWN_MINUTES=1
export MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS=15
export VLM_MAX_COMPLETION_TOKENS=1000
```

### Secure Environment

```bash
export MQTT_BROKER_PORT=8883
export MQTT_USERNAME="${MQTT_SECURE_USER}"
export MQTT_PASSWORD="${MQTT_SECURE_PASSWORD}"
export VLM_BASE_URL="https://vlm-service.secure.com"
export DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@db.secure.com:5432/scene_intelligence"
```
