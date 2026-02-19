# Release Notes

## Current Release

**Version**: 1.1.0-rc1
**Release Date**: WW08 2026
- Updated OpenVINO plugin to support NPU for LLM models
- Enabled OpenVINO plugin with VLM support.
- Implemented component-based model conversion for models not supported by Optimum
- Added new GETI plugin for downloading models from GETI

## Known Issues/Behavior:
- EMF deployment is not supported right now

**Version**: 1.0.1  
**Release Date**: WW49 2025
- Enhanced response structure consistency across all plugins

## Known Issues/Behavior:
- EMF deployment is not supported right now


**Version**: 1.0.0  
**Release Date**: WW45 2025
- Introduces a Model Download Microservice featuring a plugin-based architecture for extensibility.
- Integrates pre-configured model hubs, enabling support for downloading models from sources such as Hugging Face, Ollama, and Ultralytics.
- Currently supports conversion of Hugging Face models to the OpenVINO IR format.
- Provides two plugin types: Conversion plugins (for model format conversion) and Hub plugins (for integrating new model sources).
- Supports installing plugin dependencies during container startup.
- Highlights that dependencies for selected plugins are automatically installed when the container starts.
- Streamlines the setup process for users and ensures that all necessary components are available for the chosen plugins.

## Known Issues/Behavior:
- EMF deployment is not supported right now
