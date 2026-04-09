# Semantic Comparison Service

AI-powered semantic comparison service for item matching and validation. Consolidates semantic matching logic from multiple applications into a single, extensible, production-ready microservice.

## Features

- **Multiple Matching Strategies**:
  - Exact matching (fast string comparison)
  - Semantic matching (VLM/LLM-based)
  - Hybrid matching (exact first, semantic fallback)

- **Flexible VLM Backends**:
  - OVMS (OpenVINO Model Server) - GPU-accelerated, supports batching
  - OpenVINO GenAI (local) - In-process inference
  - OpenAI API (cloud fallback)

- **Production-Ready**:
  - FastAPI with async support
  - Pydantic models for validation
  - Structured logging
  - Prometheus metrics
  - Health checks
  - Response caching (memory/Redis)

- **Comprehensive Testing**:
  - Unit tests for all components
  - Integration tests for API endpoints
  - 80%+ code coverage

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (optional)
- **External VLM/OVMS server** (optional - only if using semantic/hybrid matching)
  - If you want semantic matching, you'll need an OVMS instance with a vision-language model
  - Or use OpenVINO local inference
  - Or use OpenAI API

### Local Development

1. **Clone and setup**:
```bash
cd semantic-search-agent
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure**:
```bash
cp .env.example .env
# Edit .env with your settings
```

3. **Run service**:
```bash
uvicorn app.main:app --reload --port 8080
```

4. **Test**:
```bash
# Run tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Access API docs
open http://localhost:8080/docs
```

### Docker Deployment

#### Minimum Required Environment Variables

**Basic deployment (exact matching only - no VLM):**
```bash
# Copy and edit .env
cp .env.example .env

# Minimum required in .env:
DEFAULT_MATCHING_STRATEGY=exact    # No VLM needed
API_PORT=8080                      # Service port
LOG_LEVEL=INFO                     # Logging level
```

**With VLM support (semantic/hybrid matching):**
```bash
# In addition to above, add:
DEFAULT_MATCHING_STRATEGY=hybrid   # or 'semantic'

# Choose ONE VLM backend and provide its required variables:

# Option 1: External OVMS (most common)
VLM_BACKEND=ovms
OVMS_ENDPOINT=http://your-ovms-host:8000    # ⚠️ REQUIRED
OVMS_MODEL_NAME=your-model-name             # ⚠️ REQUIRED

# Option 2: Local OpenVINO
VLM_BACKEND=openvino_local
OPENVINO_MODEL_PATH=/path/to/model          # ⚠️ REQUIRED

# Option 3: OpenAI API
VLM_BACKEND=openai
OPENAI_API_KEY=sk-your-key-here             # ⚠️ REQUIRED
```

---

#### Deployment Steps

**Prerequisites:**
- Docker and Docker Compose installed
- (Optional) External OVMS server if using semantic/hybrid matching

**1. Configure environment:**
```bash
cp .env.example .env
# Edit .env with your configuration:

# For EXACT matching only (no VLM needed):
DEFAULT_MATCHING_STRATEGY=exact

# For SEMANTIC/HYBRID matching (VLM required):
DEFAULT_MATCHING_STRATEGY=hybrid
OVMS_ENDPOINT=http://your-ovms-host:port  # Your external OVMS endpoint
OVMS_MODEL_NAME=your-model-name           # Your VLM model name
# Or use OpenVINO local:
VLM_BACKEND=openvino_local
OPENVINO_MODEL_PATH=/path/to/your/model
# Or use OpenAI:
VLM_BACKEND=openai
OPENAI_API_KEY=your-api-key
```

**2. Build and run:**
```bash
cd docker
docker-compose up -d
```

**3. Check health:**
```bash
curl http://localhost:8080/api/v1/health
```

**4. View logs:**
```bash
cd docker
docker-compose logs -f semantic-service
```

---

**Note:** The service runs without VLM by default using exact matching. VLM is only required if you set `DEFAULT_MATCHING_STRATEGY=semantic` or `hybrid`.

**Environment Variables for Docker:**
- `API_PORT` - Service API port (default: 8080)
- `METRICS_PORT` - Prometheus metrics port (default: 9090)
- `DEFAULT_MATCHING_STRATEGY` - Matching strategy: exact (no VLM), semantic, or hybrid
- `OVMS_ENDPOINT` - Your external OVMS endpoint (required if using OVMS backend)
- `OVMS_MODEL_NAME` - Your VLM model name (required if using OVMS backend)

## API Usage

### Order Validation

Compare expected vs detected items:

```bash
curl -X POST http://localhost:8080/api/v1/compare/order \
  -H "Content-Type: application/json" \
  -d '{
    "expected_items": [
      {"name": "apple", "quantity": 2},
      {"name": "banana", "quantity": 1}
    ],
    "detected_items": [
      {"name": "green apple", "quantity": 2},
      {"name": "orange", "quantity": 1}
    ],
    "options": {
      "use_semantic": true
    }
  }'
