# Build License Plate Recognition Pipeline Using API

This guide shows how to create and test an LPR pipeline with the ViPPET REST API.

For LPR architecture and pipeline variants, see the
[License Plate Recognition pipeline guide](./license-plate-recognition-pipeline.md).

For full endpoint and schema details, see the [API Reference](../api-reference.md).

## API Base URL

The OpenAPI server path is `/api/v1`.

Example local base URL:

```text
http://localhost:7860/api/v1
```

## Prerequisites

Before starting, verify the API is ready and check available resources:

```bash
# Check API health
curl -X GET "http://localhost:7860/api/v1/health"

# Check detailed status
curl -X GET "http://localhost:7860/api/v1/status"

# List available models (look for LPR models)
curl -X GET "http://localhost:7860/api/v1/models" | jq '.[] | select(.category == "detection" or .name | contains("license"))'

# List available devices
curl -X GET "http://localhost:7860/api/v1/devices"

# List input videos
curl -X GET "http://localhost:7860/api/v1/videos"
```

## 1) Convert pipeline description to graph

Use `POST /convert/to-graph` with a complete LPR pipeline description.

```bash
curl -X POST "http://localhost:7860/api/v1/convert/to-graph" \
  -H "Content-Type: application/json" \
  -d @- << EOF | jq '.'
{
  "pipeline_description": "filesrc location=/videos/input/license-plate-detection.mp4 ! decodebin3 ! videoconvert ! gvadetect model=vehicle-detection-0202 device=CPU ! gvadetect model=license-plate-detection-0106 device=CPU ! gvaclassify model=license-plate-recognition-barrier-0001 device=CPU ! gvawatermark ! videoconvert ! fakesink"
}
EOF
```

Store `pipeline_graph` and `pipeline_graph_simple` from the response.

Example response structure:

```json
{
  "pipeline_graph": {
    "nodes": [...],
    "edges": [...]
  },
  "pipeline_graph_simple": {
    "nodes": [...],
    "edges": [...]
  }
}
```

## 2) Create user-defined LPR pipeline

Use `POST /pipelines` with schema `PipelineDefinition`. Replace the placeholder graphs with actual values from step 1:

```bash
# Store graphs from previous step (replace with actual JSON from step 1)
PIPELINE_GRAPH='{"nodes":[...],"edges":[...]}'  # From step 1 response
SIMPLE_GRAPH='{"nodes":[...],"edges":[...]}'    # From step 1 response

curl -X POST "http://localhost:7860/api/v1/pipelines" \
  -H "Content-Type: application/json" \
  -d @- << EOF | jq '.id'
{
  "name": "license-plate-recognition",
  "description": "Complete LPR pipeline: vehicle detection -> plate detection -> OCR",
  "tags": ["LPR", "Smart Cities", "Transportation"],
  "variants": [
    {
      "name": "CPU",
      "pipeline_graph": $PIPELINE_GRAPH,
      "pipeline_graph_simple": $SIMPLE_GRAPH
    }
  ]
}
EOF
```

Save the `pipeline ID` from the response for subsequent steps.

## 3) Validate pipeline graph

Use `POST /pipelines/validate` to ensure the pipeline is syntactically correct and can run.

```bash
PIPELINE_ID="pipeline-abc123"  # From step 2

# Start validation
VALIDATION_RESPONSE=$(curl -X POST "http://localhost:7860/api/v1/pipelines/validate" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "pipeline_graph": $PIPELINE_GRAPH,
  "parameters": {"max-runtime": 30}
}
EOF
)

JOB_ID=$(echo $VALIDATION_RESPONSE | jq -r '.job_id')
echo "Validation job started: $JOB_ID"

# Monitor validation progress
while true; do
  STATUS=$(curl -s "http://localhost:7860/api/v1/jobs/validation/$JOB_ID/status")
  STATE=$(echo $STATUS | jq -r '.state')
  
  case $STATE in
    "COMPLETED")
      IS_VALID=$(echo $STATUS | jq -r '.is_valid')
      if [ "$IS_VALID" = "true" ]; then
        echo "Pipeline validation successful"
        break
      else
        echo "Pipeline validation failed:"
        echo $STATUS | jq '.details'
        exit 1
      fi
      ;;
    "FAILED")
      echo "Validation error:"
      echo $STATUS | jq '.details'
      exit 1
      ;;
    "RUNNING")
      echo "Validation in progress..."
      sleep 2
      ;;
  esac
done
```

