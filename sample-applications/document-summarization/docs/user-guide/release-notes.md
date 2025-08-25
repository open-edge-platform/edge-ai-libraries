# Release Notes


## Current Release

**Version**: 1.0.1
**Release Date**: 19 Aug 2025

- Fix issue where document summary fails due to missing `nltk` package

**Known Issues/Behaviour:**

- EMF Deployment package is not supported yet
- Summary time depends on the size and complexity (image, tables, cross references) of the document
- Helm and docker compose deployment has been validated on EMT 3.0

## Previous Releases

**Version**: 1.0.0
**Release Date**: 25 July 2025

**Key Features and Improvements:**

- **Document Summary Use Case:** The sample application provides capability to generate document summary using LlamaIndex Document Summary Index. It supports different file formats such as txt, pdf, docs.
- **Nginx Support:** The app uses Nginx to expose the services and internal communication b/w the services happen over docker network.
- **Helm:**  Helm chart integration is done to simplify the deployment and management of applications on Kubernetes clusters
- **Telemetry:** OpenTelemetry instrumentation provides the application insights and API traces
- **Streamlined Build, Deployment and Documentation:** Added setup script to simplify service build and deployment processes and several other [user guide](../user-guide)  All supporting documents have been added.
- **Deployment:** Helm and docker compose deployment has been validated on EMT 3.0.
 
## Known Issues/Behaviour (Consolidated):
- Application running into Model Type issue on EMT 3.1 - Open
- EMF Deployment package is not supported. - Open
- Summary time depends on the size and complexity (image, tables, cross references) of the document - Open