```

Response:
```json
{
  "status": "mismatch",
  "validation": {
    "missing": [
      {"name": "banana", "quantity": 1}
    ],
    "extra": [
      {"name": "orange", "quantity": 1}
    ],
    "quantity_mismatch": [],
    "matched": [
      {
        "expected": {"name": "apple", "quantity": 2},
        "detected": {"name": "green apple", "quantity": 2},
        "match_type": "hybrid_semantic",
        "confidence": 0.95
      }
    ]
  },
  "metrics": {
    "total_expected": 2,
    "total_detected": 2,
    "exact_matches": 0,
    "semantic_matches": 1,
    "processing_time_ms": 145.67
  }
}
```

### Inventory Validation

Check if items exist in inventory:

```bash
curl -X POST http://localhost:8080/api/v1/compare/inventory \
  -H "Content-Type: application/json" \
  -d '{
    "items": ["coca cola", "bread", "unknown item"],
    "options": {
      "use_semantic": true
    }
  }'
```

### Semantic Match

Generic semantic comparison:

```bash
curl -X POST http://localhost:8080/api/v1/compare/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "text1": "green apple",
    "text2": "apple",
    "context": "grocery products"
  }'
```

## Configuration

### Environment Variables Reference

#### **Minimum Required Variables (No VLM)**

To run the service with **exact matching only** (no VLM/AI needed), set these variables:

```bash
# .env file
SERVICE_NAME=semantic-search-agent
SERVICE_VERSION=1.0.0
LOG_LEVEL=INFO
API_PORT=8080
METRICS_PORT=9090

# Matching strategy - 'exact' requires no VLM
DEFAULT_MATCHING_STRATEGY=exact
CONFIDENCE_THRESHOLD=0.85
MAX_RETRIES=2

# Caching (optional but recommended)
CACHE_ENABLED=true
CACHE_BACKEND=memory
CACHE_TTL=3600

# Metrics
PROMETHEUS_ENABLED=true
```

**That's it!** The service will run with fast exact string matching. No GPU, no AI model needed.

---

#### **Optional: Adding VLM Support**

To enable **semantic matching** (AI-powered), you must provide VLM backend configuration.

##### **Option 1: External OVMS Server** (Recommended for production)

```bash
# Required variables
DEFAULT_MATCHING_STRATEGY=hybrid     # or 'semantic'
VLM_BACKEND=ovms

# ⚠️ REQUIRED: Your OVMS endpoint and model name
OVMS_ENDPOINT=http://192.168.1.100:8000    # Your OVMS server URL
OVMS_MODEL_NAME=Qwen2-VL-7B-Instruct       # Your VLM model name in OVMS
OVMS_TIMEOUT=30                            # Request timeout (seconds)
```

**Example with actual values:**
```bash
# Real-world OVMS example
OVMS_ENDPOINT=http://ovms-server.company.local:8000
OVMS_MODEL_NAME=vision-model-v2
OVMS_TIMEOUT=60
```

##### **Option 2: Local OpenVINO Inference**

```bash
# Required variables
DEFAULT_MATCHING_STRATEGY=hybrid     # or 'semantic'
VLM_BACKEND=openvino_local

# ⚠️ REQUIRED: Path to your local OpenVINO model
OPENVINO_MODEL_PATH=/opt/models/qwen-vlm-7b-int8
OPENVINO_DEVICE=GPU                  # Options: CPU, GPU, NPU
OPENVINO_MAX_NEW_TOKENS=512
OPENVINO_TEMPERATURE=0.0
```

##### **Option 3: OpenAI Cloud API**

```bash
# Required variables
DEFAULT_MATCHING_STRATEGY=hybrid     # or 'semantic'
VLM_BACKEND=openai