## 4) Optimize pipeline (recommended)

Before performance testing, optimize the pipeline for better throughput:

```bash
VARIANT_ID="cpu"  # Replace with actual variant_id from the pipeline

# Start optimization
OPT_RESPONSE=$(curl -X POST "http://localhost:7860/api/v1/pipelines/$PIPELINE_ID/variants/$VARIANT_ID/optimize" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "type": "optimize",
  "parameters": {
    "search_duration": 180,
    "sample_duration": 10
  }
}
EOF
)

OPT_JOB_ID=$(echo $OPT_RESPONSE | jq -r '.job_id')

# Monitor optimization (this may take several minutes)
while true; do
  STATUS=$(curl -s "http://localhost:7860/api/v1/jobs/optimization/$OPT_JOB_ID/status")
  STATE=$(echo $STATUS | jq -r '.state')
  
  case $STATE in
    "COMPLETED")
      echo "Optimization completed"
      OPTIMIZED_FPS=$(echo $STATUS | jq '.total_fps')
      echo "Optimized pipeline FPS: $OPTIMIZED_FPS"
      
      # Create optimized variant
      OPTIMIZED_GRAPH=$(echo $STATUS | jq '.optimized_pipeline_graph')
      OPTIMIZED_SIMPLE=$(echo $STATUS | jq '.optimized_pipeline_graph_simple')
      curl -X POST "http://localhost:7860/api/v1/pipelines/$PIPELINE_ID/variants" \
        -H "Content-Type: application/json" \
        -d @- << EOF
{
  "name": "CPU-Optimized",
  "pipeline_graph": $OPTIMIZED_GRAPH,
  "pipeline_graph_simple": $OPTIMIZED_SIMPLE
}
EOF
      break
      ;;
    "FAILED")
      echo "Optimization failed, continuing with original pipeline"
      echo $STATUS | jq '.details'
      break
      ;;
    "RUNNING")
      ELAPSED=$(echo $STATUS | jq '.elapsed_time')
      echo "Optimization running... (${ELAPSED}ms elapsed)"
      sleep 10
      ;;
  esac
done
```

## 5) Run performance test

Use `POST /tests/performance` with schema `PerformanceTestSpec`. Test both original and optimized variants:

```bash
# Performance test with multiple variants
PERF_RESPONSE=$(curl -X POST "http://localhost:7860/api/v1/tests/performance" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "pipeline_performance_specs": [
    {
      "pipeline": {
        "source": "variant",
        "pipeline_id": "$PIPELINE_ID",
        "variant_id": "cpu"
      },
      "streams": 2
    },
    {
      "pipeline": {
        "source": "variant",
        "pipeline_id": "$PIPELINE_ID",
        "variant_id": "cpu-optimized"
      },
      "streams": 4
    }
  ],
  "execution_config": {
    "output_mode": "disabled",
    "max_runtime": 60
  }
}
EOF
)

PERF_JOB_ID=$(echo $PERF_RESPONSE | jq -r '.job_id')

# Monitor performance test
while true; do
  STATUS=$(curl -s "http://localhost:7860/api/v1/jobs/tests/performance/$PERF_JOB_ID/status")
  STATE=$(echo $STATUS | jq -r '.state')
  
  case $STATE in
    "COMPLETED")
      echo "Performance test completed"
      echo "Results:"
      echo "  Total FPS: $(echo $STATUS | jq '.total_fps')"
      echo "  Per-stream FPS: $(echo $STATUS | jq '.per_stream_fps')"
      echo "  Total streams: $(echo $STATUS | jq '.total_streams')"
      echo "  Pipeline breakdown:"
      echo $STATUS | jq '.streams_per_pipeline'
      break
      ;;
    "FAILED")
      echo "Performance test failed:"
      echo $STATUS | jq '.details'
      exit 1
      ;;
    "RUNNING")
      ELAPSED=$(echo $STATUS | jq '.elapsed_time')
      CURRENT_FPS=$(echo $STATUS | jq '.total_fps // "measuring..."')
      echo "Performance test running... (${ELAPSED}ms, FPS: $CURRENT_FPS)"
      sleep 5
      ;;
  esac
done
```

