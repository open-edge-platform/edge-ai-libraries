# Release Notes: Model Download

## Version 1.1.0-r2-rc1

**April 17, 2026**

**New**

- Upgraded the Ultralytics public model download script to DL Streamer v2026.0.0.
- Added Ultralytics INT8 quantization support through `config.quantize` and added relevant unit test cases
- Added rejection of multi-model requests (`all`, `yolo_all`, and comma-separated model names) when `quantize` is set.
- Added cleanup when INT8 artifacts are not generated when user sends INT8 request.

**Known Issues**:
- Intel does not support Edge Manageability Framework deployment currently.
- Due to a limitation in the DL Streamer public model download script, all supported precision artifacts (for example, FP32 and FP16) are downloaded by default even when not requested. When INT8 is specifically requested by user, the other supported precision artifacts are still downloaded along with INT8.


## Version 1.1.0

**February 20, 2026**

**New**

- Implemented component-based model conversion for models not supported by Optimum library.
- Added a new Geti™ plugin for downloading models from Geti software.
- Enabled the OpenVINO plugin with VLM support.

**Improved**

- Updated the OpenVINO™ plugin to support NPU for LLM models.


**Known Issues**:
- Intel does not support Edge Manageability Framework deployment currently.


For older release notes, check out:

- [Release notes 2025](./release-notes/release-notes-2025.md)



<!--hide_directive
```{toctree}
:hidden:

Release Notes 2025 <./release-notes/release-notes-2025.md>

```
hide_directive-->