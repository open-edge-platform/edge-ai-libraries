# Release Notes


## Current Release
**Version**: RC4 \
**Release Date**: 18 June 2025  

**Features**:
- Added helm chart for summary and search.
- Streamlined microservices names and folder structure.
- Updated documentation.
- Reuse of VLM services with updates for Metro AI suite.
- Addressed various issues and bugs from the previous builds.
- Unified Search and Summary Use Case: Integration of search and summarization capabilities into a single deployment experience. Users can select the use case deployment at runtime.
- Elimination of Datastore Microservice Dependency: Simplified architecture by removing reliance on the datastore microservice.
- Nginx Support: Added compatibility for both Helm and Docker Compose-based deployments.
- Streamlined Build, Deployment and Documentation: Introduction of a setup script to simplify service build and deployment processes.

**HW used for validation**:
- Xeon 5 + BMG580 GPU
- Vanilla Kubernetes Cluster

**Known Issues/Limitations**:
- EMF and EMT are not supported yet.
- Users are required to build the images and use the sample application. Docker images are not available yet on public registries (pending approvals).
- Occasionally, the VLM/OVMS models may generate repetitive responses in a loop. We are actively working to resolve this issue in an upcoming update.
- HW sizing of the Search/Summary pipeline is in progress. Optimization of the pipelines will follow HW sizing.
- VLM models on GPUs currently support only microsoft/Phi-3.5-vision-instruct.
- The Helm chart presently supports only CPU deployments.
- Known issues are internally tracked. Reference not provided here.
- `how-to-performance` document is not updated yet. HW sizing details will be added to this section shortly.

## Previous releases

**Version**:  \
**Release Date**:  

- <Previous release notes>
