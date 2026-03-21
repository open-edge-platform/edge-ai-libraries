# Model Download

The Model Download microservice is a centralized model management system that downloads AI or machine learning models from various model hubs while ensuring consistency and simplicity across applications, stores the models, and handles optional format conversions.

## Architecture

The following figure shows the high-level architecture of Model Download, which includes its core components and their interactions with external systems:

![architecture](./images/architecture.png)

## Components

The following are the core components of the plugin-based microservice architecture:

### Core Components

1. **FastAPI Service Layer**
   - **Description**: The FastAPI Service Layer is the primary entry point for client interactions. It exposes a RESTful API for downloading, converting, and managing models.
   - **Functions**:
     - Provides RESTful API endpoints for service operations.
     - Handles incoming request validation, serialization, and routes to the appropriate components.
     - Generates and serves OpenAPI (Swagger suite) documentation for clear, interactive API specifications.

2. **Model Manager**
   - **Description**: The Model Manager is the central orchestration component that directs model download and conversion processes. It coordinates actions between the API layer and the plugin system.
   - **Functions**:
     - Orchestrates end-to-end model download and conversion workflows.
     - Manages model storage, which includes organizing file paths and handling caching.
     - Interfaces with the Plugin Registry to delegate tasks to the appropriate plugins.

3. **Plugin Registry**
   - **Description**: The Plugin Registry discovers, registers, and manages available plugins. It can extend the service's capabilities without modifying the core application logic.
   - **Functions**:
     - Dynamically discovers and registers plugins at startup.
     - Manages the lifecycle of each plugin.
     - Provides a consistent abstraction layer that decouples the Model Manager from concrete plugin implementations.

### Plugin System

The Plugin System extends the service's functionality by handling interactions with different model sources and conversion tasks.

**Model Hub Plugins:**

- **HuggingFace Hub Plugin**: Downloads models from the Hugging Face hub, including handling authentication for private or gated models.
- **Ollama Hub Plugin**: Interfaces with Ollama tool to pull and manage models from the Ollama model library.
- **Ultralytics Hub Plugin**: Downloads computer vision models, such as YOLO, from the Ultralytics framework.
- **Geti™ Plugin**: Downloads models optimized through the Geti™ platform.

**Conversion Plugins:**

- **OpenVINO™ Model Conversion Plugin**: Converts downloaded models, for example, from Hugging Face model hub into the OpenVINO Intermediate Representation (IR) format for optimized inference on Intel® hardware.

### Storage

- **Downloaded Models Storage**: This component represents the physical storage location for downloaded and converted models. It is a configurable filesystem path that acts as a centralized repository and cache.
  - **Functions**:
    - Provides a persistent location for storing model files.
    - Enables caching to avoid redundant downloads of the same model.
    - Organizes models in a structured directory format for easy access.

## Key Features

- **Multi-Hub Support**: Download models from multiple sources (Hugging Face model hub, Ollama model library, Ultralytics library, OpenVINO Model Hub, and Geti platform)
- **Format Conversion**: Convert models to OpenVINO format for optimization
- **Parallel Downloads**: Optional concurrent model downloads
- **Precision Control**: Support for various model precisions (INT8, FP16, and FP32)
- **Device Targeting**: Optimization for different compute devices (CPU, GPU, and NPU)
- **Caching**: Configurable model caching for improved performance

## Integration

The service can be integrated into applications through:

- REST API calls
- Docker container deployment
- Docker Compose orchestration

## Use Cases

This microservice is ideal for:

- Edge AI applications requiring model downloads
- Development and testing environments
- Sample applications demonstrating AI capabilities
- Automated model deployment pipelines

## Limitations

This service does not replace full model registry solutions and has the following limitations:

- Basic model versioning
- Limited model metadata management
- No built-in model serving capabilities

## Learn More

- [**Get Started Guide**](./get-started.md)
- [**API Reference**](./api-docs/openapi.yaml)

<!--hide_directive
:::{toctree}
:hidden:

get-started
system-requirements
build-from-source
deploy-with-helm-chart
running-tests
release-notes

:::
hide_directive-->
