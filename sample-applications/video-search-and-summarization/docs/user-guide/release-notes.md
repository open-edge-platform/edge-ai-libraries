# Release Notes


## Current Release
**Version**: 1.2.0 \
**Release Date**: 04 August 2025  

**Features**:
- This is an incremental release on top of RC4.1 providing fixes for issues found on RC4.1 The notes provided under RC4.1 apply for this incremental release too.
- Issues fixed are listed below:
    - Updated docker and helm to public registry.
    - Updated tags for the helm and docker images. 


## Previous releases

**Version**: RC4.1 \
**Release Date**: 29 July 2025  

**Features**:
- This is an incremental release on top of RC4 providing fixes for issues found on RC4. The notes provided under RC4 apply for this incremental release too.
- Issues fixed are listed below:
    - Error message is displayed on the UI when invalid video is uploaded in both video summary and video search modes.
    - Only mp4 format is supported currently. For other formats, error message is displayed on the UI.
    - Fix to ensure that the sample application can be shutdown in a terminal different from the one in which it was started.
    - A few minor documentation issues have been fixed.
    - Provided a means to manage the PVC in values.yaml file.
    - Fixed an issue where video summary progress is kept in the pipeline manager service even if the specific video summary is deleted
    - Issues around tag handling for videos has been fixed.
    - Trouble shooting section updated with observed useful information.
    - Enabled a minimum configuration of video summary to work on older Xeon configurations. Note that there is no official support for versions of Xeon earlier than Xeon 4.

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
- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU
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
