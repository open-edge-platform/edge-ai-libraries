# Troubleshooting

## 1. DL Streamer Optimizer takes a long time or causes the application to restart

When using DL Streamer Optimizer from within ViPPET, optimization runs can be **long‑running**:

- It may take **5–6 minutes** (or more, depending on pipeline complexity and hardware) for DL Streamer Optimizer to explore
  variants and return an optimized pipeline.

In the current implementation, it can also happen that while DL Streamer Optimizer is searching for an optimized pipeline,
the ViPPET application is **restarted**.

For more information about DL Streamer Optimizer behavior and limitations, see the DL Streamer
Optimizer limitations section in the DL Streamer documentation:
[DL Streamer Optimizer limitations](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/dev_guide/optimizer.html#limitations).

**If ViPPET is restarted while DL Streamer Optimizer is running:**

- Any **in‑progress optimization job** is interrupted and its results are lost.
- In the current release, an application restart **removes all user‑created pipelines and all types of jobs**
  (tests, optimization runs, validation runs). Only predefined pipelines remain available after restart.
- You may need to **recreate or reimport** your custom pipelines and re‑run your jobs after the application comes back.

### Workaround for the DL Streamer Optimizer issue

If this behavior is problematic in your environment (for example, it disrupts interactive work or automated
  workflows), avoid using pipeline optimization and instead:

- Use baseline, hand‑tuned pipelines.
- Adjust parameters manually rather than relying on DL Streamer Optimizer.

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
If a restart happens during a long‑running operation (for example, during DL Streamer Optimizer
runs), the in‑progress job is lost, and you need to recreate or reimport your custom pipelines
and rerun the jobs.

---

## 5. Support limited to DL Streamer 2026.0.0 pipelines and models

ViPPET currently supports only pipelines and models that are supported by **DL Streamer 2026.0.0**.

For the full list of supported models, elements, and other details, see the DL Streamer release notes:
[DL Streamer release notes](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/release-notes.html)

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

ViPPET currently supports only models defined under:

- [`vippet/models/`](https://github.com/open-edge-platform/edge-ai-libraries/tree/main/tools/visual-pipeline-and-platform-evaluation-tool/vippet/models)
  — one YAML file per model. This catalog is synced into the application
  database at startup (insert-only: existing rows are never updated or
  removed when a file changes).

A user can try to add a new model by creating a new YAML file in
`vippet/models/` (following the shape of an existing entry), but there is
**no guarantee** that such models will work out of the box. New entries
must point to a `source`/`hub` that the `model-download` microservice
knows how to handle (for example `huggingface`, `ultralytics`, `openvino`,
`pipeline-zoo-models`, `geti`, `hls`).

`vippet/models/` is copied into the image at build time, not mounted as a
runtime volume, so after adding or editing a model file you need to
**rebuild the image**, not just restart the stack:

```bash
make build run
```

(If you are running with the dev override, `make run-dev`, the whole
`vippet/` source tree is bind-mounted, so a restart — `make stop`
then `make run-dev` — is enough, no rebuild required.)

After the stack comes back up, install the new models from the **Models**
page in the UI (or via the `/api/v1/models` API).

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
port, e.g., `http://localhost:8081`:

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

---

## 13. Network Camera Discovery does not find cameras

If the Sensor Manager service does not find any cameras on the network, check the following:

- Ensure that the cameras are ONVIF‑compliant and support discovery.
- Verify that the cameras have ONVIF services enabled.
- Confirm that the cameras are on the same network segment as the ViPPET application.
- Check for any firewall rules or network configurations that may block discovery traffic
  (UDP multicast `239.255.255.250:3702`).
- Check that the `sensor-manager` container is running and reachable from the `vippet` container
  (`docker logs sensor-manager`, `curl http://localhost:8090/api/v1/sensors` on the host).

---

## 14. Network Camera Authentication fails

If you are able to discover network cameras but cannot authenticate to them, check the following:

- Verify that the correct username and password are being used for each camera.
- Ensure time synchronization between the ViPPET host and the cameras,
  as some ONVIF implementations require closely synchronized clocks for authentication.
- Check for any specific ONVIF profiles or settings required by the cameras for authentication.

---

## 15. Pipelines fail on NPU with `ZE_RESULT_ERROR_INVALID_NATIVE_BINARY`

Running any pipeline with `device=NPU` fails during element initialization with an error similar to:

```text
Pipeline runtime error: base_inference plugin initialization failed
  ... Failed to construct OpenVINOImageInference
  ... Compilation failed. Level0 pfnCreate2 result: ZE_RESULT_ERROR_INVALID_NATIVE_BINARY
  ... ERROR! MAPPED_INFERENCE_VERSION is NOT compatible with the ELF
      Expected: 6.1.0 vs received: 7.0.4
```

### Cause

The NPU stack is split between the container and the host:

- The **NPU user‑mode driver and compiler** (`intel-level-zero-npu`, `intel-driver-compiler-npu`)
  ship inside the `vippet` image and generate the compiled NPU binary (ELF).
- The **NPU kernel driver (`intel_vpu`) and firmware** live on the **host**. The kernel loads
  firmware from the host filesystem, so the `intel-fw-npu` package inside the image is never used.

If the host firmware is older than the in‑container compiler, the firmware rejects the generated
ELF. `Expected` is the version the host firmware supports; `received` is the version the container
compiler produced. Distribution `linux-firmware` packages often lag the NPU driver releases by a
long time, which makes this the common failure mode on otherwise correctly configured systems.

### Diagnosis

Check the firmware version the host kernel driver actually loaded:

```bash
sudo dmesg | grep -i intel_vpu
# intel_vpu 0000:00:0b.0: [drm] Firmware: intel/vpu/vpu_37xx_v1.bin, version: 20230726*...
```

Compare it with the NPU driver version bundled in the image:

```bash
docker exec -u root vippet dpkg -l | grep -E "intel-(fw-npu|level-zero-npu|driver-compiler-npu)"
```

A host firmware build date much older than the container driver version confirms the mismatch.

### Resolution

Install firmware matching the container's NPU driver into `/lib/firmware/updates/`, which takes
precedence over the distribution‑provided firmware in `/lib/firmware/` and survives
`linux-firmware` upgrades. The matching firmware is already in the image, so it can be copied out
of the running container.

Select the file for your NPU generation: `vpu_37xx_*` for Meteor Lake, `vpu_40xx_*` for Arrow Lake
and Lunar Lake, `vpu_50xx_*` for Panther Lake. Confirm the generation with
`lspci -nn | grep -i "Processing accelerators"`.

```bash
# Example for Meteor Lake (37xx); adjust the file name for other generations.
sudo mkdir -p /lib/firmware/updates/intel/vpu
sudo docker cp vippet:/lib/firmware/updates/intel/vpu/vpu_37xx_v1.bin /tmp/vpu_37xx.bin
sudo install -m 644 /tmp/vpu_37xx.bin /lib/firmware/updates/intel/vpu/vpu_37xx_v1.bin
# Older kernels request the v0.0 name, so install both.
sudo install -m 644 /tmp/vpu_37xx.bin /lib/firmware/updates/intel/vpu/vpu_37xx_v0.0.bin
sudo rm /tmp/vpu_37xx.bin

# Reload the kernel driver so the new firmware is picked up (no reboot required).
# Stop the containers first so they release /dev/accel/accel0.
docker stop vippet metrics-manager
sudo rmmod intel_vpu && sudo modprobe intel_vpu
docker start vippet metrics-manager
```

Confirm that the new firmware is active:

```bash
sudo dmesg | grep -i intel_vpu | tail -3
```

The reported firmware version should now match the container driver's release. Rerun the pipeline
on NPU to verify.

> **Note:** A kernel upgrade does not revert this fix, because `/lib/firmware/updates/` is not owned
> by the `linux-firmware` package. However, after upgrading the `vippet` image to a release with a
> newer NPU driver, repeat the procedure so the host firmware stays aligned.

### Related non‑fatal warning

The following warning is unrelated to this failure and does not stop the pipeline:

```text
Model quantization runtime (2026.2.0-...) does not match current runtime (2026.4.0-...).
Results may be inaccurate. Please re-quantize the model with the current runtime version.
```

It means an INT8 model was quantized with an older OpenVINO™ release than the runtime in the image.
Inference still runs; only accuracy may differ slightly from the originally quantized model.
