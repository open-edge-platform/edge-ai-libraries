# Release Notes

## Current Release

**Version**: 1.2.2 \
**Release Date**: WW32 2025

- Replaced environment variable-based configuration with YAML file loading for model-related settings, improving flexibility and maintainability.
- Enhanced container security by updating UI and NGINX containers to run as non-root users, aligning with industry best practices.
- Renamed stream_log/ endpoint to chat/, reflecting its current functionality more accurately.

## Previous Release

**Version**: 1.2.1 \
**Release Date**: WW27 2025

- Image Optimization for ChatQnA Core Backend. Reducing image sizes, which will lead to faster processing times and reduced bandwidth usage.
- Security Vulnerabilities Fix for Dependency Packages.
- Update in Setup Scripts for default model download path in the backend.
- Bug fixes.

### Known Issues/Behavior:
- Not validated with the EMF deployment package
- Not validated on EMT edge node

**Version**: 1.2.0 \
**Release Date**: WW20 2025

- Support for GPU (discrete and integrated) is now available. Refer to system requirements documentation for details.
- Changed the default LLM to "Phi 3.5 Mini instruct"
- Bug fixes
- Docker images for this release:
  - CPU-only support: intel/chatqna:core_1.2.0
  - GPU-enabled support: intel/chatqna:core_gpu_1.2.0

## Earlier releases

**Version**: 1.1.2 \
**Release Date**: WW16 2025

- Persistent volume used instead of hostpath. This is enabled by default requiring clusters to support dynamic storage support.
- Documentation updated for ESC compatability. As ESC supports only absolute file path, the links in the documentation always point to main repo even on forked repos.
- Bug fixes

**Version**: 1.1.1 \
**Release Date**: WW13 2025

- Updated the documentation to reflect availability in public artefactory.
- Bug fixes.

**Version**: 1.0.0 \
**Release Date**: WW11 2025

- Initial release of the Chat Question-and-Answer Core Sample Application. It supports only Docker Compose approach given the target memory optimized Core deployment as a monolith.
- Improved user interface for better user experience.
- Documentation as per new recommended template.

## Known limitations

- The load time for the application is ~10mins during the first run as the models needs to be downloaded and converted to OpenVINO IR format. Subsequent run with the same model configuration will not have this overhead. However, if the model configuration is changed, it will lead to the download and convert requirement resulting in the load time limitation.

