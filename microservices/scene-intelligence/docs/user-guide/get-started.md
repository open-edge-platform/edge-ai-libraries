# Get Started

The **Scene Intelligence microservice** provides comprehensive traffic analysis capabilities including real-time intersection monitoring, directional traffic density analysis, and VLM-powered traffic insights. This guide provides step-by-step instructions to:

- Set up the microservice using the automated setup script for quick deployment.
- Run predefined tasks to explore its functionality.
- Learn how to modify configurations to suit specific requirements.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).
- **MQTT Broker**: Ensure access to an MQTT broker for traffic data streaming (or use the included broker).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Quick Start with Setup Script

The Scene Intelligence microservice includes an automated setup script that handles environment configuration, secrets generation, building, and deployment. This is the **recommended approach** for getting started.

### 1. Clone the Repository

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/microservices/scene-intelligence
```

### 2. Run the Complete Setup

The setup script provides several options. For a complete setup (recommended for first-time users):

```bash
# Complete setup: generates secrets, builds images, and starts all services
source setup.sh --setup
```

This single command will:

- Set all required environment variables with sensible defaults
- Generate required TLS certificates and authentication files
- Download demo video files for testing
- Build Docker images
- Start all services in the Scene Intelligence stack

### 3. Alternative Setup Options

For more granular control, the setup script provides individual commands:

```bash
# Set environment variables only
source setup.sh --setenv

# Generate secrets only
source setup.sh --secrets

# Download demo videos only
source setup.sh --videos

# Download videos and build images
source setup.sh --build

# Start services only (after setup)
source setup.sh --run

# Stop services
source setup.sh --stop

# Check service status
source setup.sh --status

# Clean up everything
source setup.sh --clean
```

### 4. Verify the Stack

After running the setup, check that all services are running:

```bash
source setup.sh --status
```

Check Scene Intelligence health:

```bash
curl -s -X GET http://localhost:8082/health
```

## Manual Setup (Advanced Users)

For advanced users who need more control over the configuration, you can manually set up the stack using Docker Compose.

### Manual Environment Configuration

If you prefer to manually configure environment variables instead of using the setup script, see the [Environment Variables Guide](./environment-variables.md) for complete details. Key variables include:

```bash
# Core Scene Intelligence Configuration
export SCENE_INTELLIGENCE_PORT=8082
export LOG_LEVEL=INFO

# MQTT Broker Configuration
export MQTT_BROKER_HOST=broker.scenescape.intel.com
export MQTT_BROKER_PORT=1883
export MQTT_PORT=1883

# VLM Service Configuration
export VLM_BASE_URL=http://vlm-openvino-serving:8000
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_SERVICE_PORT=9764

# SceneScape Configuration
export SCENESCAPE_PORT=443
export DLSTREAMER_PORT=8555

# Traffic Analysis Parameters
export HIGH_DENSITY_THRESHOLD=5.0
export VLM_WORKERS=4
export VLM_COOLDOWN_MINUTES=1
export VLM_TIMEOUT_SECONDS=10
```

### Manual Docker Compose Deployment

```bash
# 1. Generate secrets manually
./src/secrets/generate_secrets.sh

# 2. Start services
docker compose -f docker/compose.yaml up -d
```

## Services Included

The Scene Intelligence stack includes these services:

- **MQTT Broker** (Eclipse Mosquitto) - Message broker for traffic data
- **DL Streamer Pipeline Server** - Video analytics and AI inference
- **SceneScape Database** - Configuration and metadata storage
- **SceneScape Web Server** - Management interface
- **SceneScape Controller** - Orchestration service
- **Scene Intelligence API** - Main traffic analysis service
- **VLM OpenVINO Serving** - Vision Language Model inference

## Testing the API

### 1. Get Service Status

```bash
curl -s -X GET http://localhost:8082/health
```

Expected response:

```json
{
  "status": "healthy",
  "timestamp": "2025-08-19T10:30:00.000000+00:00",
  "service": "scene-intelligence"
}
```

### 2. Get Available Intersections

First, get the list of available intersection IDs:

```bash
curl -s -X GET "http://localhost:8082/api/v1/intersections"
```

This will return the actual intersection UUIDs you need to use in subsequent API calls.

### 3. Get Traffic Summary

```bash
curl -s -X GET "http://localhost:8082/api/v1/traffic/directional/summary"
```

### 4. Get Intersection Traffic

Use an actual intersection ID from the `/intersections` endpoint:

```bash
# First get intersection IDs
INTERSECTION_ID=$(curl -s -X GET "http://localhost:8082/api/v1/intersections" | jq -r '.intersections[0].intersection_id')

