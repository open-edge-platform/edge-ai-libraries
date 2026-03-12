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
  -d '{
    "pipeline_description": "filesrc location=/videos/input/license-plate-detection.mp4 ! decodebin3 ! videoconvert ! gvadetect model=vehicle-detection-0202 device=CPU ! gvadetect model=license-plate-detection-0106 device=CPU ! gvaclassify model=license-plate-recognition-barrier-0001 device=CPU ! gvawatermark ! videoconvert ! fakesink"
  }' | jq '.'
```

Store `pipeline_graph` and `pipeline_graph_simple` from the response.

Example response structure:
```JSON
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
  -d "{
    \"name\": \"license-plate-recognition\",
    \"description\": \"Complete LPR pipeline: vehicle detection → plate detection → OCR\",
    \"tags\": [\"LPR\", \"Smart Cities\", \"Transportation\"],
    \"variants\": [
      {
        \"name\": \"CPU\",
        \"pipeline_graph\": $PIPELINE_GRAPH,
        \"pipeline_graph_simple\": $SIMPLE_GRAPH
      }
    ]
  }" | jq '.id'
```

Save the `pipeline ID` from the response for subsequent steps.

## 3) Validate pipeline graph

Use `POST /pipelines/validate`to ensure the pipeline is syntactically correct and can run.

```bash
PIPELINE_ID="pipeline-abc123"  # From step 2

# Start validation
VALIDATION_RESPONSE=$(curl -X POST "http://localhost:7860/api/v1/pipelines/validate" \
  -H "Content-Type: application/json" \
  -d "{
    \"pipeline_graph\": $PIPELINE_GRAPH,
    \"parameters\": {\"max-runtime\": 30}
  }")

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
        echo "✅ Pipeline validation successful"
        break
      else
        echo "❌ Pipeline validation failed:"
        echo $STATUS | jq '.details'
        exit 1
      fi
      ;;
    "FAILED")
      echo "❌ Validation error:"
      echo $STATUS | jq '.details'
      exit 1
      ;;
    "RUNNING")
      echo "⏳ Validation in progress..."
      sleep 2
      ;;
  esac
done
```
## 4) Optimize pipeline (recommended)
Before performance testing, optimize the pipeline for better throughput:
```bash
# Start optimization
OPT_RESPONSE=$(curl -X POST "http://localhost:7860/api/v1/pipelines/$PIPELINE_ID/variants/cpu/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "optimize",
    "parameters": {
      "search_duration": 180,
      "sample_duration": 10
    }
  }')

OPT_JOB_ID=$(echo $OPT_RESPONSE | jq -r '.job_id')

# Monitor optimization (this may take several minutes)
while true; do
  STATUS=$(curl -s "http://localhost:7860/api/v1/jobs/optimization/$OPT_JOB_ID/status")
  STATE=$(echo $STATUS | jq -r '.state')
  
  case $STATE in
    "COMPLETED")
      echo "✅ Optimization completed"
      OPTIMIZED_FPS=$(echo $STATUS | jq '.total_fps')
      echo "Optimized pipeline FPS: $OPTIMIZED_FPS"
      
      # Create optimized variant
      OPTIMIZED_GRAPH=$(echo $STATUS | jq '.optimized_pipeline_graph')
      OPTIMIZED_SIMPLE=$(echo $STATUS | jq '.optimized_pipeline_graph_simple')
      curl -X POST "http://localhost:7860/api/v1/pipelines/$PIPELINE_ID/variants" \
        -H "Content-Type: application/json" \
        -d "{
          \"name\": \"CPU-Optimized\",
          \"pipeline_graph\": $OPTIMIZED_GRAPH,
          \"pipeline_graph_simple\": $OPTIMIZED_SIMPLE
        }"
      break
      ;;
    "FAILED")
      echo "⚠️ Optimization failed, continuing with original pipeline"
      echo $STATUS | jq '.details'
      break
      ;;
    "RUNNING")
      ELAPSED=$(echo $STATUS | jq '.elapsed_time')
      echo "⏳ Optimization running... (${ELAPSED}ms elapsed)"
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
  -d "{
    \"pipeline_performance_specs\": [
      {
        \"pipeline\": {
          \"source\": \"variant\",
          \"pipeline_id\": \"$PIPELINE_ID\",
          \"variant_id\": \"cpu\"
        },
        \"streams\": 2
      },
      {
        \"pipeline\": {
          \"source\": \"variant\",
          \"pipeline_id\": \"$PIPELINE_ID\",
          \"variant_id\": \"cpu-optimized\"
        },
        \"streams\": 4
      }
    ],
    \"execution_config\": {
      \"output_mode\": \"disabled\",
      \"max_runtime\": 60
    }
  }")

