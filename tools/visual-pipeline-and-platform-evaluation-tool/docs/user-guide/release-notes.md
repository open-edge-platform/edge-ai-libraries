# Release Notes

Details about the changes, improvements, and known issues in this release of the application.

## Current Release: [2026.0.0]

**Release Date**: [2026-03-25]

### New Features (2026.0.0)

- **Demo mode**:
  - A dedicated demo page is available at the `/demo` endpoint, providing a streamlined presentation view
    of the application with pre-configured scenarios and adjusted visual styling.

- **Pipeline variants**:
  - Each pipeline can now contain multiple variants (for example CPU, GPU, and NPU), each with its own
    graph definition. Users can switch between variants to quickly match the pipeline to the available
    hardware without creating separate pipelines.
  - Variants are fully integrated across the pipeline editor, performance tests, density tests, and demo mode.

- **Pipeline templates and creation from templates**:
  - Predefined pipeline templates (such as Detect and Detect + Classify) are now available as read-only
    starting points for creating new pipelines.
  - Users can create a new pipeline from a template and customize it by selecting a model, input source,
    and adding tags.

- **Simple view for pipeline graphs**:
  - A simplified pipeline view is now available alongside the advanced graph editor. It hides technical
    GStreamer elements and shows only the key processing steps, making pipelines easier to understand
    and configure for less advanced users.
  - Changes made in the simple view are automatically synchronized with the advanced graph, and vice versa.

- **Redesigned pipeline editor layout**:
  - A refined pipeline nodes view with flow visualization and automatic adjustment to the results charts window.

- **New navigation and updated look and feel**:
  - A new navigation view between pages and an updated overall look and feel across the application.

- **New predefined pipelines**:
  - **Retail analytics**: Face detection, age/gender recognition, YOLO 11n object detection, and
    EfficientNet B0 classification pipelines, each available in CPU and GPU variants.
  - **Pallet defect detection**: AI-powered quality control pipelines for detecting defects on pallets,
    available in CPU, GPU, and NPU variants.
  - **Smart parking**: Parking-space occupancy detection pipelines with color classification support,
    available in CPU, GPU, and NPU variants.
  - All predefined pipelines include matching sample videos and model configurations.

- **Camera discovery and management**:
  - A new camera discovery service automatically detects both USB cameras (via `v4l2-ctl`) and network
    cameras (via the ONVIF protocol with WS-Discovery).
  - Discovered cameras are listed in a dedicated Cameras view, where network cameras can be authenticated
    to retrieve their RTSP stream profiles.
  - In the pipeline editor, users can choose between a video file and a camera as the input source directly
    from a dropdown. Only authenticated network cameras appear in the list.

- **Live pipeline output preview**:
  - A WebRTC-based video player is integrated into the UI, enabling real-time preview of pipeline output
    during execution. Live preview works with both video file and camera inputs.

- **Timed pipeline execution**:
  - Pipelines can now be configured to run for a specified duration. When the video file is shorter than
    the requested time, it loops automatically. When the duration is reached, the pipeline stops gracefully.

- **Redesigned metrics charts**:
  - The performance view now displays up to eight live charts — including GPU frequency, GPU power consumption,
    GPU memory usage, GPU utilization, CPU temperature, CPU frequency, CPU utilization, and CPU power —
    depending on the available hardware. When multiple GPUs are present, users can select a specific device.
  - After a pipeline run completes, the collected metrics and charts remain visible, allowing users to
    review the full run results without data loss. Persistent charts are fully integrated across the
    pipeline editor, performance tests, density tests, and demo mode.

- **Custom gvapython scripts**:
  - Users can now add custom Python scripts to pipelines using the `gvapython` element. A new guide
    explains how to configure and integrate these scripts.

---

## 2025.2.0

**Release Date**: [2025-12-10]

### New Features (2025.2.0)

- **New graphical user interface (GUI)**:
  - A visual representation of the underlying `gst-launch` pipeline graph is provided, presenting elements, links, and
    branches in an interactive view.
  - Pipeline parameters (such as sources, models, and performance-related options) can be inspected and
    modified graphically, with changes propagated to the underlying configuration.

