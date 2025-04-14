# Release Notes


## Current Release

**Version**: 1.1.2 \
**Release Date**: WW16 2025 

- Persistent volume used instead of hostpath. This is enabled by default requiring clusters to support dynamic storage support.
- Documentation updated for ESC compatability. As ESC supports only absolute file path, the links in the documentation will always point to main repo even on forked repos.
- Bug fixes

## Previous releases

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