# Then get traffic data for that intersection
curl -s -X GET "http://localhost:8082/api/v1/traffic/directional/intersection/$INTERSECTION_ID"
```

Or use a specific intersection UUID directly:

```bash
curl -s -X GET "http://localhost:8082/api/v1/traffic/directional/intersection/3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d"
```

### 5. View Service Configuration

```bash
curl -s -X GET http://localhost:8082/api/v1/config
```

### 6. Check VLM Integration

```bash
# Get current VLM threshold
curl -s -X GET http://localhost:8082/api/v1/config/vlm/threshold

# Update VLM threshold (optional)
curl -s -X PUT http://localhost:8082/api/v1/config/vlm/threshold \
  -H "Content-Type: application/json" \
  -d '{"threshold": 6.0}'
```

### 7. Monitor Camera Images

```bash
curl -s -X GET http://localhost:8082/api/v1/cameras/images
curl -s -X GET http://localhost:8082/api/v1/cameras/stats
```

## Service Ports

The complete stack exposes several services on different ports:

| Service | Port | Description |
|---------|------|-------------|
| Scene Intelligence API | 8082 | Main traffic analysis API |
| VLM OpenVINO Serving | 9764 | Vision Language Model service |
| SceneScape Web | 443 | Management web interface (HTTPS) |
| MQTT Broker | 1883 | Message broker |
| DL Streamer | 8555 | Video analytics pipeline |

## Configuration Files

The Scene Intelligence stack uses several configuration files located in the `config/` directory:

### Scene Intelligence Configuration

The main service configuration is located at `config/scene_intelligence_config.json`:

```json
{
  "service": {
    "name": "scene-intelligence",
    "port": 8080,
    "host": "0.0.0.0"
  },
  "intersections": {
    "3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d": {
      "name": "Intersection-1",
      "latitude": 40.7516,
      "longitude": -73.9944
    },
    "f8e9c1a2-b3d4-4e5f-9a8b-7c6d5e4f3g2h": {
      "name": "Intersection-2", 
      "latitude": 40.7580,
      "longitude": -73.9855
    }
  },
  "regions": {
    "intersection_regions": {
      "3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d": {
        "north": ["bd0b91b8-ccfb-4413-acb9-91d7ad0abce0"],
        "south": ["8d2edd2f-667d-41c2-9bc0-fadb27906452"],
        "east": ["453cb3e7-c819-46eb-81c6-d772eec9d2a8"],
        "west": ["fe6d755b-86ca-4d57-9ca3-51d5dda19801"]
      }
    }
  }
}
```

### VLM Configuration

VLM service configuration is at `config/vlm_config.json`:

```json
{
  "vlm_service": {
    "base_url": "http://vlm-openvino-serving:8000",
    "model": "Qwen/Qwen2.5-VL-3B-Instruct",
    "timeout_seconds": 10,
    "vlm_workers": 4
  },
  "traffic_analysis": {
    "high_density_threshold": 5.0,
    "minimum_duration_for_consistently_high_traffic_seconds": 2,
    "vlm_cooldown_minutes": 1
  },
  "vlm_model_parameters": {
    "max_completion_tokens": 500,
    "temperature": 0.3,
    "top_p": 0.9
  },
  "prompts": {
    "system_prompt": "You are an AI traffic analyst specializing in intersection traffic analysis.",
    "traffic_analysis_prompt": "Analyze the provided intersection images and explain the high traffic density situation."
  }
}
```

### DL Streamer Configuration

Pipeline configuration is at `src/dlstreamer-pipeline-server/config.json` for video analytics setup.

## Next Steps

- **Traffic Analysis Deep Dive**: See [Traffic Data Analysis Workflow](./traffic-data-analysis-workflow.md) for comprehensive details on VLM integration, trigger conditions, windowed analysis, and configuration parameters.
- **Advanced Configuration**: For detailed environment variable options, see [Environment Variables](./environment-variables.md).
- **API Documentation**: Explore the full [API Reference](./api-reference.md) for detailed endpoint documentation.
- **SceneScape Management**: Access the web interface at `https://localhost:443` for visual management.
- **Video Analytics**: Configure video streams and AI models through DL Streamer integration.
- **Build from Source**: See [How to Build from Source](./how-to-build-from-source.md) for development and custom builds.

