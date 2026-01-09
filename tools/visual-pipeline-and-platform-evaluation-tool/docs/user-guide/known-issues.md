# Known issues, limitations and troubleshooting

## Known issues

### 1. Pipelines failing or missing bounding boxes when multiple devices/codecs are involved

ViPPET lets you select the `device` for inference elements such as `gvadetect` and `gvaclassify`. However, in
the current implementation there is no integrated mechanism to also update the DL Streamer codec and post‑processing
elements for multi‑GPU or mixed‑device pipelines.

This means that:

- You can change the `device` property on AI elements (for example, to run detection on another GPU),
- But the corresponding DL Streamer elements for **decoding**, **post‑processing**, and **encoding** may remain bound
  to a different GPU or to a default device.

In such cases a pipeline can:

- Fail to start,
- Error out during caps negotiation,
- Or run but produce an output video with no bounding boxes rendered, even though inference is executed.

The relevant DL Streamer elements include:

- **Decoder elements**, such as:
  - `vah264dec` (for GPU.0, or simply `GPU` on single-GPU systems)
  - `varenderD129h264dec` (for GPU.1)
  - `varenderD130h264dec` (for GPU.2)
- **Post‑processing elements**, such as:
  - `vapostproc` (for GPU.0, or simply `GPU` on single-GPU systems)
  - `varenderD129postproc` (for GPU.1)
  - `varenderD130postproc` (for GPU.2)
- **Encoder elements**, such as:
  - `vah264enc`, `vah264lpenc` (for GPU.0, or simply `GPU` on single-GPU systems)
  - `varenderD129h264enc` (for GPU.1)
  - `varenderD130h264enc` (for GPU.2)

> **GPU.0 note:** In systems with only one GPU, it appears as just `GPU` and uses the generic elements above
> (`vah264dec`, `vapostproc`, `vah264enc`, `vah264lpenc`).
> Only on multi-GPU systems will elements for `GPU.1`, `GPU.2` etc. (`varenderD129*`, `varenderD130*`, etc.) appear.

#### Workaround

If you see that the pipeline fails or runs without expected bounding boxes:

1. Export or re‑create the pipeline description.
2. Manually adjust the DL Streamer decoder, post‑processing, and encoder elements so they are explicitly bound to the
   GPU/device consistent with the `device` used by `gvadetect` / `gvaclassify`.
3. Import this modified pipeline into ViPPET as a custom pipeline and run it with the corrected static
   device assignments.