## 6) Track performance job

Use these endpoints to monitor job progress:

- `GET /jobs/tests/performance/{job_id}/status`
- `GET /jobs/tests/performance/{job_id}`

```bash
# Get detailed status
curl -X GET "http://localhost:7860/api/v1/jobs/tests/performance/$PERF_JOB_ID/status" | jq '.'

# Get job summary
curl -X GET "http://localhost:7860/api/v1/jobs/tests/performance/$PERF_JOB_ID" | jq '.'

# List all performance jobs
curl -X GET "http://localhost:7860/api/v1/jobs/tests/performance/status" | jq '.'
```

## 7) Optional: run density test

Use `POST /tests/density` with schema `DensityTestSpec`  to find maximum throughput:

```bash
# Find maximum streams while maintaining 25 FPS per stream
DENSITY_RESPONSE=$(curl -X POST "http://localhost:7860/api/v1/tests/density" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "fps_floor": 25,
  "pipeline_density_specs": [
    {
      "pipeline": {
        "source": "variant",
        "pipeline_id": "$PIPELINE_ID",
        "variant_id": "cpu-optimized"
      },
      "stream_rate": 100
    }
  ],
  "execution_config": {
    "output_mode": "disabled",
    "max_runtime": 120
  }
}
EOF
)

DENSITY_JOB_ID=$(echo $DENSITY_RESPONSE | jq -r '.job_id')

# Monitor density test
while true; do
  STATUS=$(curl -s "http://localhost:7860/api/v1/jobs/tests/density/$DENSITY_JOB_ID/status")
  STATE=$(echo $STATUS | jq -r '.state')
  
  case $STATE in
    "COMPLETED")
      echo "Density test completed"
      echo "Maximum streams: $(echo $STATUS | jq '.total_streams')"
      echo "Achieved FPS per stream: $(echo $STATUS | jq '.per_stream_fps')"
      break
      ;;
    "FAILED")
      echo "Density test failed"
      break
      ;;
    "RUNNING")
      CURRENT_STREAMS=$(echo $STATUS | jq '.total_streams // "testing..."')
      echo "Density test running... (Current streams: $CURRENT_STREAMS)"
      sleep 10
      ;;
  esac
done

# Check density job details
curl -X GET "http://localhost:7860/api/v1/jobs/tests/density/$DENSITY_JOB_ID/status"
curl -X GET "http://localhost:7860/api/v1/jobs/tests/density/$DENSITY_JOB_ID"

```

## 8) Advanced: Live Camera Integration

Create camera-based variant.