# ⚠️ REQUIRED: Your OpenAI API key
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o-mini             # or gpt-4o, gpt-4-turbo
OPENAI_MAX_TOKENS=100
```

---

#### **Complete Environment Variables List**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| **SERVICE CONFIGURATION** |
| `SERVICE_NAME` | No | `semantic-search-agent` | Service identifier |
| `SERVICE_VERSION` | No | `1.0.0` | Service version |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG/INFO/WARN/ERROR) |
| `API_PORT` | No | `8080` | API server port |
| `METRICS_PORT` | No | `9090` | Prometheus metrics port |
| **MATCHING CONFIGURATION** |
| `DEFAULT_MATCHING_STRATEGY` | **YES** | `exact` | Strategy: `exact` (no VLM), `semantic` (VLM required), `hybrid` (VLM optional) |
| `CONFIDENCE_THRESHOLD` | No | `0.85` | Semantic match confidence threshold (0.0-1.0) |
| `MAX_RETRIES` | No | `2` | Max retries for failed VLM requests |
| **VLM BACKEND (Optional - only if using semantic/hybrid)** |
| `VLM_BACKEND` | No* | `ovms` | VLM backend: `ovms`, `openvino_local`, `openai` |
| **OVMS BACKEND (Required if VLM_BACKEND=ovms)** |
| `OVMS_ENDPOINT` | **YES*** | - | Your OVMS server URL (e.g., `http://10.0.0.5:8000`) |
| `OVMS_MODEL_NAME` | **YES*** | - | Your model name in OVMS |
| `OVMS_TIMEOUT` | No | `30` | Request timeout in seconds |
| **OPENVINO LOCAL (Required if VLM_BACKEND=openvino_local)** |
| `OPENVINO_MODEL_PATH` | **YES*** | - | Path to local OpenVINO model directory |
| `OPENVINO_DEVICE` | No | `GPU` | Device: `CPU`, `GPU`, `NPU` |
| `OPENVINO_MAX_NEW_TOKENS` | No | `512` | Max output tokens |
| `OPENVINO_TEMPERATURE` | No | `0.0` | Sampling temperature |
| **OPENAI (Required if VLM_BACKEND=openai)** |
| `OPENAI_API_KEY` | **YES*** | - | Your OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model name |
| `OPENAI_MAX_TOKENS` | No | `100` | Max completion tokens |
| **CACHING** |
| `CACHE_ENABLED` | No | `true` | Enable response caching |
| `CACHE_BACKEND` | No | `memory` | Cache backend: `memory`, `redis` |
| `CACHE_TTL` | No | `3600` | Cache TTL in seconds |
| `REDIS_HOST` | No* | `redis` | Redis hostname (if CACHE_BACKEND=redis) |
| `REDIS_PORT` | No* | `6379` | Redis port |
| `REDIS_DB` | No | `0` | Redis database number |
| **METRICS & CONFIG** |
| `PROMETHEUS_ENABLED` | No | `true` | Enable Prometheus metrics |
| `CONFIG_DIR` | No | `./config` | Configuration directory |
| `ORDERS_FILE` | No | `./config/orders.json` | Orders database file |
| `INVENTORY_FILE` | No | `./config/inventory.json` | Inventory file |

**\*** Required only when using corresponding feature

---

### Deployment Examples

#### Example 1: Basic Deployment (No VLM)

Minimal setup for exact matching only - **fastest and simplest**:

```bash
# .env
DEFAULT_MATCHING_STRATEGY=exact
API_PORT=8080
LOG_LEVEL=INFO
```

**Start:**
```bash
cd docker && docker-compose up -d
```

**Result:** Service runs with exact string matching. No VLM needed.

---

#### Example 2: With External OVMS (Production)

Using your existing OVMS infrastructure:

```bash
# .env
DEFAULT_MATCHING_STRATEGY=hybrid

# Your OVMS server details
VLM_BACKEND=ovms
OVMS_ENDPOINT=http://192.168.50.100:8000
OVMS_MODEL_NAME=qwen2-vl-7b-instruct
OVMS_TIMEOUT=60

# Service config
API_PORT=8080
LOG_LEVEL=INFO
CACHE_ENABLED=true
CACHE_BACKEND=redis
REDIS_HOST=redis-server.local
```

**Start:**
```bash
cd docker && docker-compose up -d
```

**Result:** Service uses exact matching first, falls back to OVMS for semantic matching.

---

#### Example 3: With Local OpenVINO Model

Running VLM locally on the same machine:

```bash
# .env
DEFAULT_MATCHING_STRATEGY=hybrid

# Local OpenVINO model
VLM_BACKEND=openvino_local
OPENVINO_MODEL_PATH=/data/models/qwen-vlm-2b-int8
OPENVINO_DEVICE=GPU

# Service config
API_PORT=8080
LOG_LEVEL=INFO
```

**Start:**
```bash
cd docker && docker-compose up -d
```

**Result:** Service uses local GPU for VLM inference.

---

#### Example 4: With OpenAI API (Cloud)

Using OpenAI as VLM backend:

```bash
# .env
DEFAULT_MATCHING_STRATEGY=semantic

# OpenAI configuration
VLM_BACKEND=openai
OPENAI_API_KEY=sk-proj-abc123xyz789...
OPENAI_MODEL=gpt-4o-mini

# Service config
API_PORT=8080
LOG_LEVEL=INFO
CACHE_ENABLED=true  # Important for cost savings!
```

**Start:**
```bash
cd docker && docker-compose up -d
```

