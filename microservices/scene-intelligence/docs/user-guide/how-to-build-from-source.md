# How to Build from Source

Build the **Scene Intelligence microservice** from source to customize, debug, or extend its functionality. In this guide, you will:
- Set up your development environment.
- Compile the source code and resolve dependencies.
- Generate a runnable build for local testing or deployment.

This guide is ideal for developers who want to work directly with the source code.

## Prerequisites

Before you begin, ensure the following:
- **System Requirements**: Verify your system meets the [minimum requirements](./system-requirements.md).
- This guide assumes basic familiarity with Git commands, Python virtual environments, and terminal usage. If you are new to these concepts, see:
  - [Git Documentation](https://git-scm.com/doc)
  - [Python Virtual Environments](https://docs.python.org/3/tutorial/venv.html)

## Steps to Build

This section provides a detailed note on how to build the Scene Intelligence microservice.

**_(Optional)_** Docker Compose builds the _Scene Intelligence_ with a default image and tag name. If you want to use a different image and tag, export these variables:

```bash
export REGISTRY_URL="your-container-registry_url"
export PROJECT_NAME="your-project-name"
export TAG="your_tag"
```

> **_NOTE:_** `PROJECT_NAME` will be suffixed to `REGISTRY_URL` to create a namespaced url. Final image name will be created/pulled by further suffixing the application name and tag with the namespaced url. 

> **_EXAMPLE:_** If variables are set using above command, the final image names for _Scene Intelligence_ would be `<your-container-registry-url>/<your-project-name>/scene-intelligence:<your-tag>`. 

If variables are not set, in that case, the `TAG` will have default value as _latest_. Hence, final image will be `scene-intelligence:latest`.

### 1. Clone the Repository

```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
cd edge-ai-libraries/microservices/scene-intelligence
```

### 2. Set up environment values

Follow all the instructions provided in the [get started](./get-started.md#set-environment-values) document to set up the environment variables.

### 3. Build the Docker image

To build the Docker image, run the following command:

```bash
cd docker
docker compose -f docker/compose.yaml build scene-intelligence
```

### 4. Run the Docker image

```bash
docker compose -f docker/compose.yaml up scene-intelligence
```

## Development Setup

For local development without Docker:

### 1. Set up Python Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Or using Poetry (recommended)
poetry install
poetry shell
```

### 2. Install Dependencies

```bash
# Using pip
pip install -r requirements.txt

# Using Poetry (recommended)
poetry install
```

### 3. Set up Configuration Files

Create the required configuration files:

```bash
mkdir -p config
cp config/scene_intelligence_config.json.example config/scene_intelligence_config.json
cp config/vlm_config.json.example config/vlm_config.json
```

Edit the configuration files according to your environment.

### 4. Set Environment Variables

```bash
export SCENE_INTELLIGENCE_CONFIG_PATH="./config/scene_intelligence_config.json"
export VLM_CONFIG_PATH="./config/vlm_config.json"
export MQTT_BROKER_HOST="localhost"
export MQTT_BROKER_PORT=1883
```

### 5. Run the Service

```bash
# Using Poetry
poetry run python -m src.scene_intelligence.main

# Using pip
python -m src.scene_intelligence.main
```

## Testing the Build

### 1. Run Unit Tests

```bash
# Using Poetry
poetry run pytest tests/

# Using pip
python -m pytest tests/
```

### 2. Run Integration Tests

```bash
# Start required services (MQTT broker, VLM service)
docker compose -f docker/compose.yaml up mqtt-broker vlm-service -d

# Run integration tests
poetry run pytest tests/integration/

# Stop services
docker compose -f docker/compose.yaml down
```

### 3. Verify API Endpoints

```bash
# Health check
curl http://localhost:8001/health

# Configuration
curl http://localhost:8001/config

# Get available intersections
curl http://localhost:8001/api/v1/intersections

# Traffic summary
curl "http://localhost:8001/api/v1/traffic/directional/summary"

# Intersection traffic (use actual intersection ID from /intersections endpoint)
curl "http://localhost:8001/api/v1/traffic/directional/intersection/3d7b9e1f-c4a6-4f8e-b2d5-6a8c0e2f4b7d"
```

## Development Workflow

### 1. Code Quality

```bash
# Format code
poetry run black src/
poetry run isort src/

# Lint code
poetry run flake8 src/
poetry run pylint src/

# Type checking
poetry run mypy src/
```

### 2. Pre-commit Hooks

```bash
# Install pre-commit
poetry add --dev pre-commit

# Install hooks
poetry run pre-commit install

# Run hooks manually
poetry run pre-commit run --all-files
```

### 3. Documentation

```bash
# Generate API documentation
poetry run sphinx-build -b html docs/ docs/_build/html

# Serve documentation locally
cd docs/_build/html && python -m http.server 8080
```

## Deployment

### 1. Production Build

```bash
# Build optimized Docker image
docker build -t scene-intelligence:production -f docker/Dockerfile.prod .

# Or using Docker Compose with production overrides
docker compose -f docker/compose.yaml -f docker compose -f docker/compose.yaml.yml -f docker compose -f docker/compose.yaml.prod.yml build
```

### 2. Multi-architecture Build

```bash
# Build for multiple architectures
docker buildx build --platform linux/amd64,linux/arm64 -t scene-intelligence:latest .
```

### 3. Kubernetes Deployment

```bash
# Generate Kubernetes manifests
helm template scene-intelligence helm/scene-intelligence > k8s-manifests.yaml

# Deploy to Kubernetes
kubectl apply -f k8s-manifests.yaml
```

## Troubleshooting

### Common Issues

**Dependencies not installing**:
- Ensure Python 3.10+ is installed
- Update pip: `pip install --upgrade pip`
- Clear Poetry cache: `poetry cache clear pypi --all`

**Import errors**:
- Verify PYTHONPATH includes the src directory
- Check virtual environment is activated
- Ensure all dependencies are installed

**Configuration errors**:
- Validate JSON configuration files
- Check file paths in environment variables
- Verify all required configuration sections are present

**Service not starting**:
- Check port availability
- Verify MQTT broker connectivity
- Review service logs for detailed error messages

### Debug Mode

Run the service in debug mode for detailed logging:

```bash
export LOG_LEVEL=DEBUG
poetry run python -m src.scene_intelligence.main
```

## Supporting Resources

* [Get Started Guide](get-started.md)
* [Environment Variables](environment-variables.md)
* [System Requirements](system-requirements.md)
