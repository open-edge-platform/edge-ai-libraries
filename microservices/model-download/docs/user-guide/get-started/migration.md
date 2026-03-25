# Migrate from Model Registry to Model Download

Model Download replaces Model Registry, which will be deprecated soon. Intel suggests the following migration approach, depending on your needs:

| Category         | Model Registry  | Model Download                          | Migration Approach                |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Core Role        | Model           | Runtime model acquisition and           | Core usage shifts from model      |
|                  | management      | preparation.                            | management to runtime fetching    |
|                  | system          |                                         | and model preparation before      |
|                  |                 |                                         | application startup.              |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Primary          | Storage,        | Fetches, converts to the OpenVINO™      | Replace registry-based storage    |
| Purpose          | version         | Intermediate Representation (IR)        | with direct model pulling from    |
|                  | control, and    | format, optimizes through precision     | external sources. No additional   |
|                  | model           | reduction and hardware-specific         | action is required for            |
|                  | management      | tuning, and stores the models.          | conversion or optimization.       |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Onboarding       | - Downloads     | No onboarding required.\                | Remove manual onboarding flow.    |
| Process          | model\          | Directly pulls models from external     | Configure model source details    |
|                  | - Compressed    | sources using API.                      | during setup and use the pull     |
|                  | package\        |                                         | API.                              |
|                  | - Uploads to    |                                         |                                   |
|                  | registry        |                                         |                                   |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Model Sources    | Only models     | All supported models from multiple      | Update model references to        |
|                  | that were       | model hubs:\                            | point to the source instead of    |
|                  | uploaded to     | - Hugging Face\                         | the registry by enabling the      |
|                  | the registry    | - Ollama\                               | required source plugins during    |
|                  |                 | - Geti™ software\                       | setup and passing the             |
|                  |                 | - Ultralytics                           | appropriate model hub to the      |
|                  |                 |                                         | download API.                     |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Storage Type     | Centralized:\   | Local filesystem storage or             | Update applications to read       |
|                  | - Metadata      | PersistentVolumeClaim (PVC)             | models from the local             |
|                  | database\       |                                         | filesystem path managed by        |
|                  | - Object        |                                         | Model\                            |
|                  | storage         |                                         | Download.\                        |
|                  |                 |                                         | \                                 |
|                  |                 |                                         | In Docker deployments, this       |
|                  |                 |                                         | path is typically mounted as a    |
|                  |                 |                                         | volume to persist downloaded      |
|                  |                 |                                         | models across container           |
|                  |                 |                                         | restarts                          |
|                  |                 |                                         |                                   |
|                  |                 |                                         | In Helm/Kubernetes deployments,   |
|                  |                 |                                         | this is configured using          |
|                  |                 |                                         | Persistent Volumes (PVCs) to      |
|                  |                 |                                         | retain models across pod          |
|                  |                 |                                         | restartsand avoid redundant       |
|                  |                 |                                         | downloads. Shared PVCs are used   |
|                  |                 |                                         | between Model Download and        |
|                  |                 |                                         | dependent applications to         |
|                  |                 |                                         | enable direct access to           |
|                  |                 |                                         | downloaded models                 |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Metadata         | Stored in       | Encoded in model path                   | No metadata management overhead   |
| Storage          | separate        | (name/device/precision)                 | because most of the required      |
|                  | databases       |                                         | metadata details are encoded in   |
|                  |                 |                                         | the model path. If still          |
|                  |                 |                                         | needed, manage externally. (can   |
|                  |                 |                                         | use MLOps tools, config files,    |
|                  |                 |                                         | and etc)                          |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Persistence      | Strong          | Persistent shared storage (host         | No change is needed.\             |
|                  | centralized     | volume / PVC)                           | \                                 |
|                  | persistence     |                                         | Models remain in local storage    |
|                  |                 |                                         | on the host machine in Docker     |
|                  |                 |                                         | deployments. In Kubernetes,       |
|                  |                 |                                         | they are stored in a PVC until    |
|                  |                 |                                         | manually deleted.\                |
|                  |                 |                                         | \                                 |
|                  |                 |                                         | Lightweight and sufficient for    |
|                  |                 |                                         | runtime use.                      |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Infrastructure   | High:\          | Low:\                                   | Replace all registry components   |
| Overhead         | - Registry      | - Single service\                       | with a single Model Download      |
|                  | service\        | - Local storage                         | service.\                         |
|                  | - Database\     |                                         | \                                 |
|                  | - Storage       |                                         | Simplify architecture and         |
|                  |                 |                                         | reduce maintenance.               |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Metadata         | Supported       | Not supported                           | Avoid continuous metadata         |
| Updates          | (score,         |                                         | maintenance. Use external         |
|                  | format, and     |                                         | systems/tools if needed.          |
|                  | etc.)           |                                         |                                   |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Versioning       | Mandatory and   | Not enforced                            | Reduce complexity for dynamic     |
|                  | enforced        |                                         | workloads because models are      |
|                  |                 |                                         | pulled directly from hubs;        |
|                  |                 |                                         | specific versions can be          |
|                  |                 |                                         | fetched using version tags or     |
|                  |                 |                                         | identifiers. Use external tools   |
|                  |                 |                                         | if version management is          |
|                  |                 |                                         | required.                         |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Conversion       | Not supported   | Converts models to the                  | Enable                            |
| Support          |                 | OpenVINO™ format                        | OpenVINO™                         |
|                  |                 | automatically.                          | plugin during the setup and       |
|                  |                 |                                         | configure the required fields     |
|                  |                 |                                         | based on the parameters           |
|                  |                 |                                         | provided via the download API.    |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Precision        | Not             | Supports all OpenVINO™                  | Specify required precision in     |
| Support          | applicable      | toolkit-supported formats:\             | the download API configuration    |
|                  |                 | - INT4\                                 | if needed.                        |
|                  |                 | - INT8\                                 |                                   |
|                  |                 | - FP16\                                 |                                   |
|                  |                 | - FP32                                  |                                   |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Device           | Not supported   | Supports all OpenVINO™                  | Configure the target device in    |
| Targeting        |                 | toolkit-supported devices:\             | the download API configuration    |
|                  |                 | - CPU\                                  | if needed.                        |
|                  |                 | - GPU\                                  |                                   |
|                  |                 | - NPU                                   |                                   |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Parallel         | Not supported   | Supports parallel downloads of          | Set the parallel download flag    |
| Downloads        |                 | multiple models. Leads to a faster      | to true in the Model Download     |
|                  |                 | startup when multiple models are        | API configuration.                |
|                  |                 | required.                               |                                   |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Caching          | No runtime      | Configurable local caching:\            | Specify the path for model        |
|                  | caching         | - Reuses existing models\               | download during setup. No         |
|                  | mechanism       | - Skips re-download if already          | additional configuration is       |
|                  |                 | exists.                                 | needed.                           |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| API Style        | CRUD-heavy:\    | Minimal pull-based API with Optimum     | Replace registry APIs with the    |
|                  | - Upload        | CLI compliance                          | pull API to download models       |
|                  | models\         |                                         | directly from thesource at        |
|                  | - List          |                                         | runtime.\                         |
|                  | models\         |                                         | \                                 |
|                  | - Delete        |                                         | Supports Optimum CLI              |
|                  | models\         |                                         | compliance, where parameters      |
|                  | - Update        |                                         | compatible with the OpenVINO      |
|                  | metadata        |                                         | backend (via optimum-cli ...      |
|                  |                 |                                         | openvino ...) can be used for     |
|                  |                 |                                         | model export, compilation, and    |
|                  |                 |                                         | quantization.                     |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Model Listing    | From the        | From the local filesystem               | Replace registry dependencies     |
|                  | registry        |                                         | with the relevant GET API from    |
|                  | database        |                                         | Model Download.                   |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Geti             | Import ,        | Direct pull from                        | Configure                         |
| Integration      | store, and      | Geti™ software                          | Geti™                             |
|                  | download        |                                         | software details during setup     |
|                  |                 |                                         | and use the pull API. The rest    |
|                  |                 |                                         | is handled by the                 |
|                  |                 |                                         | Geti™                             |
|                  |                 |                                         | plugin.                           |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Upload Models    | Supported       | Not supported                           | Not required. Remove registry     |
|                  |                 |                                         | upload workflows. Ensure models   |
|                  |                 |                                         | are accessible via the source.    |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Delete Models    | Supported       | Not supported                           | Delete downloaded models          |
|                  |                 |                                         | manually or implement simple      |
|                  |                 |                                         | cleanup scripts if required.      |
|                  |                 |                                         | Deletion of model at the hub      |
|                  |                 |                                         | source is not supported.          |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Runtime          | Not required    | Mandatory (must run before              | Ensure Model Download is          |
| Dependency       |                 | application startup)                    | deployed and ready before         |
|                  |                 |                                         | dependent services start.         |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Startup          | None            | Must be available before dependent      | Use API to check download job     |
| Dependency       |                 | application services start              | status and ensure completion      |
|                  |                 |                                         | before app startup.               |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Model Location   | Stored in       | Stored in the local download path.      | Update model paths in             |
|                  | registry        | Fast local access.                      | application configuration.        |
|                  | storage         |                                         |                                   |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Operational      | High:\          | Low:\                                   | No additional action is           |
| Overhead         | - Manage        | - Single service\                       | required.                         |
|                  | registry        | - Local storage only                    |                                   |
|                  | service\        |                                         |                                   |
|                  | - Metadata      | Fewer components to manage. Reduced     |                                   |
|                  | database\       | operational effort.                     |                                   |
|                  | - Storage\      |                                         |                                   |
|                  | - Model         |                                         |                                   |
|                  | lifecycle\      |                                         |                                   |
|                  | - More          |                                         |                                   |
|                  | towards         |                                         |                                   |
|                  | deployment,     |                                         |                                   |
|                  | monitoring,     |                                         |                                   |
|                  | debugging,      |                                         |                                   |
|                  | and scaling     |                                         |                                   |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |
| Scalability      | Limited:\       | Flexible:\                              | No additional changes are         |
|                  | - Central       | - Independent downloads\                | required. Model Download uses a   |
|                  | bottleneck\     | - Local caching\                        | decentralized approach in which   |
|                  | - Storage       | - No central bottleneck                 | each service manages models       |
|                  | pressure with   |                                         | independently, enabling it to     |
|                  | an increased    |                                         | scale naturally.                  |
|                  | number of       |                                         |                                   |
|                  | models          |                                         |                                   |
| ---------------- | --------------- | --------------------------------------- | --------------------------------- |

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
