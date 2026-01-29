# Release Notes

## Current Release

**Version**: rc1.4.0 \
**Release Date**: 16 Jan 2026  

**Features**:

- In VSS search mode, users can now filter results by time range via:
  - Query parsing to infer time ranges (e.g., "person seen in last 5 minutes").
  - Direct time range input from the UI.
- Added live system performance metrics in the search UI (enable with `export ENABLE_VSS_COLLECTOR=true`).
- Fixed the build script of the `vdms-dataprep` microservice.
- Added telemetry collection of the application metrics for VDMS-dataprep microservice and VLM microservice.

**HW used for validation**:

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU
- Vanilla Kubernetes Cluster

**Known Issues/Limitations**:

- Helm implementation for telemetry feature not implemented yet.
- EMF and EMT are not supported yet.
- Video Summarization with `mini_cpm` model not working on Xeon® 4 and Xeon® 6 machines.
- Occasionally, the VLM/OVMS models may generate repetitive responses in a loop. We are actively working to resolve this issue in an upcoming update.
- HW sizing of the Video Search or Video Summarization pipeline is in progress. Optimization of the pipelines will follow HW sizing.
- Known issues are internally tracked. Reference not provided here.
- `how-to-performance` document is not updated yet. HW sizing details will be added to this section shortly.

## Previous releases

**Version**: 1.3.1 \
**Release Date**: 20 Nov 2025

**Features**:

- [VLM] Added cleanup helpers so every request releases OpenVINO infer requests; streaming responses call this once the event stream finishes to release resource and merge back the threads.
- Sanity on user_override_variables.yaml file in VSS helm chart.
- Updated the VLM, MME, VDMS-Dataprep docs to enable user to download public docker image and
- added notes on embedding model selection for Helm charts.
- Exposed the env variable `MAX_CONTEXT_LENGTH` to enable user to override this value for setting LLM model context length.
- Trivy scan fixes for  audio-analyzer-microservice,  multimodal-embedding-microservice, pipeline-manager, vdms-dataprep, video-ingestion, video-search, vlm-openvino-serving.
- Sanity on some deprecated field in helm which previously treat as Warning but now it have been treated as ERROR in latest helm version.
- Removed failed search queries from search left column.
- Fixed search UI checkbox selection/deselection issue.
- Fixed VSS video upload streamable mp4 error message.
- Documentations updates and some other required setup-script/code fixes to be able to build standalone Audio-Analyzer image and run/use it without any external dependency (like minio etc).
- Updated image tags for various components and helm chart to version 1.3.1.

**HW used for validation**:

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU
- Vanilla Kubernetes Cluster


**Version**: rc1.3.2 \
**Release Date**: 14 Nov 2025

**Features**:

- **Update VSS Helm chart configurations and dependencies for updated microservice dataprep, MME, search-ms**
  - Added environment variables for embedding model configuration in multiple YAML files.
  - Updated image tags for various components to version 1.3.0.
  - Enhanced deployment configurations for multimodal embedding and VDMS DataPrep.
  - Improved documentation for embedding model settings and deployment instructions.

- Video_Summary: Link to Multimodal embedding models are missing in the getting started guide
- Video_Search: Change in models with different embedding dimension results in no video search
- Video_Summary: When Video search is deployed with embedding model as Blip2/blip2_feature_extractor, Multimodal embedding serving doesnt run

**HW used for validation**:

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU
- Vanilla Kubernetes Cluster

**Version**: 1.3.0 \
**Release Date**: 14 Nov 2025

**Features**:

- **Enhanced Multimodal Embedding (MME) Microservice**:
  - Implemented CLIP, CN-CLIP, MobileCLIP, SigLIP2, and BLIP2 model handlers to support by OpenVINO support.
  - Added model registry and factory pattern for creating model handlers based on configuration.
  - Introduced text-only Qwen3-embedding model family support.
  - Enabled dual runtime support: models can run using native PyTorch or OpenVINO runtime.
  - Microservice supports both API and SDK modes of operation for flexible integration.
  - Implemented utility functions for embedding text and images with support for base64 and URL inputs.
  - Created application-level EmbeddingModel class for high-level functionality, including video processing.

