# Release Notes: Model Download

## Version 2026.2.0

**TBD**

This release introduces **configurable external model sources**, **request-scoped credential overrides and startup model preloading**, **OpenVINO HETERO device conversion**, and **job cancellation**, along with validation, AI skill, and documentation improvements.

**New**

- **External Model Sources**: introduces a YAML-driven plugin for Pipeline Zoo models, time-series UDF tarballs, OpenVINO Model Zoo models, and allowlisted remote URLs.
- **Credential Overrides and Startup Preloading**: adds validated per-request credential overrides and YAML-based startup model downloads, including parallel multi-model processing and OpenVINO conversion settings.
- **HETERO Device Conversion**: adds OpenVINO conversion for ordered HETERO device combinations such as `HETERO:GPU,CPU`.
- **Job Cancellation**: adds an endpoint to cancel queued or running jobs, stop active work where supported, and clean up only the affected model artifacts.

**Improved**

- **Model Download AI Skills**: expands developer and user skill guidance, examples, evaluations, integration patterns, and current API workflows.
- **Model Storage Documentation**: documents deterministic, hub-specific model storage paths returned by completed jobs.

**Fixed**

- **Uploaded Model Name Validation**: preserves letter case, converts spaces to underscores, and rejects unsafe or malformed names with clearer errors.
- **Updated the default container UID/GID to 1000**: to align with host user permissions and simplify volume access
- **Fixed security vulnerability issues**

**Known Issues:**

- **Intermittent curl SSL certificate errors**: Some plugins may intermittently fail with curl: (60) SSL certificate problem: unable to get local issuer certificate during HTTPS requests. The root cause is currently under investigation.

---

## Version 2026.1.0

**Release Date:** June 17, 2026

**New:**

- Added HETERO device support for OpenVINO conversion: `config.device` now accepts `HETERO:<dev>[,<dev>...]` (e.g. `HETERO:GPU,CPU`) in addition to `CPU`, `GPU`, and `NPU`. Converted models are stored under a filesystem-safe device directory (e.g. `openvino_models/hetero_gpu_cpu/`). The NPU int4 override applies only to the exact `NPU` device, not to HETERO combinations.
- Added a new Pipeline Zoo Models plugin for downloading models from the `dlstreamer/pipeline-zoo-models` repository.
- Added external source hubs for OpenVINO™ Model Zoo (`omz`) and allowlisted runtime archive downloads (`remote-url`).
- Isolated Python virtual environments per plugin to prevent dependency conflicts.
- Out-of-the-box support for the latest OpenVINO™ release (any version above 2025.4.1).
- Enabled TTS, STT, and image generation model types in the OpenVINO™ plugin.
- Introduced `--ovms-release-tag` option in `run_service.sh` to configure the OVMS release version (default: `v2025.4.1`).
- Resolved `Qwen/Qwen3-VL-8B` conversion failure when using a newer OpenVINO™ release tag.
- Upgraded the Ultralytics public model download script to DL Streamer v2026.0.0.
- Added Ultralytics INT8 quantization support through `config.quantize` and added relevant unit test cases.
- Added rejection of multi-model requests (`all`, `yolo_all`, and comma-separated model names) when `quantize` is set.
- Added cleanup when INT8 artifacts are not generated after user sends the INT8 request.
- Added ephemeral container support for one-shot downloads without impacting the existing download flow.
- Introduced a new script to enable the ephemeral download flow.
- Made HF token optional for model downloads.
- Added a quickstart guide for ephemeral mode.
- Added `POST /api/v1/models/list` to list models available from supported hubs before download. Listing is currently supported for `huggingface`, `ultralytics`, `pipeline-zoo-models`, and `geti`.

**Improved:**

- API hub names are now accepted case-insensitively (e.g. `Geti`, `GETI`, and `HuggingFace` all map to their canonical lowercase identifier).
- `GET /api/v1/plugins` now reports model-listing capabilities and accepted listing filter fields.
- `microsoft/Phi3.5-mini-instruct` model conversion requires the default OpenVINO™ version (`v2025.4.1`); newer versions with `transformers>4.55` are not yet compatible.

**Known Issues:**

- Intel® does not support Edge Manageability Framework deployment currently.
- Due to a limitation in the DL Streamer public model download script, all supported precision artifacts (for example, FP32 and FP16) are downloaded by default even when not requested. When INT8 is specifically requested by user, the other supported precision artifacts are still downloaded along with INT8.

## Version 1.1.0

**Release Date:** February 20, 2026

**New:**

- Implemented component-based model conversion for models not supported by Optimum library.
- Added a new Geti™ plugin for downloading models from Geti software.
- Enabled the OpenVINO™ plugin with VLM support.

**Improved:**

- Updated the OpenVINO™ plugin to support NPU for LLM models.

**Known Issues:**

- Intel® does not support Edge Manageability Framework deployment currently.

## Previous Releases

- [Release notes 2025](./release-notes/release-notes-2025.md)

<!--hide_directive
```{toctree}
:hidden:

Release Notes 2025 <./release-notes/release-notes-2025.md>

```
hide_directive-->
