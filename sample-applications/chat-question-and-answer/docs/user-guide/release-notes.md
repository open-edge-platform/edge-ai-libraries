# Release Notes

## Current Release

**Version**: 1.2.3 \
**Release Date**: WW39 2025

- Updated to OpenVINO™ model server version 2025.3.
- Streamlined Docker-based application deployment steps.
- Refreshed list of embedding models.
- UI and NGINX containers now run with non-root privileges in Helm deployments.
- Various bug fixes.


## Known Issues/Behavior (Consolidated):
- TGI on EMT 3.0 on Core&trade; configuration has a long startup time due to resource constraints. Alternative is to use TGI only on Xeon® based systems.
- Application running into Model Type issue on EMT 3.1 - Open
- DeepSeek/Phi Models are observed, at times, to continue generating response in an endless loop. Close the browser and restart in such cases. - Open

## Previous Releases

**Version**: 1.2.2 \
**Release Date**: WW32 2025

- Enhanced container security by updating UI and NGINX containers to run as non-root users, aligning with industry best practices.
- Improved EMT-S 3.0 stability and performance through targeted bug fixes and optimizations. EMT 3.1 not supported in this version.
- Renamed `stream_log/` endpoint to `chat/`, reflecting its functionality more accurately.
- Functional on EMT 3.0.

**Version**: 1.2.1 \
**Release Date**: WW27 2025

- Image Optimization for ChatQnA Backend and Document Ingestion Microservices. Reducing image sizes, which will lead to faster processing times and reduced bandwidth usage.
- Update to Run ChatQnA-UI and Nginx Container with Non-Root Access Privileges.
- Security Vulnerabilities Fix for Dependency Packages.
- Max Token Parameter Added to /stream_log API.
- EMF deployment is supported.
- Bug fixes.

**Version**: 1.2.0 \
**Release Date**: WW20 2025

- Support for GPU (discrete and integrated) is now available. Refer to system requirements documentation for details.
- Bug fixes

## Earlier releases

**Version**: 1.1.2 \
**Release Date**: WW16 2025

- Edge Orchestrator onboarding supported. Documentation updated to provide necessary onboarding process details.
- Persistent volume used instead of hostpath. This is enabled by default requiring clusters to support dynamic storage support.
- Documentation updated for ESC compatability. As ESC supports only absolute file path, the links in the documentation will always point to main repo even on forked repos.
- Bug fixes

**Version**: 1.1.1 \
**Release Date**: WW13 2025

- Updated the documentation to reflect availability in public artefactory.
- Bug fixes.

**Version**: 1.0.0 \
**Release Date**: WW11 2025

- Initial release of the ChatQ&A Sample Application.
- Added support for vLLM, TGI, and OVMS inference methods.
- Improved user interface for better user experience.
