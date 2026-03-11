# How to Test Density

This article explains how to run density tests in ViPPET and interpret the results.
A density test finds the maximum number of streams that can run while keeping the target
minimum FPS per stream. Compared to a standard performance test (fixed stream count),
density testing increases the load and searches for the highest stable stream count that
still meets your FPS requirement. Therefore, it answers the question:

"How many concurrent streams can this platform sustain at my required FPS floor?"

## Configure a density test in the UI

1. Open **Density** tab.
2. Set **FPS Floor**  (for example, `30`).
3. Add one or more pipelines.
4. For each pipeline, set **Stream Rate** so all pipelines sum to `100%`.
5. Set ** iteration duration**  in seconds (for example, `30`). 
6. Click **Run density test**.

When the job completes, ViPPET reports:

- Per-stream FPS
- Total streams
- Stream distribution per pipeline

## Stream rate rules

`stream_rate` defines how total streams are distributed among selected pipelines.

Example:

- Pipeline A: `60`
- Pipeline B: `40`
- Total: `100` ✅

Validation requirements:

- `pipeline_density_specs` cannot be empty.
- Pipeline rates must sum to exactly `100`.
- Duplicate pipeline references are not allowed.

## API format (optional)

If you run tests via API, use `POST /tests/density`.

### Request schema

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `fps_floor` | number | Yes | Minimum acceptable FPS per stream |
| `pipeline_density_specs` | array | Yes | Pipelines and stream rates |
| `execution_config` | object | Yes | Output mode and runtime |

### Pipeline source options

Each entry in `pipeline_density_specs` can use one of the following pipeline sources:

1. `variant`
2. `graph`
3. `description`

### Example request (variant source)

```json
{
  "fps_floor": 30,
  "pipeline_density_specs": [
    {
      "pipeline": {
        "source": "variant",
        "pipeline_id": "pipeline-a3f5d9e1",
        "variant_id": "variant-abc123"
      },
      "stream_rate": 50
    },
    {
      "pipeline": {
        "source": "variant",
        "pipeline_id": "pipeline-b7c2e114",
        "variant_id": "variant-def456"
      },
      "stream_rate": 50
    }
  ],
  "execution_config": {
    "output_mode": "disabled",
    "max_runtime": 0
  }
}
```

### Success response

```json
{
  "job_id": "job456"
}
```

## Important constraints

- Density tests do not support `live_stream` output mode.
- Use only `disabled` or `file` for `output_mode`.
- For stable comparison between platforms, keep the same FPS floor, input data, and pipeline configuration.

## Typical errors

Common request validation errors:

- `Pipeline` field cannot be empty`
- `Participation Rate` -  must sum to 100% for all pipelines
- Duplicate pipeline identifier in one request

## Result interpretation

Use density results together with performance metrics:

- Higher **total streams** at the same FPS floor indicates better density.
- **Per-stream FPS** should stay at or above the configured floor.
- Compare results across devices using the same test profile.