```bash
# List available cameras
curl -X GET "http://localhost:7860/api/v1/cameras"

# For ONVIF cameras, load profiles with authentication
curl -X POST "http://localhost:7860/api/v1/cameras/network-camera-192.168.1.100-80/profiles" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "username": "admin",
  "password": "password123"
}
EOF

# Create live camera variant
curl -X POST "http://localhost:7860/api/v1/pipelines/$PIPELINE_ID/variants" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "name": "Live-Camera",
  "pipeline_graph": {
    "nodes": [
      {"id": "0", "type": "rtspsrc", "data": {"location": "rtsp://192.168.1.100:554/stream1", "latency": "200"}},
      {"id": "1", "type": "rtph264depay", "data": {}},
      {"id": "2", "type": "h264parse", "data": {}},
      {"id": "3", "type": "avdec_h264", "data": {}},
      {"id": "4", "type": "videoconvert", "data": {}},
      {"id": "5", "type": "gvadetect", "data": {"model": "vehicle-detection-0202", "device": "GPU"}},
      {"id": "6", "type": "gvadetect", "data": {"model": "license-plate-detection-0106", "device": "GPU"}},
      {"id": "7", "type": "gvaclassify", "data": {"model": "license-plate-recognition-barrier-0001", "device": "GPU"}},
      {"id": "8", "type": "gvawatermark", "data": {}},
      {"id": "9", "type": "videoconvert", "data": {}},
      {"id": "10", "type": "autovideosink", "data": {}}
    ],
    "edges": [
      {"id": "0", "source": "0", "target": "1"},
      {"id": "1", "source": "1", "target": "2"},
      {"id": "2", "source": "2", "target": "3"},
      {"id": "3", "source": "3", "target": "4"},
      {"id": "4", "source": "4", "target": "5"},
      {"id": "5", "source": "5", "target": "6"},
      {"id": "6", "source": "6", "target": "7"},
      {"id": "7", "source": "7", "target": "8"},
      {"id": "8", "source": "8", "target": "9"},
      {"id": "9", "source": "9", "target": "10"}
    ]
  },
  "pipeline_graph_simple": {
    "nodes": [
      {"id": "0", "type": "rtspsrc", "data": {"location": "rtsp://192.168.1.100:554/stream1"}},
      {"id": "5", "type": "gvadetect", "data": {"model": "vehicle-detection-0202"}},
      {"id": "6", "type": "gvadetect", "data": {"model": "license-plate-detection-0106"}},
      {"id": "7", "type": "gvaclassify", "data": {"model": "license-plate-recognition-barrier-0001"}},
      {"id": "10", "type": "autovideosink", "data": {}}
    ],
    "edges": [
      {"id": "0", "source": "0", "target": "5"},
      {"id": "1", "source": "5", "target": "6"},
      {"id": "2", "source": "6", "target": "7"},
      {"id": "3", "source": "7", "target": "10"}
    ]
  }
}
EOF
```

Test with live streaming output

```bash
# Performance test with live stream output
curl -X POST "http://localhost:7860/api/v1/tests/performance" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "pipeline_performance_specs": [
    {
      "pipeline": {
        "source": "variant",
        "pipeline_id": "$PIPELINE_ID",
        "variant_id": "live-camera"
      },
      "streams": 2
    }
  ],
  "execution_config": {
    "output_mode": "live_stream",
    "max_runtime": 300
  }
}
EOF
```

## 9) Troubleshooting

Common issues when pipeline validation fails:

```bash
# Check model availability
curl -X GET "http://localhost:7860/api/v1/models" | jq '.[] | select(.name | contains("license"))'

# Check video file exists
curl -X GET "http://localhost:7860/api/v1/videos" | jq '.[] | select(.filename | contains("license"))'

# Verify device availability
curl -X GET "http://localhost:7860/api/v1/devices"
```

### Common Issues

#### Performance test shows low FPS

- Try GPU variants if available
- Reduce input resolution using videoscale and capsfilter
- Use optimized pipeline variants
- Check system resources (CPU, memory, GPU utilization)
- Reduce number of parallel streams

#### Camera connection fails

- Verify RTSP URL accessibility: `ffplay rtsp://camera-ip:port/stream`
- Check network connectivity: `ping camera-ip`
- Validate ONVIF credentials
- Try different latency settings in rtspsrc

#### Job gets stuck in RUNNING state

- Check job details for error messages
- Verify input files are accessible
- Monitor system resources
- Stop job if needed: `DELETE /jobs/tests/performance/{job_id}`

