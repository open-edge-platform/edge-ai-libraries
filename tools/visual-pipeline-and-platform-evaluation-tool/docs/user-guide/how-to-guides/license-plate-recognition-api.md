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

## 1) Convert pipeline description to graph

Use `POST /convert/to-graph`.

```bash
curl -X POST "http://localhost:7860/api/v1/convert/to-graph" \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_description": "filesrc location=/videos/input/license-plate-detection.mp4 ! decodebin3 ! ... ! fakesink"
  }'
```

Store `pipeline_graph` and `pipeline_graph_simple` from the response.

## 2) Create user-defined LPR pipeline

Use `POST /pipelines` with schema `PipelineDefinition`.

```bash
curl -X POST "http://localhost:7860/api/v1/pipelines" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "license-plate-recognition",
    "description": "Detect, track, and OCR license plates",
    "source": "USER_CREATED",
    "tags": ["Smart Cities", "Transportation", "LPR"],
    "variants": [
      {
        "name": "CPU",
        "pipeline_graph": {"nodes": [], "edges": []},
        "pipeline_graph_simple": {"nodes": [], "edges": []}
      }
    ]
  }'
```

Replace placeholder graph objects with real values from step 1.

## 3) Validate pipeline graph

Use `POST /pipelines/validate`.

```bash
curl -X POST "http://localhost:7860/api/v1/pipelines/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_graph": {"nodes": [], "edges": []},
    "parameters": null
  }'
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