PERF_JOB_ID=$(echo $PERF_RESPONSE | jq -r '.job_id')

# Monitor performance test
while true; do
  STATUS=$(curl -s "http://localhost:7860/api/v1/jobs/tests/performance/$PERF_JOB_ID/status")
  STATE=$(echo $STATUS | jq -r '.state')
  
  case $STATE in
    "COMPLETED")
      echo "✅ Performance test completed!"
      echo "Results:"
      echo "  Total FPS: $(echo $STATUS | jq '.total_fps')"
      echo "  Per-stream FPS: $(echo $STATUS | jq '.per_stream_fps')"
      echo "  Total streams: $(echo $STATUS | jq '.total_streams')"
      echo "  Pipeline breakdown:"
      echo $STATUS | jq '.streams_per_pipeline'
      break
      ;;
    "FAILED")
      echo "❌ Performance test failed:"
      echo $STATUS | jq '.details'
      exit 1
      ;;
    "RUNNING")
      ELAPSED=$(echo $STATUS | jq '.elapsed_time')
      CURRENT_FPS=$(echo $STATUS | jq '.total_fps // "measuring..."')
      echo "⏳ Performance test running... (${ELAPSED}ms, FPS: $CURRENT_FPS)"
      sleep 5
      ;;
  esac
done
```

## 5) Track performance job

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

## 6) Optional: run density test

Use `POST /tests/density` with schema `DensityTestSpec`  to find maximum throughput:

```bash
# Find maximum streams while maintaining 25 FPS per stream
DENSITY_RESPONSE=$(curl -X POST "http://localhost:7860/api/v1/tests/density" \
  -H "Content-Type: application/json" \
  -d "{
    \"fps_floor\": 25,
    \"pipeline_density_specs\": [
      {
        \"pipeline\": {
          \"source\": \"variant\",
          \"pipeline_id\": \"$PIPELINE_ID\",
          \"variant_id\": \"cpu-optimized\"
        },
        \"stream_rate\": 100
      }
    ],
    \"execution_config\": {
      \"output_mode\": \"disabled\",
      \"max_runtime\": 120
    }
  }")

DENSITY_JOB_ID=$(echo $DENSITY_RESPONSE | jq -r '.job_id')

# Monitor density test
while true; do
  STATUS=$(curl -s "http://localhost:7860/api/v1/jobs/tests/density/$DENSITY_JOB_ID/status")
  STATE=$(echo $STATUS | jq -r '.state')
  
  case $STATE in
    "COMPLETED")
      echo "✅ Density test completed!"
      echo "Maximum streams: $(echo $STATUS | jq '.total_streams')"
      echo "Achieved FPS per stream: $(echo $STATUS | jq '.per_stream_fps')"
      break
      ;;
    "FAILED")
      echo "❌ Density test failed"
      break
      ;;
    "RUNNING")
      CURRENT_STREAMS=$(echo $STATUS | jq '.total_streams // "testing..."')
      echo "⏳ Density test running... (Current streams: $CURRENT_STREAMS)"
      sleep 10
      ;;
  esac
done

# Check density job details
curl -X GET "http://localhost:7860/api/v1/jobs/tests/density/$DENSITY_JOB_ID/status"
curl -X GET "http://localhost:7860/api/v1/jobs/tests/density/$DENSITY_JOB_ID"

```



## Related Guides

- [License Plate Recognition pipeline guide](./license-plate-recognition-pipeline.md)
- [Configure pipelines guide](./configure-pipelines.md)
- [API Reference](../api-reference.md)
