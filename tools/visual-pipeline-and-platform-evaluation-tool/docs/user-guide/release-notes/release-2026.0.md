# ViPPET 2026.0

## Major features and improvements

- [Demo mode](#demo-mode) - A dedicated UI specifically tailored to conference/tradeshow settings.
- [New predefined pipelines](#new-predefined-pipelines) - New pipelines for retail (Goods Detection,
  Goods Detection and Classification, Age and Gender Recognition), manufacturing (Defect Detection) and
  metro (Smart Parking)
- [Pipeline variants](#pipeline-variants): Each pipeline can now contain multiple variants
  (e.g., CPU, GPU, and NPU), each with its own graph definition
- [Pipeline templates](#pipeline-templates-and-creation-from-templates): Predefined and highly
  optimized Detect and Detect + Classify pipeline templates as starting points for creating new pipelines
- [Simple view for pipeline graphs](#simple-view-for-pipeline-graphs): A simplified pipeline view
  is now available alongside the advanced full GStreamer graph view
- [Cameras as input source](#camera-discovery-and-management): Camera discovery service automatically
  detects both USB and network cameras, which can be used as the input sources in the pipeline editor
- [Live pipeline output preview](#live-pipeline-output-preview): A WebRTC-based video player is
  integrated into the UI, enabling real-time preview of pipeline output during execution
- [Timed pipeline execution](#timed-pipeline-execution): Pipelines can now be configured to run for
  a specified duration; when the video file is shorter than the requested time, it loops automatically
- [Redesigned metrics charts](#redesigned-metrics-charts): The performance view now displays up to
  eight live charts, including GPU frequency, GPU power consumption, GPU memory usage, GPU utilization,
  CPU temperature, CPU frequency, CPU utilization, and CPU power
- [UI improvements](#new-navigation-and-updated-look-and-feel): New navigation style, updated
  look and feel, redesigned pipeline editor layout

## Release Details

This section covers additional details on the new ViPPET's functionality.

### Demo mode

A dedicated demo page is available at the `/demo` endpoint, providing a streamlined presentation view
of the application with pre-configured scenarios and adjusted visual styling.

### New predefined pipelines

- **Retail analytics**: Face detection, age/gender recognition, YOLO 11n object detection, and
  EfficientNet B0 classification pipelines, each available in CPU and GPU variants.
- **Pallet defect detection**: AI-powered quality control pipelines for detecting defects on pallets,
available in CPU, GPU, and NPU variants.
- **Smart parking**: Parking-space occupancy detection pipelines with color classification support,
available in CPU, GPU, and NPU variants.

All predefined pipelines include matching sample videos and model configurations.

### Pipeline variants

- Each pipeline can now contain multiple variants (for example CPU, GPU, and NPU), each with its own
    graph definition. Users can switch between variants to quickly match the pipeline to the available
    hardware without creating separate pipelines.
- Variants are fully integrated across the pipeline editor, performance tests, density tests, and demo mode.

### Pipeline templates and creation from templates

- Predefined pipeline templates (such as Detect and Detect + Classify) are now available as read-only
    starting points for creating new pipelines.
- Users can create a new pipeline from a template and customize it by selecting a model, input source,
    and adding tags.

### Simple view for pipeline graphs

- A simplified pipeline view is now available alongside the advanced graph editor. It hides technical
    GStreamer elements and shows only the key processing steps, making pipelines easier to understand
    and configure for less advanced users.
- Changes made in the simple view are automatically synchronized with the advanced graph, and vice versa.

### Redesigned pipeline editor layout

- A refined pipeline nodes view with flow visualization and automatic adjustment to the results charts window.

### Camera discovery and management

- A new camera discovery service automatically detects both USB cameras (via `v4l2-ctl`) and network
    cameras (via the ONVIF protocol with WS-Discovery).
- Discovered cameras are listed in a dedicated Cameras view, where network cameras can be authenticated
    to retrieve their RTSP stream profiles.
- In the pipeline editor, users can choose between a video file and a camera as the input source directly
    from a dropdown. Only authenticated network cameras appear in the list.

### Live pipeline output preview

- A WebRTC-based video player is integrated into the UI, enabling real-time preview of pipeline output
    during execution. Live preview works with both video file and camera inputs.

### Timed pipeline execution

- Pipelines can now be configured to run for a specified duration. When the video file is shorter than
    the requested time, it loops automatically. When the duration is reached, the pipeline stops gracefully.

### Redesigned metrics charts

- The performance view now displays up to eight live charts — including GPU frequency, GPU power consumption,
    GPU memory usage, GPU utilization, CPU temperature, CPU frequency, CPU utilization, and CPU power —
    depending on the available hardware. When multiple GPUs are present, users can select a specific device.
- After a pipeline run completes, the collected metrics and charts remain visible, allowing users to
    review the full run results without data loss. Persistent charts are fully integrated across the
    pipeline editor, performance tests, density tests, and demo mode.

### New navigation and updated look and feel

- A new navigation view between pages and an updated overall look and feel across the application.

### Custom gvapython scripts

- Users can now add custom Python scripts to pipelines using the `gvapython` element. A new guide
    explains how to configure and integrate these scripts.
