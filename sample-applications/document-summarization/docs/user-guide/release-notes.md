# Release Notes

## Current Release

**Version**: 1.0.4
**Release Date**: 17 Feb 2026

- Updated default CHUNK_SIZE to 4096 to support larger files and updated supporting documents


## Known Issues/Behaviour (Consolidated):

- Application running into Model Type issue on EMT 3.1 - Closed
- EMF Deployment package is not supported. - Open
- Summary time depends on the size and complexity (image, tables, cross references) of the document - Open

## Previous Releases

**Version**: 1.0.3
**Release Date**: 07 Nov 2025

- Update nginxinc/nginx-unprivileged to 1.29.2 version
- Update few package version to fix vulnerabilities
- Update openvino/model_server to 2025.3 version

**Version**: 1.0.2
**Release Date**: 09 Sep 2025

- Fix issue where summary generation timed-out for huge text files. Now text file chunking is done and then summary is generated.
- Update openvino/model_server to 2025.2 version
- Update nginxinc/nginx-unprivileged to 1.29.1 version

**Version**: 1.0.1
**Release Date**: 19 Aug 2025

- Fix issue where document summary fails due to missing `nltk` package

**Version**: 1.0.0
**Release Date**: 25 July 2025

**Key Features and Improvements:**

- **Document Summary Use Case:** The sample application provides capability to generate document summary using LlamaIndex Document Summary Index. It supports different file formats such as txt, pdf, docs.
- **Nginx Support:** The app uses Nginx to expose the services and internal communication b/w the services happen over docker network.
- **Helm:**  Helm chart integration is done to simplify the deployment and management of applications on Kubernetes clusters
- **Telemetry:** OpenTelemetry instrumentation provides the application insights and API traces
- **Streamlined Build, Deployment and Documentation:** Added setup script to simplify service build and deployment processes and several other [user guide](../user-guide)  All supporting documents have been added.
- **Deployment:** Helm and docker compose deployment has been validated on EMT 3.0.
