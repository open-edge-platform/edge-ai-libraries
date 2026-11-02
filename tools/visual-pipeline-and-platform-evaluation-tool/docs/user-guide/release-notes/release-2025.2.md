# ViPPET 2025.2

## Major features and improvements

- [New graphical user interface (GUI)](#new-graphical-user-interface-gui): Interactive visual
  representation of pipeline graphs with graphical parameter inspection and modification.
- [Pipeline import and export](#pipeline-import-and-export): Share and version control pipeline
  configurations across environments.
- [Backend and frontend separation](#backend-and-frontend-separation): Independent development
  with fully functional REST API for automation and direct access.
- [Extensible architecture for dynamic pipelines](#extensible-architecture-for-dynamic-pipelines):
  Support for custom pipeline types without modifying core components.
- [POSE model support](#pose-model-support): POSE estimation models integrated into pipeline configuration.
- [DL Streamer Optimizer integration](#dl-streamer-optimizer-integration): Automatic optimization
  of GStreamer-based pipelines.
- [Model management enhancements](#model-management-enhancements): Add and remove supported models
  directly through the application.

## Release Details

This section covers additional details on the new ViPPET's functionality.

### New graphical user interface (GUI)

- A visual representation of the underlying `gst-launch` pipeline graph is provided, presenting elements, links, and
  branches in an interactive view.
- Pipeline parameters (such as sources, models, and performance-related options) can be inspected and
  modified graphically, with changes propagated to the underlying configuration.

### Pipeline import and export

- Pipelines can be imported from and exported to configuration files, enabling sharing of configurations between
  environments and easier version control.
- Exported definitions capture both topology and key parameters, allowing reproducible pipeline setups.

### Backend and frontend separation

- The application is now structured as a separate backend and frontend, allowing independent development and
  deployment of each part.
- A fully functional REST API is exposed by the backend, which can be accessed directly by automation scripts or
  indirectly through the UI.

### Extensible architecture for dynamic pipelines

- The internal architecture has been evolved to support dynamic registration and loading of pipelines.
- New pipeline types can be added without modifying core components, enabling easier experimentation with
  custom topologies.

### POSE model support

- POSE estimation model is now supported as part of the pipeline configuration.

### DL Streamer Optimizer integration

- Integration with the DL Streamer Optimizer has been added to simplify configuration of GStreamer-based pipelines.
- Optimized elements and parameters can be applied automatically, improving performance and reducing manual tuning.

### Model management enhancements

- Supported models can now be added and removed directly through the application.
- The model manager updates available models in a centralized configuration, ensuring that only selected models are
  downloaded, stored, and exposed in the UI and API.
