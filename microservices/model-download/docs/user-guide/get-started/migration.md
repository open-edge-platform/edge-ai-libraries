# Migrate from Model Registry to Model Download

Model Download replaces Model Registry, which will be deprecated soon. Intel suggests the following migration approach, depending on your needs:

```{list-table}
:header-rows: 1

* - Category
  - Model Registry
  - Model Download
  - Migration Approach
* - Core Role
  - Model management system
  - Runtime model acquisition and preparation
  - Core usage shifts from model management to runtime fetching and model preparation before application startup.
* - Primary Purpose
  - Storage, version control, and model management
  - Fetches models, converts to OpenVINO™ Intermediate Representation (IR) format, optimizes via precision reduction and hardware tuning, and stores the models.
  - Replace registry storage with direct model pulls from external sources; no extra conversion or optimization steps needed.
* - Onboarding Process
  - Downloads models, compresses the packages, and uploads to the registry
  - No onboarding required; directly pulls models from external sources via API
  - Remove the manual onboarding flow; configure model source during setup and use pull API.
* - Model Sources
  - Only models that were uploaded to the registry
  - All supported models from multiple module hubs: Hugging Face / Ollama / Geti™ software / Ultralytics
  - Update model references to point to the source instead of the registry by enabling the required source plugins during setup and passing the appropriate model hub to the download API.
* - Storage Type
  - Centralized metadata database and object storage
  - Local filesystem storage or PersistentVolumeClaim (PVC)
  - Update applications to read models from the local filesystem path managed by Model Download. In Docker deployments, this path is typically mounted as a volume to persist downloaded models across container restarts. In Helm / Kubernetes deployments, this is configured using PersistentVolumeClaims (PVCs) to retain models across pod restarts and avoid redundant downloads. Shared PVCs are used between Model Download and dependent applications to enable direct access to downloaded models.
* - Metadata Storage
  - Stored in separate databases
  - Encoded in model path (name / device / precision)
  - No metadata management overhead as most of the metadata details are encoded in the model path. If needed, manage externally (e.g., use MLOps tools, config files, etc.).
* - Persistence
  - Strong centralized persistence
  - Persistent shared storage (host volume / PVC)
  - No change needed. In Docker deployments, models remain in local storage on the host machine; in Kubernetes, they are stored in a PVC until manual deletion. The app is lightweight and sufficient for runtime use.
* - Infrastructure Overhead
  - High: registry service, database, storage
  - Low: single service, local storage
  - Replace registry components with a single Model Download service, simplifying architecture and reducing maintenance.
* - Metadata Updates
  - Supported (score, format, etc.)
  - Not supported
  - Avoid continuous metadata maintenance. Use external systems or tools if needed.
* - Versioning
  - Mandatory and enforced
  - Not enforced
  - Reduce complexity for dynamic workloads with models pulled directly from hubs. If needed, fetch specific versions via version tags or identifiers. Use external tools if version management is required.
* - Conversion Support
  - Not supported
  - Automatic conversion to OpenVINO™ format
  - Enable OpenVINO™ plugin during setup and configure the required fields based on the parameters provided via the download API.
* - Precision Support
  - Not applicable
  - All OpenVINO™ toolkit-supported formats: INT4 / INT8 / FP16 / FP32
  - Specify precision in the download API configuration, if needed.
* - Device Targeting
  - Not supported
  - All OpenVINO™ toolkit-supported devices: CPU / GPU / NPU
  - Configure the target device in the download API configuration, if needed.
* - Parallel Downloads
  - Not supported
  - Parallel downloads of multiple models, leading to faster startup when multiple models are required
  - Enable parallel download flag in the Model Download API configuration.
* - Caching
  - No runtime caching
  - Configurable local caching: Reuses existing models, or skips re-download if models already exist
  - Specify model download path during setup; no further configuration needed.
* - API Style
  - CRUD-heavy: upload, list and delete models, update metadata
  - Minimal pull-based API with Optimum CLI compliance
  - Replace registry APIs with pull APIs to download models from the source at runtime. Optimum CLI compliance support enables the use of OpenVINO backend-compatible parameters for model export, compilation and quantization.
* - Model Listing
  - From the registry database
  - From the local filesystem
  - Replace registry dependencies with Model Download GET APIs.
* - Geti Integration
  - Import, store, and download
  - Direct pull from Geti™ software
  - Configure Geti™ details during setup and use the pull API; the Geti™ plugin handles integration.
* - Upload Models
  - Supported
  - Not supported
  - Not required; Model Download removes registry upload workflows and ensures model accesibility via the source.
* - Delete Models
  - Supported
  - Not supported
  - Delete downloaded models locally (manually or via cleanup scripts). Deletion of models at hub source is not supported.
* - Runtime Dependency
  - Not required
  - Mandatory before application startup
  - Ensure Model Download is deployed and ready before dependent services start.
* - Startup Dependency
  - None
  - Model Download must be available before dependent services start
  - Use API to check download job status and ensure completion before application startup.
* - Model Location
  - Stored in registry
  - Stored in local download path, ensuring fast local access
  - Update model paths in application configuration.
* - Operational Overhead
  - High: manage registry service, metadata database storage, model lifecycle; deployment, monitoring, debugging, and scaling
  - Low: single service, local storage only; fewer components to manage, reduced operational effort
  - No additional action required.
* - Scalability
  - Limited: central registry bottleneck, storage pressure with an increased number of models
  - Flexible: decentralized, independent downloads, local caching
  - No additional changes required. Model Download uses a decentralized approach in which each service manages models independently, scaling naturally.
```

Conclusion:

Model Registry provides centralized storage, metadata management, and
versioning, while Model Download focuses on runtime model handling
through direct fetching, conversion, optimization, and local caching.

As part of this transition:
Registry-based workflows (upload, metadata management, and versioning)
are not required. Basic metadata information is encoded in the model
download path. If you need to maintain registry-based workflows, you
will need to handle them externally.

Model access will shift from centralized storage to source-based
retrieval and local filesystem storage. Update applications to read
models from the local filesystem path managed by Model Download.
In Docker deployments, this path is mounted as a volume for model
persistence across restarts. In Kubernetes deployments, Persistent
Volumes (PVCs) are used, often shared between Model Download and
dependent applications for direct access and reuse.

Model Download becomes a mandatory runtime dependency to ensure models
are available and ready before application startup.

> **Note:**
> Currently, Model Download provides Helm charts for Kubernetes
> deployments; however, a separate deployment package is not yet available
> for Edge Manageability Framework. As a result, Model Download is
> integrated into the application-level deployment package. Intel will
> create a dedicated deployment package for Model Download.
