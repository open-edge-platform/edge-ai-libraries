# Model Update

## Model Registry service integration
EVAM supports MLOps capabilities through integration with the Model Registry service. This enhancement streamlines the model management process, enabling dynamic updates and ensuring that EVAM utilizes the most accurate and up-to-date models. Currently it supports following features:

**Model Initialization**: Upon initialization, EVAM can retrieve and deploy machine learning models directly from a Model Registry. To leverage this feature, users must specify the necessary model details in the configuration file.

**Runtime Model Update**: EVAM offers a REST endpoint that facilitates on-demand model updates during runtime. This endpoint allows users to pull the latest model version from the Model Registry and download it for immediate use within the existing EVAM pipeline. This endpoint also provides options to dynamically restart pipeline with new model.

Refer the detailed [documentation](../../working_with_other_services//MRaaS.md) for steps on launching the model registry microservice and configurations to interact with it during EVAM's startup and runtime.