# Release Notes

## Current Release

**Version**: 2.0.0\
**Release Date**: 06 Nov 2025

- Integrated OPEA UI with OEP backend and added conversation history to improve contextual responses.
- Enhanced file and link uploads with success/failure alerts, duplicate detection alerts, file size exceed alerts, single-upload restriction, and selected file/urls deletion and bulk delete options.
- Added options to rename, delete, and view full conversation titles via tooltip. Added a loading spinner beside conversation titles while a response is in progress for that conversation. Added a blinking cursor to show when the AI is processing or generating a response.
- Enhanced OPEA interface layout to maintain consistency with the existing UI design and user experience.
- Improved RAG chain and Redux handling for conversation management.
- Enhanced documentation to include comprehensive chat history management features and localStorage persistence details in the architecture overview.

## Known Issues/Behavior (Consolidated):
- The upload button is temporarily disabled during chat response generation to prevent delays. File or link uploads trigger embedding generation, which runs on the same OVMS server as the LLM, potentially slowing response streaming if both run together.
- Chat data is stored in localStorage for session continuity. After container restarts, old chats may reappear — clear your browser’s localStorage to start fresh.
- Limited validation done on EMT-S due to EMT-S issues. Not recommended to use ChatQnA modular on EMT-S until full validation is completed.
- TGI on EMT 3.0 on Core&trade; configuration has a long startup time due to resource constraints. Alternative is to use TGI only on Xeon® based systems. (*Low priority as TGI and vLLM is deprecated effective 2025.2.0*)
- DeepSeek/Phi Models are observed, at times, to continue generating response in an endless loop. Close the browser and restart in such cases. 

## Previous Releases

**Version**: 1.2.4 \
**Release Date**: WW45 2025

- Fix OVMS Dependencies Error in Helm Deployment.


**Version**: 1.2.3 \
**Release Date**: WW39 2025

- Updated to OpenVINO™ model server version 2025.3.
- Streamlined Docker-based application deployment steps.
- Refreshed list of embedding models.
- UI and NGINX containers now run with non-root privileges in Helm deployments.
- Various bug fixes.

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
