<!--
# How to Use This Template

1. **Purpose**:
   - Summarize new features, improvements, bug fixes, and known issues for each release.
   - Help developers quickly understand updates and adapt workflows accordingly.

2. **Content Customization**:
   - Replace placeholders (e.g., `[Version X.X.X]`, `[YYYY-MM-DD]`, `<description>`) with specific release details.
   - Refer to the user stories in comments to understand what information developers expect to find.

3. **Style Guidelines**:
   - Use bullet points and concise descriptions for clarity.
   - Organize changes by category: New Features, Improvements, Bug Fixes, and Known Issues.
   - Use active voice and developer-focused language.
   - Follow the **Microsoft Developer Writing Style Guide**.

4. **GitHub Copilot Tool Can Help**:
   - **For Style Adherence**:
     - This template specifys the style guide to be followed, ask GitHub Copilot tool to check.
     - GitHub Copilot tool can generate suggestions in line with the specified writing style.
   - **To Validate Content Completeness**:
     - The template includes in comments the user stories and acceptance criteria to be fulfilled by its content in
       each section. GitHub Copilot tool can check if you have included all required information.
5. **Validation**:
   - Verify all details, links, and formatting before publishing.
   - Ensure that descriptions are accurate and actionable.

-->

# Release Notes

Details about the changes, improvements, and known issues in this release of the application.

## Current Release: [Version 2025.2]

**Release Date**: [2025-12-10]

### New Features (v2025.2)

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

### Improvements (v2025.2)

- **Model management enhancements**:
  - Supported models can now be added and removed directly through the application.
  - The model manager updates available models in a centralized configuration, ensuring that only selected models are
    downloaded, stored, and exposed in the UI and API.

---

## Current Release: [Version 1.2]

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

## Version 1.0.0

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