## 10) Complete Example Script

```bash
#!/bin/bash
set -e

BASE_URL="http://localhost:7860/api/v1"
VIDEO_FILE="/videos/input/license-plate-detection.mp4"

echo "Starting LPR Pipeline Creation..."

# 1. Convert pipeline description
echo "Converting pipeline description to graph..."
GRAPH_RESPONSE=$(curl -s -X POST "$BASE_URL/convert/to-graph" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "pipeline_description": "filesrc location=$VIDEO_FILE ! decodebin3 ! videoconvert ! gvadetect model=vehicle-detection-0202 device=CPU ! gvadetect model=license-plate-detection-0106 device=CPU ! gvaclassify model=license-plate-recognition-barrier-0001 device=CPU ! gvawatermark ! videoconvert ! fakesink"
}
EOF
)

PIPELINE_GRAPH=$(echo $GRAPH_RESPONSE | jq '.pipeline_graph')
SIMPLE_GRAPH=$(echo $GRAPH_RESPONSE | jq '.pipeline_graph_simple')

# 2. Create pipeline
echo "Creating LPR pipeline..."
PIPELINE_RESPONSE=$(curl -s -X POST "$BASE_URL/pipelines" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "name": "license-plate-recognition",
  "description": "Complete LPR pipeline: vehicle detection -> plate detection -> OCR",
  "tags": ["LPR", "Smart Cities", "Transportation"],
  "variants": [
    {
      "name": "CPU",
      "pipeline_graph": $PIPELINE_GRAPH,
      "pipeline_graph_simple": $SIMPLE_GRAPH
    }
  ]
}
EOF
)

PIPELINE_ID=$(echo $PIPELINE_RESPONSE | jq -r '.id')
echo "Pipeline created: $PIPELINE_ID"

# 3. Validate pipeline
echo "Validating pipeline..."
VALIDATION_RESPONSE=$(curl -s -X POST "$BASE_URL/pipelines/validate" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "pipeline_graph": $PIPELINE_GRAPH,
  "parameters": {"max-runtime": 30}
}
EOF
)

VALIDATION_JOB_ID=$(echo $VALIDATION_RESPONSE | jq -r '.job_id')

# Wait for validation
while true; do
  STATUS=$(curl -s "$BASE_URL/jobs/validation/$VALIDATION_JOB_ID/status")
  STATE=$(echo $STATUS | jq -r '.state')
  
  if [ "$STATE" = "COMPLETED" ]; then
    IS_VALID=$(echo $STATUS | jq -r '.is_valid')
    if [ "$IS_VALID" = "true" ]; then
      echo "Pipeline validation successful"
      break
    else
      echo "Pipeline validation failed"
      echo $STATUS | jq '.details'
      exit 1
    fi
  elif [ "$STATE" = "FAILED" ]; then
    echo "Validation error"
    echo $STATUS | jq '.details'
    exit 1
  fi
  
  sleep 2
done

# 4. Run performance test
echo "Running performance test..."
PERF_RESPONSE=$(curl -s -X POST "$BASE_URL/tests/performance" \
  -H "Content-Type: application/json" \
  -d @- << EOF
{
  "pipeline_performance_specs": [
    {
      "pipeline": {
        "source": "variant",
        "pipeline_id": "$PIPELINE_ID",
        "variant_id": "cpu"
      },
      "streams": 2
    }
  ],
  "execution_config": {
    "output_mode": "disabled",
    "max_runtime": 60
  }
}
EOF
)

PERF_JOB_ID=$(echo $PERF_RESPONSE | jq -r '.job_id')
echo "Performance job started: $PERF_JOB_ID"
```

## Related Guides

- [License Plate Recognition pipeline guide](./license-plate-recognition-pipeline.md)
- [Configure pipelines guide](./configure-pipelines.md)
- [API Reference](../api-reference.md)