## Stack Architecture

The Scene Intelligence stack provides a complete traffic analysis solution:

```

┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Video Input   │───▶│  DL Streamer     │───▶│  MQTT Broker    │
│   (Cameras)     │    │  Pipeline Server │    │  (Mosquitto)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   SceneScape    │◀───│  Scene           │◀───│  Scene          │
│   Web Interface │    │  Controller      │    │  Intelligence   │
└─────────────────┘    └──────────────────┘    │  API Service    │
                                                └─────────────────┘
                                                         │
                                                ┌─────────────────┐
                                                │  VLM OpenVINO   │
                                                │  Serving        │
                                                └─────────────────┘
```

## Troubleshooting

### Stack Not Starting

**Use the setup script to check status**:

```bash
source setup.sh --status
```

**Check logs**:

```bash
cd docker
docker compose  logs
```

**Restart services**:

```bash
source setup.sh --stop
source setup.sh --run
```

**Common issues**:

- Missing secrets/certificates in `src/secrets/` directory
- Port conflicts (8082, 9764, 443, 1883, 8555)
- Insufficient system resources for VLM service
- Proxy configuration issues

### Service Health Issues

**Check individual service health**:

```bash
# Scene Intelligence API
curl -s -X GET http://localhost:8082/health

# VLM Service
curl -s -X GET http://localhost:9764/health

# Check service logs
docker compose -f docker/compose.yaml logs scene-intelligence
docker compose -f docker/compose.yaml logs vlm-openvino-serving
```

### API Connection Issues

**Verify network connectivity**:

```bash
# Check if services are accessible
docker compose -f docker/compose.yaml exec scene-intelligence curl -s http://vlm-openvino-serving:8000/health
docker compose -f docker/compose.yaml  exec scene-intelligence curl -s http://broker.scenescape.intel.com:1883

# Check service configuration
curl -s -X GET http://localhost:8082/api/v1/config
curl -s -X GET http://localhost:8082/api/v1/status
```

### VLM Analysis Not Working

**Debug VLM integration**:

```bash
# Check VLM threshold configuration
curl -s -X GET http://localhost:8082/api/v1/config/vlm/threshold

# Monitor image requests
curl -s -X GET http://localhost:8082/api/v1/debug/image-requests

# Check camera images availability
curl -s -X GET http://localhost:8082/api/v1/cameras/stats
```

### Performance Issues

**Resource monitoring**:

```bash
# Check container resource usage
docker stats

# Adjust VLM workers if needed
export VLM_WORKERS=2
docker compose -f docker/compose.yaml up -d vlm-openvino-serving
```

### Configuration Issues

**Validate configuration files**:

```bash
# Check JSON syntax
cat config/scene_intelligence_config.json | jq .
cat config/vlm_config.json | jq .

# Verify mounted configuration
docker compose -f docker/compose.yaml exec scene-intelligence ls -la /app/config/
```
