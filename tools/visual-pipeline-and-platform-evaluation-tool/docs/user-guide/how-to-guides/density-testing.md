# How to Test Density

This article explains how to run density tests in ViPPET and interpret the results.
A density test finds the maximum number of streams that can run while keeping the target
minimum FPS per stream. Compared to a standard performance test (fixed stream count),
density testing increases the load and searches for the highest stable stream count that
still meets your FPS requirement. Therefore, it answers the question:"How many concurrent streams can this platform sustain at my required FPS floor?"

## Configure a density test in the UI

1. Open **Density** tab.
2. Set **FPS Floor**  (for example, `30`).
3. Add one or more pipelines.
4. For each pipeline, set **Stream Rate** so all pipelines sum to `100%`.
5. Set **iteration duration** in seconds (for example, `30`).
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


## Important constraints

- Duplicate pipeline references are not allowed. Each pipeline must be unique in the request.
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