**Result:** Service uses OpenAI API for semantic matching (costs per request).

---

### Configuration Files

Additional configuration can be set via YAML files:

| File | Purpose |
|------|---------|
| `config/service_config.yaml` | Service-wide settings (matching strategies, VLM config, caching) |
| `config/orders.json` | Expected orders database for validation |
| `config/inventory.json` | Inventory items list for validation |

**Note:** Environment variables override YAML configuration values.

---

## Architecture

```
app/
├── main.py                 # FastAPI application
├── api/
│   ├── routes.py          # API endpoints
│   ├── models.py          # Pydantic models
│   └── dependencies.py    # Dependency injection
├── core/
│   ├── config.py          # Configuration management
│   ├── logger.py          # Structured logging
│   └── metrics.py         # Prometheus metrics
├── services/
│   ├── comparison_engine.py  # Core comparison logic
│   ├── matchers/
│   │   ├── base.py        # BaseMatcher interface
│   │   ├── exact.py       # Exact matching
│   │   ├── semantic.py    # Semantic matching
│   │   └── hybrid.py      # Hybrid strategy
│   └── vlm/
│       ├── base.py        # BaseVLMBackend interface
│       ├── ovms.py        # OVMS backend
│       ├── openvino_local.py  # OpenVINO local
│       └── openai.py      # OpenAI API
└── utils/
    ├── __init__.py        # Text utilities
    └── cache.py           # Caching layer
```

## Integration Examples

### Order Accuracy Application

Replace direct VLM calls with service API:

```python
import httpx

response = httpx.post(
    "http://semantic-service:8080/api/v1/compare/order",
    json={
        "expected_items": expected_items,
        "detected_items": detected_items,
        "options": {"use_semantic": True}
    },
    timeout=30.0
)
validation = response.json()
```

### Loss Prevention Application

Replace inventory set matching:

```python
import httpx

response = httpx.post(
    "http://semantic-service:8080/api/v1/compare/inventory",
    json={
        "items": [item_name],
        "options": {"use_semantic": True}
    },
    timeout=10.0
)
result = response.json()["results"][0]
match = result["match"]
```

## Monitoring

### Prometheus Metrics

Access metrics at `http://localhost:9090/metrics`:

- `api_requests_total` - Total API requests by endpoint/status
- `matches_total` - Total matches by type/result
- `request_duration_seconds` - Request latency histogram
- `vlm_inference_duration_seconds` - VLM inference time
- `cache_hits_total` / `cache_misses_total` - Cache performance
- `vlm_backend_available` - VLM backend health

### Structured Logging

JSON logs with contextual information:

```json
{
  "event": "Semantic match",
  "text1": "apple",
  "text2": "green apple",
  "match": true,
  "confidence": 0.95,
  "timestamp": "2026-01-30T10:30:45.123Z"
}
```

## Testing

Run full test suite:

```bash
# All tests
pytest

# Specific test file
pytest tests/test_matchers.py

# With coverage
pytest --cov=app --cov-report=html

# Verbose output
pytest -v
```

## Performance

### Benchmarks

- **Exact matching**: < 5ms per comparison
- **Semantic matching**: < 100ms per comparison (OVMS)
- **Throughput**: > 50 req/s (exact), > 10 req/s (semantic)
- **Cache hit rate**: 80%+ for repeated queries

### Optimization Tips

1. Enable caching for repeated queries
2. Use hybrid matcher (exact first, semantic fallback)
3. Use OVMS with continuous batching for high throughput
4. Tune `CONFIDENCE_THRESHOLD` to reduce false positives

## Troubleshooting

### VLM Backend Not Available

If you're using semantic/hybrid matching and get VLM errors:

1. **Check your OVMS endpoint** (if using OVMS backend):
```bash
curl ${OVMS_ENDPOINT}/v1/models
# Example: curl http://your-ovms-host:8000/v1/models
```

2. **Verify environment variables**:
```bash
# Check your .env file has correct values
echo $OVMS_ENDPOINT
echo $OVMS_MODEL_NAME
```

3. **Fallback to exact matching**:
```bash
# Edit .env and set:
DEFAULT_MATCHING_STRATEGY=exact
```

### High Latency

1. Check VLM backend latency in metrics
2. Enable caching: `CACHE_ENABLED=true`
3. Use exact matching first: `DEFAULT_MATCHING_STRATEGY=hybrid`
4. Consider using local OpenVINO inference instead of remote OVMS

### Memory Issues

1. Use Redis for caching: `CACHE_BACKEND=redis`
2. Reduce cache TTL: `CACHE_TTL=1800`
3. Limit concurrent requests

## License

Copyright (c) 2026 Intel Corporation

## Support

For issues and questions, contact Intel AI Team.
