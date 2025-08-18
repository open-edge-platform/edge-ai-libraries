# Intel® Visual Pipeline and Platform Evaluation Tool Release 1.2
**Release Date**: [2025-08-20]

## New Features

- **Feature 1**: Simple Video Structurization Pipeline: The Simple Video Structurization (D-T-C) pipeline is a versatile, use case-agnostic solution that supports license plate recognition, vehicle detection with attribute classification, and other object detection and classification tasks, adaptable based on the selected model.
- **Feature 2**: Live pipeline output preview: The pipeline now supports live output, allowing users to view real-time results directly in the UI. This feature enhances the user experience by providing immediate feedback on video processing tasks.
- **Feature 3**: New pre-trained models: The release includes new pre-trained models for object detection (`YOLO v8 License Plate Detector`) and classification (`PaddleOCR`, `Vehicle Attributes Recognition Barrier 0039`), expanding the range of supported use cases and improving accuracy for specific tasks.

## Known Issues

- **Issue**: Metrics are displayed only for the last GPU when the system has multiple discrete GPUs.

# Intel® Visual Pipeline and Platform Evaluation Tool Release 1.0.0
**Release Date**: [2025-03-31]

## New Features
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

- **Feature 1**: Pre-trained Models Optimized for Specific Use Cases: ViPPET includes pre-trained models that are optimized for specific use cases, such as object detection for Smart NVR pipeline. These models can be easily integrated into the pipeline, allowing users to quickly evaluate their performance on different Intel platforms.
- **Feature 2**: Metrics Collection with Turbostat and Qmassa: VIPPET collects real-time CPU and GPU performance metrics using Turbostat and Qmassa. The collector agent runs in a dedicated collector container, gathering CPU and GPU metrics. Users can access and analyze these metrics via intuitive UI, enabling efficient system monitoring and optimization.
- **Feature 3**: Smart NVR Pipeline Integration: The Smart NVR Proxy Pipeline is seamlessly integrated into the tool, providing a structured video recorder architecture. It enables video analytics by supporting AI inference on selected input channels while maintaining efficient media processing. The pipeline includes multi-view composition, media encoding, and metadata extraction for insights.

## Known Issues

- **Issue**: The VIPPET container fails to start the analysis when the "Run" button is clicked in the UI, specifically for systems without GPU.
  - **Workaround**: Consider upgrading the hardware to meet the required specifications for optimal performance.

