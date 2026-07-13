# How to add a new pipeline

ViPPET supports two kinds of pipelines:

- **Built-in (predefined) pipelines**: shipped with the backend image and
  loaded at startup from YAML files in
  [`vippet/pipelines/`](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/tools/visual-pipeline-and-platform-evaluation-tool/vippet/pipelines).
  All their variants are marked `read_only=true`.
- **User-created pipelines**: created at runtime through the REST API
  (`POST /api/v1/pipelines`) or from the **Pipelines** page in the UI.
  They are kept in-memory by the singleton `PipelineManager`, are editable,
  and disappear when the backend restarts.

This page explains how to add both. In day-to-day contribution work,
"adding a new pipeline" almost always means adding a YAML file under
`vippet/pipelines/`, that is the path covered first and in most detail.

You can use the
[example pull request adding the *Defect Detection* pipeline](https://github.com/open-edge-platform/edge-ai-libraries/pull/2279)
as a real-world reference.

## A. Add a built-in pipeline (YAML)

### 1. Create the YAML file

Drop a new file into `vippet/pipelines/`. The filename (without extension)
becomes part of the on-disk identifier; use kebab-case, for example
`vehicle-detection.yaml`. `PipelineLoader.list()` auto-discovers every
`*.yaml` file in this directory at startup, **no registration code is
needed**.

### 2. Required structure

```yaml
name: Vehicle Detection           # required, non-empty
definition: >                     # optional human-readable description
  Short, user-facing description of what the pipeline does and where it fits.
tags:                             # optional list of strings
  - Traffic
  - Detection
thumbnail: images/vehicle-detection.png   # optional; path relative to vippet/pipelines/
variants:                         # required, at least one
  - name: CPU                     # required, non-empty (trimmed)
    pipeline_description: >-
      filesrc location=/videos/input/sample.mp4 !
      decodebin3 !
      gvadetect
        model=/models/output/.../model.xml
        device=CPU
        ... !
      queue !
      gvafpscounter starting-frame=100 !
      gvawatermark !
      gvametaconvert !
      queue !
      gvametapublish file-format=json-lines file-path=/dev/null !
      fakesink name=default_output_sink sync=false async=false
  - name: GPU
    pipeline_description: >-
      ...
  - name: NPU
    pipeline_description: >-
      ...
```

Field reference (enforced by `PipelineManager.load_predefined_pipelines()`):

| Field                             | Required | Notes                                                                            |
|-----------------------------------|----------|----------------------------------------------------------------------------------|
| `name`                            | Yes      | Non-empty after trimming. The pipeline ID is derived from it.                    |
| `definition`                      | No       | Free-text description shown in the UI. May be empty.                             |
| `tags`                            | No       | List of strings. Anything that is not a list is ignored and replaced with `[]`.  |
| `thumbnail`                       | No       | PNG/JPEG path relative to `vippet/pipelines/`. Loaded and inlined as base64.     |
| `variants`                        | Yes      | At least one entry. Read-only at runtime.                                        |
| `variants[].name`                 | Yes      | Non-empty after trimming. Variant ID is derived from it.                         |
| `variants[].pipeline_description` | Yes      | Non-empty after trimming. A standard `gst-launch`-style description.             |

### 3. Pipeline description conventions

The string in `pipeline_description` is parsed by
`Graph.from_pipeline_description()` (see `vippet/graph.py`) and must follow
the same conventions used by the other built-in pipelines:

- Separate elements with ` ! `.
- The pipeline **must end with a `fakesink`** that the runner can promote to
  the main output. The recommended pattern is
  `fakesink name=default_output_sink sync=false async=false`. The
  `default_output_sink` marker explicitly identifies the user-facing sink
  and is required when more than one `fakesink` is present.
- Reference models by **absolute path** inside the container
  (`/models/output/...`). Add the matching `model-proc` JSON when needed.
- Reference videos by **absolute path** inside the container
  (`/videos/input/<file>`). At parse time the backend rewrites these to
  filenames, so the pipeline remains portable across hosts.
- Provide one variant per supported device target. The other built-in
  pipelines use the following naming convention: `CPU`, `GPU`, `NPU`,
  `GPU_NPU`. Use whichever subset makes sense for the pipeline, only the
  variants you actually ship are exposed.
- Insert `queue` elements where you would do so in a normal DL Streamer
  pipeline (after inference, before sinks, around tee branches).
- For metadata-only pipelines (no rendering) `gvametaconvert` then
  `gvametapublish` then `fakesink` is the standard tail.

### 4. Models and videos

- Add any new models to the supported models catalog so they can be
  installed at runtime by the `model-download` service. The catalog
  resolution is driven by `SUPPORTED_MODELS_FILE`
  (default `/models/supported_models.yaml`).
- Sample input videos must be downloadable via the recordings YAML
  (`DEFAULT_RECORDINGS_FILE`, default `/videos/default_recordings.yaml`)
  or uploaded by the user, never commit binary media to the repo.
- If a referenced model is not installed, `PipelineManager` clears the
  `model` field on load and surfaces a clear error when the user tries to
  run the pipeline.

### 5. Add a thumbnail

Place a small PNG (or JPEG) under `vippet/pipelines/images/` and reference
it via `thumbnail:`. It is loaded as base64 and surfaced through the API
so the UI can display it on the Pipelines page.

### 6. Test it

Add or extend a unit test in
`vippet/tests/unit/managers_tests/pipeline_manager_test.py`, at minimum
make sure the new YAML is loaded successfully by
`PipelineManager.load_predefined_pipelines()` (covered by the
`test_load_predefined_pipelines` test, which iterates every YAML in the
directory). Then run:

```bash
make test
make lint
```

Finally, start the stack with `make run-dev` and verify in the UI that:

- the pipeline appears on the Pipelines page with the right name,
  description, tags and thumbnail,
- both the **Simple** and **Advanced** views render correctly,
- each variant can be executed against the matching device.

## B. Add a user-created pipeline at runtime

User-created pipelines are not committed to the repository, they are
created by API consumers. Contributors typically interact with this path
only when adding tests, examples or UI flows.

### REST API

```text
POST /api/v1/pipelines
Content-Type: application/json

{
  "name": "vehicle-detection",
  "description": "Simple vehicle detection pipeline",
  "tags": ["detection", "vehicle"],
  "variants": [
    {
      "name": "CPU",
      "pipeline_graph":        { "nodes": [...], "edges": [...] },
      "pipeline_graph_simple": { "nodes": [...], "edges": [...] }
    }
  ]
}
```

Behavior (see `vippet/api/routes/pipelines.py::create_pipeline`):

- The `source` field is **forced to `USER_CREATED`** by the route; any
  client value is ignored.
- The pipeline ID, variant IDs, and `created_at` / `modified_at`
  timestamps are generated server-side.
- All variants are stored with `read_only=false`.
- User-created pipelines have `thumbnail=null` by default.
- Successful creation returns `201` with the generated `id`.

After creation, additional variants can be added with
`POST /api/v1/pipelines/{pipeline_id}/variants`, properties patched with
`PATCH /api/v1/pipelines/{pipeline_id}`, and the simple / advanced graph
views converted into each other through `POST /api/v1/convert/...`.

Full request/response schemas and examples are available in the
auto-generated OpenAPI docs at `http://localhost:7860/docs`. If you change
any of these endpoints, remember to regenerate both the schema and the UI
client, see
[Backend - API schema and clients](./backend.md#api-schema-and-clients).

## Related pages

- [How to add a new element](./new-element.md)
- [Backend contributing guide](./backend.md)
- [ViPPET Backend architecture](../architecture/vippet-be.md)
