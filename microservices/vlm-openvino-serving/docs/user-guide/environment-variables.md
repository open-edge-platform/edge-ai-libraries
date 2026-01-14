# Environment Variables

This document provides comprehensive information about all environment variables used by the VLM OpenVINO Serving microservice. These variables allow you to customize the behavior, performance, and configuration of the service.

## Required Environment Variables

### VLM_MODEL_NAME

**Description**: Specifies the model to be used for inference.

**Required**: Yes

**Examples**:

```bash
export VLM_MODEL_NAME="Qwen/Qwen2.5-VL-3B-Instruct"
export VLM_MODEL_NAME="microsoft/Phi-3.5-vision-instruct"
```

**Supported Models**: Refer to [model list](./Overview.md#models-supported) for the complete list of supported models.

## Optional Environment Variables

### Device Configuration

#### VLM_DEVICE

**Description**: Specifies the compute device to use for inference.

**Default**: `CPU`

**Supported Values**: `CPU`, `GPU`, `GPU.0`, `GPU.1`, etc.

**Examples**:

```bash
# Use CPU for inference (default)
export VLM_DEVICE=CPU

# Use GPU for inference (if available)
export VLM_DEVICE=GPU

# Use specific GPU device (if multiple GPUs available)
export VLM_DEVICE=GPU.0
export VLM_DEVICE=GPU.1
```

**Device Selection Guidelines**:

- **CPU**: Best for development, testing, and when GPU is not available
- **GPU**: Recommended for production workloads when GPU acceleration is available
- **Multi-GPU**: When multiple GPUs are available, specify which one to use

**Note**: When using GPU, the setup script automatically adjusts compression format to `int4` and sets workers to 1 for optimal GPU performance.

### OpenVINO Configuration

#### OV_CONFIG

**Description**: A JSON string containing OpenVINO configuration parameters for fine-tuning inference performance.

**Default**: `{"PERFORMANCE_HINT": "LATENCY"}`

**Format**: JSON string

**Common Parameters**:

- `PERFORMANCE_HINT`: "LATENCY" or "THROUGHPUT"
- `NUM_STREAMS`: Number of parallel inference streams
- `INFERENCE_NUM_THREADS`: Number of CPU threads for inference
- `CACHE_DIR`: Directory to cache compiled models

**Examples**:

```bash
# Default latency-optimized configuration
export OV_CONFIG='{"PERFORMANCE_HINT": "LATENCY"}'

# Throughput-optimized configuration
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT"}'

# Custom configuration with multiple streams and threads
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT", "NUM_STREAMS": 4, "INFERENCE_NUM_THREADS": 8}'

# Configuration with cache directory
export OV_CONFIG='{"PERFORMANCE_HINT": "LATENCY", "CACHE_DIR": "/tmp/ov_cache"}'
```

**Reference**: For a complete list of OpenVINO configuration options, refer to the [OpenVINO Documentation](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html).

### Model Configuration

#### VLM_COMPRESSION_WEIGHT_FORMAT

**Description**: Specifies the format for model weight compression.

**Default**: `int8`

**Supported Values**: `int8`, `int4`

**Examples**:

```bash
export VLM_COMPRESSION_WEIGHT_FORMAT=int8  # Default for CPU
export VLM_COMPRESSION_WEIGHT_FORMAT=int4  # Automatically set for GPU
```

**Note**: The setup script automatically sets this to `int4` when `VLM_DEVICE=GPU` for optimal GPU performance.

#### VLM_MAX_COMPLETION_TOKENS

**Description**: Sets the maximum number of tokens to generate in the completion.

**Default**: None (unlimited)

**Examples**:

```bash
# Set maximum completion tokens to 1000
export VLM_MAX_COMPLETION_TOKENS=1000

# Set maximum completion tokens to 500 for shorter responses
export VLM_MAX_COMPLETION_TOKENS=500
```

**Use Cases**:

- Controlling response length
- Managing computational resources
- Ensuring consistent output sizes

#### VLM_SEED

**Description**: Sets the seed value for deterministic behavior in VLM inference.

**Default**: `42`

**Examples**:

```bash
export VLM_SEED=42        # Default
export VLM_SEED=12345     # Custom seed for reproducible results
```

**Use Cases**:

- Debugging and troubleshooting
- Reproducing specific results
- Testing and validation

### Logging Configuration

#### VLM_LOG_LEVEL

**Description**: Controls the verbosity of application logs.

**Default**: `info`

**Supported Values**: `debug`, `info`, `warning`, `error`

**Examples**:

```bash
# Standard logging (default)
export VLM_LOG_LEVEL=info

# Detailed logging for troubleshooting
export VLM_LOG_LEVEL=debug

# Only warnings and errors
export VLM_LOG_LEVEL=warning

# Only error messages
export VLM_LOG_LEVEL=error
```

**Log Level Details**:

- `debug`: Enables detailed logging including OpenVINO debug information (verbose, useful for troubleshooting)
- `info`: Standard operational logging (default, recommended for production)
- `warning`: Only warnings and errors (minimal logging)
- `error`: Only error messages (very minimal logging)

**Note**: Setting `VLM_LOG_LEVEL=debug` will also enable OpenVINO debug logging, which can be very verbose.

#### VLM_ACCESS_LOG_FILE

**Description**: Controls where HTTP access logs (including health check requests) are written.

**Default**: `/dev/null` (disabled by default)

**Supported Values**: `-` (stdout), `/dev/null` (disabled), or file path

**Examples**:

```bash
# Send access logs to stdout
export VLM_ACCESS_LOG_FILE="-"

# Disable access logs completely (recommended for production)
export VLM_ACCESS_LOG_FILE="/dev/null"

# Write access logs to a specific file
export VLM_ACCESS_LOG_FILE="/app/logs/access.log"
```

**Access Log Details**:

- **Access logs**: HTTP request logs from the web server (Gunicorn/Uvicorn)
- **Application logs**: Logs from Python application code (controlled by `VLM_LOG_LEVEL`)
- Health check requests appear in access logs regardless of application log level
- Setting to `/dev/null` is recommended for production to reduce log noise

### Telemetry Storage

#### VLM_TELEMETRY_PATH

**Description**: Absolute path to the JSONL file where `/v1/telemetry` entries are persisted. Each Gunicorn worker writes to the same file using file locks.

**Default**: `/opt/vlm_telemetry.jsonl`

**Examples**:

```bash
export VLM_TELEMETRY_PATH=/var/log/vlm/telemetry.jsonl
export VLM_TELEMETRY_PATH=/tmp/dev-telemetry.jsonl
```

Use a location that is writable by the container user. When running multiple services on the same host, different paths prevent overlap.

#### VLM_TELEMETRY_MAX_RECORDS

**Description**: Maximum number of telemetry entries retained on disk. Older entries are dropped once the limit is reached.

**Default**: `100`

**Examples**:

```bash
# Keep the last 500 inference records
export VLM_TELEMETRY_MAX_RECORDS=500
```

**Notes**:

- Value must be a positive integer.
- Higher values increase disk usage but provide deeper history in `/v1/telemetry` responses.

### Service Configuration

#### VLM_SERVICE_PORT

**Description**: The port number on which the FastAPI server will run.

**Default**: `9764`

**Examples**:

```bash
export VLM_SERVICE_PORT=9764  # Default
export VLM_SERVICE_PORT=8080  # Custom port
```

#### WORKERS

**Description**: Number of Uvicorn worker processes.

**Default**: `1`

**Examples**:

```bash
export WORKERS=1   # Default (automatically set for GPU)
export WORKERS=4   # Multiple workers for CPU
```

**Note**: When using GPU (`VLM_DEVICE=GPU`), this is automatically set to 1 for optimal performance.

### Authentication

#### HUGGINGFACE_TOKEN

**Description**:

To run a **GATED MODEL** like Llama models, the user will need to pass their [huggingface token](https://huggingface.co/docs/hub/security-tokens#user-access-tokens). The user will need to request access to specific model by going to the respective model page on HuggingFace.

_Go to [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) to get your token._

**Default**: None

**Examples**:

```bash
export HUGGINGFACE_TOKEN=hf_your_token_here
```

**When Required**:

- Accessing gated models (e.g., some Llama models)
- Accessing private models
- Models requiring authentication

**How to Obtain**:

1. Visit [huggingface token](https://huggingface.co/docs/hub/security-tokens#user-access-tokens)
2. Log in to your Hugging Face account
3. Create or copy your existing access token
4. Get access to the model you want to use from the Hugging Face Hub
5. Set it using the export command

**Note**: Only set this if you need to access gated or private models. Public models don't require authentication.

### Network Configuration

#### http_proxy, https_proxy, no_proxy_env

**Description**: Proxy configuration for network requests.

**Examples**:

```bash
export http_proxy=http://proxy.company.com:8080
export https_proxy=http://proxy.company.com:8080
export no_proxy_env=localhost,127.0.0.1,.local
```

### Container Configuration

#### TAG, REGISTRY, PROJECT_NAME

**Description**: Docker image configuration.

**Examples**:

```bash
export TAG=latest              # Docker image tag
export REGISTRY_URL=docker.io/     # Docker registry URL
export PROJECT_NAME=my_project   # Docker project name
```

## Environment Variables Usage Examples

### Basic Setup (CPU)

```bash
# Minimal required configuration
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
source setup.sh
```

### GPU Acceleration

```bash
# GPU configuration with performance optimization
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_DEVICE=GPU
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT"}'
source setup.sh
```

### Production Setup

```bash
# Production configuration with clean logging
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_DEVICE=CPU
export VLM_LOG_LEVEL=warning
export VLM_ACCESS_LOG_FILE="/dev/null"
export VLM_MAX_COMPLETION_TOKENS=1000
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT", "NUM_STREAMS": 2}'
source setup.sh
```

### Debug Setup

```bash
# Debug configuration with verbose logging
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_LOG_LEVEL=debug
export VLM_ACCESS_LOG_FILE="-"
source setup.sh
```

### Multi-GPU Setup

```bash
# Specific GPU device with custom configuration
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-3B-Instruct
export VLM_DEVICE=GPU.0
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT", "CACHE_DIR": "/tmp/ov_cache"}'
source setup.sh
```

### Gated Model Access

```bash
# Access gated models with authentication
export VLM_MODEL_NAME=microsoft/Phi-3.5-vision-instruct
export HUGGINGFACE_TOKEN=hf_your_token_here
export VLM_DEVICE=GPU
source setup.sh
```

## Advanced Configuration

### Performance Tuning

For optimal performance, consider these configurations based on your hardware:

**High-End CPU (8+ cores)**:

```bash
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT", "INFERENCE_NUM_THREADS": 8, "NUM_STREAMS": 4}'
export WORKERS=2
```

**GPU with Limited Memory**:

```bash
export VLM_DEVICE=GPU
export VLM_COMPRESSION_WEIGHT_FORMAT=int4
export OV_CONFIG='{"PERFORMANCE_HINT": "LATENCY"}'
```

**High Throughput Server**:

```bash
export OV_CONFIG='{"PERFORMANCE_HINT": "THROUGHPUT", "NUM_STREAMS": 8}'
export VLM_MAX_COMPLETION_TOKENS=500
```

### Development vs Production

**Development Configuration**:

```bash
export VLM_LOG_LEVEL=debug
export VLM_ACCESS_LOG_FILE="-"
export VLM_DEVICE=CPU
```

**Production Configuration**:

```bash
export VLM_LOG_LEVEL=warning
export VLM_ACCESS_LOG_FILE="/dev/null"
export VLM_DEVICE=GPU
export VLM_MAX_COMPLETION_TOKENS=1000
```

## Environment Variables Priority

1. **Explicitly exported variables** (highest priority)
2. **Setup script defaults**
3. **Application defaults** (lowest priority)

Variables set with `export` before running the setup script will override the setup script's defaults.

## Validation and Troubleshooting

### Common Issues

1. **Invalid OV_CONFIG**: Ensure the JSON string is properly formatted
2. **Model Access**: Check if `HUGGINGFACE_TOKEN` is required for your model
3. **GPU Not Found**: Verify GPU drivers and OpenVINO GPU support
4. **Permission Errors**: Check if the `ov-models` volume has correct permissions

### Validation Commands

```bash
# Check device availability
curl 'http://localhost:9764/device'

# Check service health
curl 'http://localhost:9764/health'

# Verify model loading (check logs)
docker logs vlm-openvino-serving
```

## References

- [OpenVINO Documentation](https://docs.openvino.ai/2025/openvino-workflow/running-inference/inference-devices-and-modes.html)
- [Hugging Face Tokens](https://huggingface.co/docs/hub/security-tokens#user-access-tokens)
- [Docker Environment Variables](https://docs.docker.com/compose/environment-variables/)
