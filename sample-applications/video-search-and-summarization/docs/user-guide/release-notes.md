# Release Notes


## Current Release
**Version**: 1.2.2 \
**Release Date**: 06 Oct 2025  

**Features**:.
- Enhanced Helm Chart with RWOnce support and additional stability improvements.
- Introduced initial VSS CLI for streamlined command-line operations.
- Enabled persistent embeddings in VDMS to maintain state across container restarts.
- Implemented search result grouping by tags for improved organization and filtering.
- Updated unit tests to cover new features and recent code changes.
- Addressed vulnerabilities flagged by Trivy and dependabot scans.


**HW used for validation**:

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU
- Vanilla Kubernetes Cluster

**Known Issues/Limitations**:

- EMF and EMT are not supported yet. 
- Video summary with `mini_cpm` model not working on Xeon® 4 and Xeon® 6 machines. 
- Occasionally, the VLM/OVMS models may generate repetitive responses in a loop. We are actively working to resolve this issue in an upcoming update.
- HW sizing of the Search/Summary pipeline is in progress. Optimization of the pipelines will follow HW sizing.
- VLM models on GPUs currently support only `microsoft/Phi-3.5-vision-instruct`.
- The Helm chart presently supports only CPU deployments.
- Known issues are internally tracked. Reference not provided here.
- `how-to-performance` document is not updated yet. HW sizing details will be added to this section shortly.
- Sometimes during search, the response is not instantaneous. However, users can use the refresh button to fetch the results.
- Directory Watcher service only supported in Search only mode.

## Previous releases

**Version**: 1.2.1 \
**Release Date**: 29 Sept 2025  

**Features**:
- Unified Search and Summary functionality for streamlined user experience.
- New UI for new combined use case.
- API updates to support combined use case.
- Enhanced video management with support for tags on upload and search.
- Improved text embedding capabilities within the MME service.
- Introducing Search Alerts and Directory Watcher for proactive monitoring on search use-case.
- TopK search results now available in the UI for faster result filtering
- Helm Chart for the combined application.
- All application containers now run in non-root mode.
- Fix for high RAM consumption when the application is running in combined mode.
- Bug Fixes: Resolved multiple issues from previous builds to ensure stability and performance.


**HW used for validation**:

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU
- Vanilla Kubernetes Cluster

**Known Issues/Limitations**:

- EMF and EMT are not supported yet. 
- `RWOnce` PVC access mode not supported.
- Video summary with `mini_cpm` model not working on Xeon® 4 and Xeon® 6 machines. 
- Occasionally, the VLM/OVMS models may generate repetitive responses in a loop. We are actively working to resolve this issue in an upcoming update.
- HW sizing of the Search/Summary pipeline is in progress. Optimization of the pipelines will follow HW sizing.
- VLM models on GPUs currently support only `microsoft/Phi-3.5-vision-instruct`.
- The Helm chart presently supports only CPU deployments.
- Known issues are internally tracked. Reference not provided here.
- `how-to-performance` document is not updated yet. HW sizing details will be added to this section shortly.
- In standalone search only mode, the tags feature on query is not working.
- Sometimes during search, the response is not instantaneous. However, users can use the refresh button to fetch the results.
- Directory Watcher service only supported in Search only mode.

## Previous releases

**Version**: 1.2.0 \
**Release Date**: 04 August 2025  
**Features**:
- This is an incremental release on top of RC4.1 providing fixes for issues found on RC4.1 The notes provided under RC4.1 apply for this incremental release too.
- Issues fixed are listed below:
    - Updated docker and helm to public registry.
    - Updated tags for the helm and docker images. 
    - Sanity for deployment on EMT.
- Limited support for EMT 3.0 based deployment. CPU-only configuration supported. 
- Images for all required microservices uploaded and available on Docker registry.

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