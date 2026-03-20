# Troubleshooting

## 1. DLSOptimizer takes a long time or causes the application to restart

When using DLSOptimizer from within ViPPET, optimization runs can be **long‑running**:

- It may take **5–6 minutes** (or more, depending on pipeline complexity and hardware) for DLSOptimizer to explore
  variants and return an optimized pipeline.

In the current implementation, it can also happen that while DLSOptimizer is searching for an optimized pipeline,
the ViPPET application is **restarted**.

For more information about DLSOptimizer behavior and limitations, see the DLSOptimizer limitations section in the
DL Streamer repository:
[DLSOptimizer limitations](https://github.com/open-edge-platform/dlstreamer/blob/main/docs/user-guide/dev_guide/optimizer.md#limitations).

**If ViPPET is restarted while DLSOptimizer is running:**

- Any **in‑progress optimization job** is interrupted and its results are lost.
- In the current release, an application restart **removes all user‑created pipelines and all types of jobs**
  (tests, optimization runs, validation runs). Only predefined pipelines remain available after restart.
- You may need to **recreate or reimport** your custom pipelines and re‑run your jobs after the application comes back.

### Workaround for the DLSOptimizer issue

If this behavior is problematic in your environment (for example, it disrupts interactive work or automated
  workflows), avoid using pipeline optimization and instead:

- Use baseline, hand‑tuned pipelines.
- Adjust parameters manually rather than relying on DLSOptimizer.

---

## 2. NPU metrics are not visible in the UI

ViPPET currently does **not** support displaying NPU‑related metrics:

- NPU utilization, throughput, and latency are not exposed in the ViPPET UI.
- Metrics and visualizations are limited to what is currently integrated for other devices.

As a result, even if pipelines use an NPU, you will not see NPU‑specific telemetry in ViPPET.

---

## 3. Occasional “Connection lost” message in the UI

The ViPPET UI is a web application that communicates with backend services. Under transient network
interruptions or short service unavailability, the UI may show a **“Connection lost”** message.

- It typically appears **sporadically**.
- It is often related to short‑lived connectivity issues between the browser and the backend.

If the **“Connection lost”** message appears occasionally: **Refresh the browser page** to
re‑establish the connection to the backend.

---

## 4. Application restart removes user-created pipelines and jobs

In the current release, restarting the ViPPET application removes:

- All **pipelines created by the user**, and
- All types of **jobs** (tests, optimization runs, validation runs, and similar).

After a restart, only **predefined pipelines** remain available.
If a restart happens during a long‑running operation (for example, during DLSOptimizer runs), the in‑progress job is
lost, and you need to recreate or reimport your custom pipelines and rerun the jobs.

---

## 5. Support limited to DL Streamer 2026.0.0 pipelines and models

ViPPET currently supports only pipelines and models that are supported by **DL Streamer 2026.0.0**.

For the full list of supported models, elements, and other details, see the DL Streamer release notes:
[DL Streamer release notes](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.0.0/libraries/dl-streamer/RELEASE_NOTES.md)

If a custom pipeline works correctly with DL Streamer 2026.0.0, it is expected to also work
in ViPPET (see also the “Limited validation scope” limitation below).

---

## 6. Limited validation scope

Validation and testing in this release focused mainly on **sanity checks for predefined pipelines**.

For **custom pipelines**:

- Their behavior in ViPPET is less explored and may vary.
- However, if a custom pipeline is supported and works correctly with **DL Streamer 2026.0.0**,
  it is expected to behave similarly when run via ViPPET (see also “Support limited to
  DL Streamer 2026.0.0 pipelines and models” above).

---

## 7. Recommended to run only one operation at a time

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

## 8. Some GStreamer / DL Streamer elements may not be displayed correctly in the UI

Some GStreamer or DL Streamer elements used in a pipeline may **not be displayed correctly** by the ViPPET UI.

Even if some elements are not shown as expected in the UI, the underlying **pipeline is still expected to run**.

---

## 9. Supported models list is limited and extending it is not guaranteed to work

ViPPET currently supports only models defined in:

- [supported_models.yaml](https://github.com/open-edge-platform/edge-ai-libraries/blob/release-2026.0.0/tools/visual-pipeline-and-platform-evaluation-tool/shared/models/supported_models.yaml)

A user can try to extend this file with new models whose `source` is either `public` or `pipeline-zoo-models`, but
there is **no guarantee** that such models will work out of the box.

- Models with `source: public` must be supported by the following script:
  [download_public_models.sh](https://github.com/open-edge-platform/dlstreamer/blob/main/docs/user-guide/dev_guide/download_public_models.md)
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

## 10. Pipelines cannot depend on files other than models or videos

Currently, ViPPET does **not** support pipelines that require additional files beyond:

- **Model files**,
- **Video files**, and
- **User-defined Python scripts**.

Pipelines that depend on other external artifacts (for example, configuration files, custom resources, etc.)
are not supported in this release.

---

## 11. Application containers fail to start

In some environments, ViPPET services may fail to start correctly and the UI may not be
reachable. In such cases, stop the currently running containers and start them again with the
default configuration:

- Check container logs:

  ```bash
  docker compose logs
  ```

- Restart the stack using the provided Makefile:

  ```bash
  make stop run
  ```

---

## 12. Port conflicts for `vippet-ui`

If the `vippet-ui` service cannot be accessed in the browser, it may be caused by a port
conflict on the host. If that is the case, restart the stack and access ViPPET using the new
port, e.g. `http://localhost:8081`:

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
