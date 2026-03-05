# Release Notes

## Current Release

## Version 1.1.0-rc2

**Release Date**: WW10 2026
- Added pass-through of parameters for the OpenVINO plugin.
- Enabled use of all parameters aligned with Optimum CLI.
- Updated request payload structure for OpenVINO conversion models.
- Added support for both latest and previous (n-1) OVMS versions, configurable through a single environment variable when run as an individual plugin.
- Implemented `hls` plugin for Health AI Suite with pre-configured models: `human-pose-estimation-3d-0001`, `mtts_can.hdf5`, `ecg_8960_ir10_fp16`, `ecg_17920_ir10_fp16`.
- Added HLS plugin support for pre-configured model types: `3d-pose`, `rppg`, and `ai-ecg`.

**Known Issues or Behavior**:
- Latest OVMS version (`2026.0`) may run into dependency conflicts.

## Version 1.1.0-rc1

**Release Date**: WW08 2026
- Updated the OpenVINO™ plugin to support NPU for LLM models.
- Enabled the OpenVINO plugin with VLM support.
- Implemented component-based model conversion for models not supported by Optimum library.
- Added a new Geti™ plugin for downloading models from Geti software.

**Known Issues or Behavior**:
- Intel does not support Edge Manageability Framework deployment currently.

## Version 1.0.1  

**Release Date**: WW49 2025
- Enhanced response structure consistency across all plugins.

**Known Issues or Behavior**:
- Intel does not support Edge Manageability Framework deployment currently.


## Version: 1.0.0

**Release Date**: WW45 2025
- Introduces a Model Download Microservice featuring a plugin-based architecture for extensibility.
- Integrates pre-configured model hubs, enabling support for downloading models from sources such as Hugging Face, Ollama, and Ultralytics.
- Currently supports conversion of Hugging Face models to the OpenVINO IR format.
- Provides two plugin types: Conversion plugins (for model format conversion) and Hub plugins (for integrating new model sources).
- Supports installing plugin dependencies during container startup.
- Highlights that dependencies for selected plugins are automatically installed when the container starts.
- Streamlines the setup process for users and ensures that all necessary components are available for the chosen plugins.

**Known Issues or Behavior**:
- Intel does not support Edge Manageability Framework deployment currently.