Elements with suffixes like `D129`, `D130`, etc. are typically mapped to specific GPU indices (for example
`GPU.1`, `GPU.2`). The exact mapping between `varenderD129*` / `varenderD130*` elements and `GPU.X` devices depends on
your platform configuration and DL Streamer’s GPU selection rules. For details on how these IDs map to GPU devices and
how to choose the correct elements for each GPU, see the DL Streamer documentation on GPU device selection:
[GPU device selection in DL Streamer](https://docs.openedgeplatform.intel.com/2025.2/edge-ai-libraries/dl-streamer/dev_guide/gpu_device_selection.html).

---

### 2. DLSOptimizer takes a long time or causes the application to restart

When using DLSOptimizer from within ViPPET, optimization runs can be **long‑running**:

- It may take **5–6 minutes** (or more, depending on pipeline complexity and hardware) for DLSOptimizer to explore
  variants and return an optimized pipeline.

In the current implementation, it can also happen that while DLSOptimizer is searching for an optimized pipeline,
the ViPPET application is **restarted**.

For more information about DLSOptimizer behavior and limitations, see the DLSOptimizer limitations section in the
DL Streamer repository:
[DLSOptimizer limitations](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2025.2.0/libraries/dl-streamer/scripts/optimizer/README.md#limitations).

#### Risks related to application restart during optimization

If ViPPET is restarted while DLSOptimizer is running:

- Any **in‑progress optimization job** is interrupted and its results are lost.
- In the current release, an application restart **removes all user‑created pipelines and all types of jobs**
  (tests, optimization runs, validation runs). Only predefined pipelines remain available after restart.
- You may need to **recreate or reimport** your custom pipelines and re‑run your jobs after the application comes back.

### Recommendations

- If this behavior is problematic in your environment (for example, it disrupts interactive work or automated
  workflows), avoid using pipeline optimization and instead:
  - Use baseline, hand‑tuned pipelines.
  - Adjust parameters manually rather than relying on DLSOptimizer.

---

### 3. NPU metrics are not visible in the UI

ViPPET currently does **not** support displaying NPU‑related metrics:

- NPU utilization, throughput, and latency are not exposed in the ViPPET UI.
- Metrics and visualizations are limited to what is currently integrated for other devices.

As a result, even if pipelines use an NPU, you will not see NPU‑specific telemetry in ViPPET.

---

### 4. Occasional “Connection lost” message in the UI

The ViPPET UI is a web application that communicates with backend services. Under transient network
interruptions or short service unavailability, the UI may show a **“Connection lost”** message.

#### Characteristics

- It typically appears **sporadically**.
- It is often related to short‑lived connectivity issues between the browser and the backend.

#### Workaround

- If the **“Connection lost”** message appears occasionally:
  - **Refresh the browser page** to re‑establish the connection to the backend.

---

### 5. Choosing the encoding device for “Save output” and mapping devices to GPU indices

When you enable the **“Save output”** option in ViPPET:

- ViPPET records the output video to a file.
- You are asked to select a **device** that will be used for encoding.

The current implementation does not automatically infer the best encoding device from the existing pipeline. To avoid
confusion and potential issues, use the following guidelines.

#### How to choose the encoding device

- Prefer the **same device that is already used by the downstream video elements** in your pipeline.
- In most cases, the most reliable choice is:
  - The **device used by the element that is closest to the final `*sink`** in the pipeline (for example, the last `va*`
    encoder or post‑processing element before a sink).
- Using a different device for encoding than the one used by the rest of the downstream path can:
  - Introduce unnecessary copies between devices,
  - Or, in some environments, cause pipeline negotiation or stability issues.

#### Mapping devices (`GPU.X`) to DL Streamer elements

DL Streamer maps logical GPU devices (`GPU.0`, `GPU.1`, `GPU.2`, …) to specific element variants as follows:

- **`GPU.0`** (or `GPU` in a single-GPU system) maps to the generic VA‑API elements:
  - Decoders: `vah264dec`
  - Post‑processing: `vapostproc`
  - Encoders: `vah264enc`, `vah264lpenc`
- **`GPU.1`, `GPU.2`, …** map to per‑GPU elements whose names encode the GPU index, for example:
  - For `GPU.1`: elements like `varenderD129h264dec`, `varenderD129postproc`, `varenderD129h264enc`
  - For `GPU.2`: elements like `varenderD130h264dec`, `varenderD130postproc`, `varenderD130h264enc`
  - And so on for additional GPUs.

> **Note:** On systems with only one GPU, the device will be listed as simply `GPU` (not `GPU.0`) and you should always
> use the generic elements above (`vah264dec`, `vapostproc`, `vah264enc`, `vah264lpenc`).

#### Practical guidance

When selecting the encoding device in the **“Save output”** dialog:

- If your pipeline uses **`vah264dec` / `vapostproc` / `vah264enc` / `vah264lpenc`** near the end of the pipeline,
  it is typically running on **`GPU.0`** (or just `GPU` on a single-GPU system).
  → In this case, choose **`GPU.0`** (or `GPU`) for encoding.
- If your pipeline uses elements like **`varenderD129*`**, **`varenderD130*`**, etc. near the end of the pipeline,
  those typically correspond to **`GPU.1`**, **`GPU.2`**, and so on.
  → In this case, choose the `GPU.X` device that matches the `varenderDXXX*` elements used by the final encoder or
  post‑processing stage.

For precise and up‑to‑date mapping between `GPU.X` devices and `varenderDXXX*` elements on your platform,
as well as additional examples, see the DL Streamer GPU device selection guide:
[GPU device selection in DL Streamer](https://docs.openedgeplatform.intel.com/2025.2/edge-ai-libraries/dl-streamer/dev_guide/gpu_device_selection.html).

---

## Limitations

### 1. Application restart removes user-created pipelines and jobs

In the current release, restarting the ViPPET application removes:

- All **pipelines created by the user**, and
- All types of **jobs** (tests, optimization runs, validation runs, and similar).

After a restart, only **predefined pipelines** remain available.
If a restart happens during a long‑running operation (for example, during DLSOptimizer runs), the in‑progress job is
lost, and you need to recreate or reimport your custom pipelines and rerun the jobs.

---

### 2. Support limited to DL Streamer 2025.2.0 pipelines and models

ViPPET currently supports only pipelines and models that are supported by **DL Streamer 2025.2.0**.

For the full list of supported models, elements, and other details, see the DL Streamer release notes:
[DL Streamer release notes](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2025.2.0/libraries/dl-streamer/RELEASE_NOTES.md)

If a custom pipeline works correctly with DL Streamer 2025.2.0, it is expected to also work in ViPPET (see also the
“Limited validation scope” limitation below).

---

### 3. Limited metrics in the ViPPET UI

At this stage, the ViPPET UI shows only a **limited set of metrics**:

- Current **CPU utilization**,
- Current **utilization of a single GPU**, and
- The **most recently measured FPS**.

More metrics (including timeline‑based charts) are planned for future releases.

---

### 4. Limited validation scope

Validation and testing in this release focused mainly on **sanity checks for predefined pipelines**.

For **custom pipelines**:

- Their behavior in ViPPET is less explored and may vary.
- However, if a custom pipeline is supported and works correctly with **DL Streamer 2025.2.0**, it is expected to behave
  similarly when run via ViPPET (see also “Support limited to DL Streamer 2025.2.0 pipelines and models” above).

---

### 5. No live preview video for running pipelines

Live preview of the video from a running pipeline is **not supported** in this release.

As a workaround, you can:

- Enable the **“Save output”** option.
- After the pipeline finishes, inspect the generated **output video file**.

---

### 6. Recommended to run only one operation at a time

Currently, it is recommended to run **a single operation at a time** from the following set:

- Tests,
- Optimization,
- Validation.

In this release:

- New jobs are **not rejected or queued** when another job is already running.
- Starting more than one job at the same time launches **multiple GStreamer instances**.
- This can significantly **distort performance results** (for example, CPU/GPU utilization and FPS).

For accurate and repeatable measurements, run these operations **one by one**.

---

### 7. Some GStreamer / DL Streamer elements may not be displayed correctly in the UI

Some GStreamer or DL Streamer elements used in a pipeline may **not be displayed correctly** by the ViPPET UI.

Even if some elements are not shown as expected in the UI, the underlying **pipeline is still expected to run**.

---

### 8. Supported models list is limited and extending it is not guaranteed to work

ViPPET currently supports only models defined in:

- [supported_models.yaml](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2025.2.0/tools/visual-pipeline-and-platform-evaluation-tool/shared/models/supported_models.yaml)

A user can try to extend this file with new models whose `source` is either `public` or `pipeline-zoo-models`, but
there is **no guarantee** that such models will work out of the box.

- Models with `source: public` must be supported by the following script:
  [download_public_models.sh](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2025.2.0/libraries/dl-streamer/samples/download_public_models.sh)
- Models with `source: pipeline-zoo-models` must already exist in this repository:
  [pipeline-zoo-models](https://github.com/dlstreamer/pipeline-zoo-models)

After adding new models to `supported_models.yaml`, you must:

```bash
make stop
make install-models-force
make run
```

Only then will ViPPET rescan and manage the updated model set.

---

### 9. Pipelines cannot depend on files other than models or videos

Currently, ViPPET does **not** support pipelines that require additional files beyond:

- **Model files**, and
- **Video files**.

Pipelines that depend on other external artifacts (for example, configuration files, custom resources, etc.)
are not supported in this release.

---

## Troubleshooting

### 1. Application containers fail to start

In some environments, ViPPET services may fail to start correctly and the UI may not be reachable.

#### Troubleshooting steps

- Check container logs:

  ```bash
  docker compose logs
  ```

- Restart the stack using the provided Makefile:

  ```bash
  make stop run
  ```

This stops currently running containers and starts them again with the default configuration.

---

### 2. Port conflicts for `vippet-ui`

If the `vippet-ui` service cannot be accessed in the browser, it may be caused by a port conflict on the host.

#### Troubleshooting steps

- In the Compose file (`compose.yml`), find the `vippet-ui` service and its `ports` section:

  ```yaml
  services:
    vippet-ui:
      ports:
        - "80:80"
  ```

- Change the **host port** (left side) to an available one, for example:

  ```yaml
  services:
    vippet-ui:
      ports:
        - "8081:80"
  ```

- Restart the stack and access ViPPET using the new port, e.g. `http://localhost:8081`.