- **VDMS DataPrep Microservice Improvements**:
  - Changed video processing mechanism to extract and store frames individually in vector store for more granular content capture.
  - Enabled object detection on frames to capture additional contextual information.
  - Implemented batched mode processing for video frame aggregation.
  - Integrated SDK mode consumption of MME microservice for reduced API overhead.
  - Enabled batching and parallel processing of frame batches to significantly reduce video consumption time.
  - Enhanced SDKVDMSClient to support dynamic detection of text and image embedding capabilities.
  - Updated simplified_embedding_helper to remove Qwen model dependencies and utilize SDK for text embeddings.
  - Modified user guide to reflect changes in embedding model settings and usage instructions.
  - Adjusted setup.sh to set OpenVINO performance mode to "THROUGHPUT" for better efficiency.
  - Added build script for VDMS DataPrep to build the .whl file at runtime for docker image build. and update documentation for usage.
  - Added detailed data flow documentation and other documentation updates.

- **Search-MS and VSS Application Enhancements (Search Mode)**:
  - Enabled frame-to-video aggregation for consolidated video search results.
  - Introduced configurable aggregation settings in common.py for fine-tuning search behavior.
  - Enhanced segment scoring algorithm with qualitative metrics based on peak and sustained quality.
  - Implemented scoring that considers frame quality and contextual proximity for improved relevance.
  - Exposed all result fine-tuning parameters via environment variables for user customization.
  - Added troubleshooting section for search results with embedding model changes

**HW used for validation**:

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU

**Version**: 1.2.3 \
**Release Date**: 31 Oct 2025

**Features**:

- Enhanced helm configuration and deployment capabilities for GPU workloads, enabling better performance and flexibility.
- Refreshed UI for a more intuitive and user-friendly experience, improving overall usability and navigation.
- Updated to the latest supported OpenVINO Model Server (OVMS) version for improved stability and feature access.
- Addressed issues flagged by Trivy and Dependabot scans to ensure stronger security and compliance.

**HW used for validation**:

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU
- Vanilla Kubernetes Cluster

**Version**: 1.2.2 \
**Release Date**: 06 Oct 2025

**Features**:.

- Enhanced Helm Chart with RWOnce support and additional stability improvements.
- Introduced initial VSS CLI for streamlined command-line operations.
- Enabled persistent embeddings in VDMS to maintain state across container restarts.
- Implemented search result grouping by tags for improved organization and filtering.
- Updated unit tests to cover new features and recent code changes.
- Addressed vulnerabilities flagged by Trivy and dependabot scans.

**Version**: 1.2.1 \
**Release Date**: 29 Sept 2025

**Features**:

- Unified search and summarization functionality for streamlined user experience.
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
- Video Summarization with `mini_cpm` model not working on Xeon® 4 and Xeon® 6 machines.
- Occasionally, the VLM/OVMS models may generate repetitive responses in a loop. We are actively working to resolve this issue in an upcoming update.
- HW sizing of the Video Search or Video Summarization pipeline is in progress. Optimization of the pipelines will follow HW sizing.
- VLM models on GPUs currently support only `microsoft/Phi-3.5-vision-instruct`.
- The Helm chart presently supports only CPU deployments.
- Known issues are internally tracked. Reference not provided here.
- `how-to-performance` document is not updated yet. HW sizing details will be added to this section shortly.
- In standalone search only mode, the tags feature on query is not working.
- Sometimes during search, the response is not instantaneous. However, users can use the refresh button to fetch the results.
- Directory Watcher service only supported in Search only mode.

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
  - Error message is displayed on the UI when invalid video is uploaded in both Video Search and Video Summarization modes.
  - Only mp4 format is supported currently. For other formats, error message is displayed on the UI.
  - Fix to ensure that the sample application can be shutdown in a terminal different from the one in which it was started.
  - A few minor documentation issues have been fixed.
  - Provided a means to manage the PVC in values.yaml file.
  - Fixed an issue where video summarization progress is kept in the pipeline manager service even if the specific video summary is deleted
  - Issues around tag handling for videos has been fixed.
  - Trouble shooting section updated with observed useful information.
  - Enabled a minimum configuration of Video Summarization to work on older Xeon configurations. Note that there is no official support for versions of Xeon earlier than Xeon 4.

**Version**: RC4 \
**Release Date**: 18 June 2025
**Features**:

- Added Helm chart for Video Search and Summarization.
- Streamlined microservices names and folder structure.
- Updated documentation.
- Reuse of VLM services with updates for Metro AI suite.
- Addressed various issues and bugs from the previous builds.
- Unified Video Search and Summarization Use Case: Integration of search and summarization capabilities into a single deployment experience. Users can select the use case deployment at runtime.
- Elimination of Datastore Microservice Dependency: Simplified architecture by removing reliance on the datastore microservice.
- Nginx Support: Added compatibility for both Helm and Docker Compose-based deployments.
- Streamlined Build, Deployment and Documentation: Introduction of a setup script to simplify service build and deployment processes.

**HW used for validation**:

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU
- Vanilla Kubernetes Cluster