- **Pipeline import and export**:
  - Pipelines can be imported from and exported to configuration files, enabling sharing of configurations between
    environments and easier version control.
  - Exported definitions capture both topology and key parameters, allowing reproducible pipeline setups.

- **Backend and frontend separation**:
  - The application is now structured as a separate backend and frontend, allowing independent development and
    deployment of each part.
  - A fully functional REST API is exposed by the backend, which can be accessed directly by automation scripts or
    indirectly through the UI.

- **Extensible architecture for dynamic pipelines**:
  - The internal architecture has been evolved to support dynamic registration and loading of pipelines.
  - New pipeline types can be added without modifying core components, enabling easier experimentation with
    custom topologies.

- **POSE model support**:
  - POSE estimation model is now supported as part of the pipeline configuration.

- **DL Streamer Optimizer integration**:
  - Integration with the DL Streamer Optimizer has been added to simplify configuration of GStreamer-based pipelines.
  - Optimized elements and parameters can be applied automatically, improving performance and reducing manual tuning.

### Improvements (2025.2.0)

- **Model management enhancements**:
  - Supported models can now be added and removed directly through the application.
  - The model manager updates available models in a centralized configuration, ensuring that only selected models are
    downloaded, stored, and exposed in the UI and API.

---

## v1.2

**Release Date**: [2025-08-20]

### New Features (v1.2)

- **Feature 1**: Simple Video Structurization Pipeline: The Simple Video Structurization (D-T-C) pipeline is a versatile,
  use case-agnostic solution that supports license plate recognition, vehicle detection with attribute classification,
  and other object detection and classification tasks, adaptable based on the selected model.
- **Feature 2**: Live pipeline output preview: The pipeline now supports live output, allowing users to view real-time results
  directly in the UI. This feature enhances the user experience by providing immediate feedback on video processing tasks.
- **Feature 3**: New pre-trained models: The release includes new pre-trained models for object detection
  (`YOLO v8 License Plate Detector`) and classification (`PaddleOCR`, `Vehicle Attributes Recognition Barrier 0039`),
  expanding the range of supported use cases and improving accuracy for specific tasks.

### Known Issues (v1.2)

- **Issue**: Metrics are displayed only for the last GPU when the system has multiple discrete GPUs.

---

## v1.0.0

**Release Date**: [2025-03-31]

### New Features (v1.0.0)
<!--
**Guidelines for New Features**:
1. **What to Include**:
   - Summarize new capabilities introduced in this release.
   - Highlight how these features help developers or solve common challenges.
   - Link to relevant guides or instructions for using the feature.
2. **Example**:
   - **Feature**: Added multi-camera configuration support.
     - **Benefit**: Enables developers to monitor larger areas in real-time.
     - [Learn More](./how-to-customize.md)
-->

- **Feature 1**: Pre-trained Models Optimized for Specific Use Cases: Visual Pipeline and Platform Evaluation Tool
  includes pre-trained models that are optimized for specific use cases, such as object detection for Smart NVR
  pipeline. These models can be easily integrated into the pipeline, allowing users to quickly evaluate their
  performance on different Intel® platforms.
- **Feature 2**: Metrics Collection with Turbostat tool and Qmassa tool: Visual Pipeline and Platform Evaluation Tool
  collects real-time CPU and GPU performance metrics using Turbostat tool and Qmassa tool. The collector agent runs
  in a dedicated collector container, gathering CPU and GPU metrics. Users can access and analyze these metrics via
  intuitive UI, enabling efficient system monitoring and optimization.
- **Feature 3**: Smart NVR Pipeline Integration: The Smart NVR Proxy Pipeline is seamlessly integrated into the tool,
  providing a structured video recorder architecture. It enables video analytics by supporting AI inference on
  selected input channels while maintaining efficient media processing. The pipeline includes multi-view composition,
  media encoding, and metadata extraction for insights.

### Known Issues (v1.0.0)

- **Issue**: The Visual Pipeline and Platform Evaluation Tool container fails to start the analysis when the "Run"
  button is clicked in the UI, specifically for systems without GPU.
  - **Workaround**: Consider upgrading the hardware to meet the required specifications for optimal performance.
