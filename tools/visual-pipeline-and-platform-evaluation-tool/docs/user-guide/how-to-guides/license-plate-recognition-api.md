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

## 4) Run performance test

Use `POST /tests/performance` with schema `PerformanceTestSpec`.

```bash
curl -X POST "http://localhost:7860/api/v1/tests/performance" \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_performance_specs": [
      {
        "pipeline": {
          "source": "variant",
          "pipeline_id": "<pipeline_id>",
          "variant_id": "<variant_id>"
        },
        "streams": 1
      }
    ],
    "execution_config": {
      "output_mode": "disabled",
      "max_runtime": 30
    }
  }'
```

## 5) Track performance job

Use:

- `GET /jobs/tests/performance/{job_id}/status`
- `GET /jobs/tests/performance/{job_id}`

## 6) Optional: run density test

Use `POST /tests/density` with schema `DensityTestSpec` and then check:

- `GET /jobs/tests/density/{job_id}/status`
- `GET /jobs/tests/density/{job_id}`

## Related Guides

- [License Plate Recognition pipeline guide](./license-plate-recognition-pipeline.md)
- [Configure pipelines guide](./configure-pipelines.md)
- [API Reference](../api-reference.md)
