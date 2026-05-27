<!--SPDX-License-Identifier: Apache-2.0-->

# Optimize Pipelines

ViPPET integrates the **DL Streamer Pipeline Optimizer** (DLS Optimizer)
to help you find a well-performing configuration of a GStreamer
pipeline on the hardware available to the application. Instead of
manually editing element properties such as inference device,
`batch-size`, `nireq` or the pre-processing backend, you describe the
pipeline once as a variant and let the optimizer search for a
configuration that maximizes throughput.

This page describes how the optimizer behaves inside ViPPET today: how
to prepare a variant so that it can be optimized at all, what happens
between the moment you press **Optimize pipeline** and the moment a
result is returned, and how the variant name controls which device(s)
the optimizer is allowed to use.

For background information about the optimizer itself, see the upstream
documentation:
[DL Streamer Optimizer](https://github.com/open-edge-platform/dlstreamer/blob/main/docs/user-guide/dev_guide/optimizer.md).

## Prerequisite: an editable variant in advanced mode

The **Optimize pipeline** action is only available when **both**
conditions below are satisfied:

1. The pipeline editor is in **advanced mode**.
2. The currently selected variant is **not read-only**.

If either condition is not met, the menu entry is disabled and a lock
icon explains why.

### Advanced mode

The editor has two view modes, controlled by the **Enable advanced
mode** switch in the editor toolbar:

- **Simple mode** shows only the user-relevant elements of the
  pipeline (sources, sinks, `gvadetect`, `gvaclassify`, `gvatrack`,
  etc.). This view is intentionally restricted and several actions —
  including **Optimize pipeline**, **Import pipeline** and **Export
  pipeline** — are unavailable.
- **Advanced mode** shows every GStreamer element in the pipeline,
  including queues, converters, `gvafpscounter`, `gvametaconvert`,
  `gvametapublish`, `fakesink`, etc. The optimizer needs the full
  pipeline graph to work, so optimization is only exposed in this
  view.

When you toggle the switch, ViPPET saves the current graph (unless you
discard unsaved changes), refetches the variant, and re-renders the
editor in the requested mode.

### Read-only versus editable variants

Every pipeline has one or more **variants**. Variants come from two
sources:

- **Predefined variants** ship with ViPPET as part of the built-in
  pipeline templates. They are loaded at startup with `read_only=true`
  and represent a known-good configuration. They cannot be renamed,
  edited, deleted or optimized in place — the backend rejects update
  and delete requests with a clear error, and the UI disables the
  corresponding actions.
- **User-created variants** are variants you add yourself, either by
  saving an existing variant under a new name (**Save as new
  variant**) or by importing a pipeline. They are always created with
  `read_only=false` and are fully editable.

The optimizer overwrites the variant's `pipeline_graph` with the
optimized graph when you accept the result, so it can only run on a
variant that is allowed to be modified. To optimize a predefined
configuration you therefore have three options:

- **Save as new variant.** Open a predefined variant, choose
  **Save as new variant** from the actions menu, give it a new name,
  and optimize the new variant.
- **Create a new variant.** Add a fresh variant to the pipeline and
  build the graph in advanced mode.
- **Create a new pipeline.** Create a brand-new user-defined pipeline.
  All variants of a user-created pipeline are created with
  `read_only=false`.

In all three cases the resulting variant is editable, advanced mode
can be enabled on it, and **Optimize pipeline** becomes available.

## What happens when you press "Optimize pipeline"

The optimization flow is a two-step asynchronous operation. ViPPET
always validates the pipeline first and only invokes the optimizer if
validation succeeds.

### Step 1 — Pipeline validation

Before any optimizer code is called, the UI converts the current graph
into a `PipelineValidation` request and calls
`POST /api/v1/pipelines/validate`. The backend:

1. Converts the pipeline graph into a GStreamer launch string (the
   same string that would be used to run the pipeline).
2. Starts a short-lived validation job that runs `gst_runner.py` in
   the background against this launch string.
3. Reports whether the pipeline can be constructed and started
   successfully on the host.

If validation fails (for example because an element property is
invalid, a model file is missing or two elements cannot be linked),
the UI shows an error toast with the details from `validationStatus`
and the optimizer is **not** invoked. You must fix the pipeline and
try again.

If validation succeeds, the variant's `pipeline_graph` is saved
(`updateVariant`) and the optimization request is dispatched.

### Step 2 — Optimization

ViPPET submits an `optimize` request to
`POST /api/v1/pipelines/{pipelineId}/variants/{variantId}/optimize`.
The backend then:

1. Reads the variant's `pipeline_graph` and serializes it to a
   GStreamer pipeline string.
2. Creates an `InternalOptimizationJobStatus` in state `RUNNING`,
   assigns a job id, and spawns a background thread.
3. Resolves the **allowed devices** from the variant name
   (see [Variant names and devices](#variant-names-and-devices)).
4. Calls into the optimizer that ships with the DL Streamer image
   mounted under `/opt/intel/dlstreamer/scripts/optimizer`.

The job runs entirely inside the `vippet` container; you do not need
to install DLS Optimizer separately.

## How DLS Optimizer searches for a configuration

For `optimize` jobs ViPPET calls `DLSOptimizer.optimize_for_fps()` on
the pipeline string. The optimizer performs the following work, as
described in the upstream DLS Optimizer documentation:

1. **Pre-processing rewrite.** The pipeline is first normalized so
   that color conversions, resizing and other pre-inference operations
   are placed on the most efficient elements for the configured
   hardware (for example, moving CSC/resize into `vapostproc` on GPU,
   or into the inference element's `pre-process-backend` on CPU).
2. **Baseline measurement.** The normalized pipeline is run for a
   short sample window to establish a baseline FPS and the expected
   number of inference detections per sample. The detection count is
   used later as a sanity check to reject configurations that
   silently dropped inference work.
3. **Configuration search.** The optimizer iteratively varies
   inference-related properties on `gvadetect` / `gvaclassify` —
   primarily the **inference device** (within the allowed device
   list), `batch-size`, `nireq`, and the `pre-process-backend` — and
   re-runs the pipeline for another sample window to measure FPS.
4. **Best-configuration selection.** Candidates whose detection count
   drops below the baseline (within the optimizer's tolerance) are
   discarded; the surviving candidate with the highest measured FPS
   wins.

Both the **time budget for the search** and the **duration of each
sample window** are configured by ViPPET to fixed values; they are
not exposed as user-tunable parameters in this stack. The optimizer
stops as soon as its internal time budget is exceeded and returns the
best configuration it has confirmed so far.

When the job completes, ViPPET converts the optimizer's returned
pipeline string back into a graph and stores both views on the job:

- `optimized_pipeline_description` — the GStreamer pipeline string
  returned by the optimizer,
- `optimized_pipeline_graph` — the **advanced view** (full graph with
  every GStreamer element),
- `optimized_pipeline_graph_simple` — the **simple view** (only the
  user-relevant elements),
- `total_fps` — the measured total FPS of the winning configuration.

The UI offers an **Apply** action on the success toast; choosing it
replaces the editor's current nodes and edges with the optimized graph
so that you can inspect it, save it, run a performance test on it, or
export it.

## Variant names and devices

When you start an `optimize` job, ViPPET inspects the **name** of the
selected variant and decides whether to restrict the optimizer to a
single OpenVINO device. The matching is **case-insensitive**.

| Variant name (case-insensitive) | Optimizer search scope                           |
|---------------------------------|--------------------------------------------------|
| `CPU`                           | Restricted to `["CPU"]`                          |
| `GPU`                           | Restricted to `["GPU"]`                          |
| `NPU`                           | Restricted to `["NPU"]`                          |
| Any other name                  | Default scope (all devices detected by OpenVINO) |

Internally, ViPPET calls `DLSOptimizer.set_allowed_devices()` exactly
once with the resolved list before `optimize_for_fps()` is invoked.
For non-matching variant names the call is skipped and the optimizer
keeps its default behavior, meaning every `gvadetect` / `gvaclassify`
element in the pipeline may be moved to any device that OpenVINO
detected at startup (CPU, integrated and discrete GPUs, NPU).

Practical consequences:

- To benchmark a specific device, name the variant exactly `CPU`,
  `GPU`, or `NPU` (case does not matter). The optimizer will not move
  inference to any other device.
- To let DLS Optimizer pick the best assignment across all available
  devices, use any other name (for example, `default` or `mixed`).
- The variant name only affects the **search scope**. It does not
  change how the input pipeline is read; if the input graph already
  pins `gvadetect` to `device=GPU` and the variant is named `CPU`,
  the optimizer is allowed to move it to CPU.

## Job lifecycle and result payload

Every optimization job is tracked by a job id and has the following
state machine:

| State       | Meaning                                                                                                                    |
|-------------|----------------------------------------------------------------------------------------------------------------------------|
| `RUNNING`   | The job is queued or executing. Created immediately when you submit an optimization request.                               |
| `COMPLETED` | The optimizer finished successfully. An optimized pipeline string and both graph views are stored on the job.              |
| `FAILED`    | The job ended without producing a usable result. The `details` field contains a human-readable error or cancellation note. |

A cancelled job is always reported as `FAILED` because partial
optimization results are not reliable.

You can poll the status through:

- `GET /api/v1/jobs/optimization/{job_id}/status` — full status,
- `GET /api/v1/jobs/optimization/{job_id}` — short summary.

For a successful job, ViPPET stores and returns:

- `original_pipeline_graph` and `original_pipeline_graph_simple` —
  the variant graph you submitted, in both advanced and simple views.
- `original_pipeline_description` — the GStreamer pipeline string
  that was actually sent to the optimizer.
- `optimized_pipeline_description` — the GStreamer pipeline string
  returned by the optimizer.
- `optimized_pipeline_graph` and `optimized_pipeline_graph_simple` —
  the optimized graph, in both advanced and simple views.
- `total_fps` — measured total FPS of the optimized pipeline.
- `start_time` / `end_time` — UNIX timestamps in milliseconds.
- `details` — list of status messages (success message on completion
  or error/cancellation notes on failure).

The two graph views let the UI display both a clean overview of the
optimized pipeline and the full element-level detail used by advanced
users.
