from typing import Any, Dict, List, Optional

from enum import Enum
from pydantic import BaseModel, Field


# # Enums based on OpenAPI schema
class PipelineType(str, Enum):
    GSTREAMER = "GStreamer"
    FFMPEG = "FFmpeg"


class PipelineSource(str, Enum):
    PREDEFINED = "PREDEFINED"
    USER_CREATED = "USER_CREATED"


class TestJobState(str, Enum):
    """
    Generic state of a long-running test job (performance or density).

    Values:
        RUNNING: Job is still executing.
        COMPLETED: Job finished successfully.
        ERROR: Job failed with an error_message.
        ABORTED: Job was cancelled by the user.
    """

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    ABORTED = "ABORTED"


class OptimizationJobState(str, Enum):
    """
    Generic state of an optimization job.

    Values:
        RUNNING: Optimization is in progress.
        COMPLETED: Optimization finished successfully.
        ERROR: Optimization failed with an error_message.
        ABORTED: Optimization was cancelled by the user.
    """

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    ABORTED = "ABORTED"


class ValidationJobState(str, Enum):
    """
    Generic state of a validation job.

    Values:
        RUNNING: Validation is in progress.
        COMPLETED: Validation finished.
        ERROR: Validation failed with a technical error.
        ABORTED: Validation was cancelled by the user.
    """

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    ABORTED = "ABORTED"


class DeviceType(str, Enum):
    """
    High level type of hardware device.

    Values:
        DISCRETE: Standalone accelerator board (for example a dedicated GPU).
        INTEGRATED: Device integrated into CPU or SoC.
    """

    DISCRETE = "DISCRETE"
    INTEGRATED = "INTEGRATED"


class DeviceFamily(str, Enum):
    """
    Hardware family of a device used for inference.

    Values:
        CPU: Central Processing Unit.
        GPU: Graphics Processing Unit.
        NPU: Neural Processing Unit / AI accelerator.
    """

    CPU = "CPU"
    GPU = "GPU"
    NPU = "NPU"


class ModelCategory(str, Enum):
    CLASSIFICATION = "classification"
    DETECTION = "detection"


class OptimizationType(str, Enum):
    PREPROCESS = "preprocess"
    OPTIMIZE = "optimize"


class Node(BaseModel):
    """
    Single node in a generic pipeline graph.

    Attributes:
        id: Node identifier, unique within a single graph.
        type: Element type, usually a framework-specific element name
            (for example a GStreamer element).
        data: Key/value properties for the element (for example element
            arguments or configuration).

            Reserved keys:
              * ``"__node_kind"`` – optional internal discriminator used by the
                backend and UI to distinguish special node types. When present
                and equal to ``"caps"``, the node represents a GStreamer caps
                string (for example ``"video/x-raw,width=320,height=240"``)
                instead of a regular element.

                This field is stored inside ``data`` instead of being a
                top-level attribute to avoid breaking existing API contracts.
    """

    id: str
    type: str
    data: Dict[str, str]


class Edge(BaseModel):
    """
    Directed connection between two nodes in a generic pipeline graph.

    Attributes:
        id: Edge identifier, unique within a single graph.
        source: ID of the source node.
        target: ID of the target node.
    """

    id: str
    source: str
    target: str


class MessageResponse(BaseModel):
    """
    Generic message payload used as a simple response body.

    This model is used mainly for non-2xx responses to provide a plain
    English description of what happened (error or informational status).

    Attributes:
        message: Description of the error or status.

    Example:
        .. code-block:: json

            {
              "message": "Performance job job123 not found"
            }
    """

    message: str = Field(
        ...,
        description="Human-readable error or status message.",
        examples=[
            "Job job123 not found",
            "Unexpected error while discovering devices.",
        ],
    )


class PipelineCreationResponse(BaseModel):
    """
    Response body returned after a new pipeline is created.

    Attributes:
        id: Identifier of the created pipeline.

    Example:
        .. code-block:: json

            {
              "id": "pipeline-a3f5d9e1"
            }
    """

    id: str


class PipelineDescription(BaseModel):
    """
    Request or response body containing a pipeline description string.

    The string is a single launch line in the selected pipeline
    framework (for example GStreamer).

    Attributes:
        pipeline_description: Full pipeline description line to be converted
            or executed.
    """

    pipeline_description: str = Field(
        ...,
        description="GStreamer-like pipeline string.",
        examples=["videotestsrc ! videoconvert ! autovideosink"],
    )


class PipelineGraph(BaseModel):
    """
    Request or response body containing the structured pipeline graph.

    This is a generic representation and is used by multiple endpoints
    (conversion, validation, optimization).

    Attributes:
        nodes: List of graph nodes.
        edges: Directed connections between nodes.
    """

    nodes: List[Node] = Field(
        ...,
        description="List of pipeline nodes.",
        examples=[
            [
                {"id": "0", "type": "videotestsrc", "data": {}},
                {"id": "1", "type": "videoconvert", "data": {}},
                {"id": "2", "type": "autovideosink", "data": {}},
            ]
        ],
    )
    edges: List[Edge] = Field(
        ...,
        description="List of directed edges between nodes.",
        examples=[
            [
                {"id": "0", "source": "0", "target": "1"},
                {"id": "1", "source": "1", "target": "2"},
            ]
        ],
    )


class PipelineParameters(BaseModel):
    """
    Optional parameter set attached to a pipeline.

    Attributes:
        default: Arbitrary key/value dictionary with default parameter
            values to be used when running the pipeline.

    Example:
        .. code-block:: json

            {
              "default": {
                "max-runtime": 60,
                "threshold": 0.5
              }
            }
    """

    default: Optional[Dict[str, Any]]


class PipelinePerformanceSpec(BaseModel):
    """
    Per-pipeline configuration for performance and density tests.

    Attributes:
        id: Pipeline identifier to be executed.
        streams: Number of parallel streams to run for this pipeline.
    """

    id: str = Field(
        ...,
        description="ID of the pipeline to test.",
        examples=["pipeline-1234abcd"],
    )
    streams: int = Field(
        default=1,
        ge=0,
        description="Number of parallel streams for this pipeline.",
        examples=[1, 4, 16],
    )


class PipelineDensitySpec(BaseModel):
    """
    Per-pipeline configuration for density tests.

    Used in DensityTestSpec to describe how total streams are split between
    pipelines based on relative ratios.

    Attributes:
        id: Pipeline identifier.
        stream_rate: Relative share of total streams for this pipeline
            expressed as percentage. All stream_rate values in the request
            must sum to 100.

    Example:
        .. code-block:: json

            {
              "id": "pipeline-1",
              "stream_rate": 50
            }
    """

    id: str = Field(
        ...,
        description="ID of the pipeline used in density test.",
        examples=["pipeline-1"],
    )
    stream_rate: int = Field(
        default=100,
        ge=0,
        description="Relative share of total streams for this pipeline (percentage).",
        examples=[50],
    )


class Pipeline(BaseModel):
    """
    Full pipeline definition exposed by the pipelines API.

    Attributes:
        id: Unique pipeline identifier generated by the backend.
        name: Logical pipeline name (may have multiple versions).
        version: Version number of this pipeline definition.
        description: Human readable description.
        source: Origin of the pipeline (PREDEFINED or USER_CREATED).
        type: Pipeline type (for example GStreamer).
        pipeline_graph: Structured graph representation derived from
            the launch string.
        parameters: Optional default parameter set for this pipeline.

    Example:
        .. code-block:: json

            {
              "id": "pipeline-a3f5d9e1",
              "name": "vehicle-detection",
              "version": 1,
              "description": "Simple vehicle detection pipeline",
              "source": "USER_CREATED",
              "type": "GStreamer",
              "pipeline_graph": {
                "nodes": [...],
                "edges": [...]
              },
              "parameters": {
                "default": {
                  "max-runtime": 60
                }
              }
            }
    """

    id: str
    name: str
    version: int
    description: str
    source: PipelineSource
    type: PipelineType
    pipeline_graph: PipelineGraph
    parameters: Optional[PipelineParameters]


class PipelineDefinition(BaseModel):
    """
    Input model used to create a new pipeline via the API.

    Attributes:
        name: Non-empty pipeline name.
        version: Pipeline version (must be >= 1). For a new name this
            must be 1; for an existing name it must be the next version.
        description: Non-empty human-readable pipeline description.
        source: Pipeline source. For create endpoint this value is
            overwritten to USER_CREATED.
        type: Pipeline type (e.g. GStreamer).
        pipeline_description: GStreamer launch string that will be
            parsed into a PipelineGraph.
        parameters: Optional default parameter set.

    Example:
        .. code-block:: json

            {
              "name": "vehicle-detection",
              "version": 1,
              "description": "Simple vehicle detection pipeline",
              "type": "GStreamer",
              "pipeline_description": "filesrc location=input.mp4 ! decodebin ! fakesink",
              "parameters": {
                "default": {
                  "max-runtime": 60
                }
              }
            }
    """

    name: str = Field(..., min_length=1, description="Non-empty pipeline name.")
    version: int = Field(
        default=1,
        ge=1,
        description="Pipeline version (must be greater than or equal to 1).",
    )
    description: str = Field(
        ..., min_length=1, description="Non-empty human-readable pipeline description."
    )
    source: PipelineSource = PipelineSource.USER_CREATED
    type: PipelineType
    pipeline_description: str = Field(
        ...,
        min_length=1,
        description="GStreamer pipeline definition string (e.g., 'fakesrc ! fakesink').",
    )
    parameters: Optional[PipelineParameters]


class PipelineUpdate(BaseModel):
    """
    Partial update model for an existing pipeline.

    All fields are optional; at least one must be provided when calling
    the update endpoint.

    Attributes:
        name: Optional new pipeline name (non-empty if provided).
        description: Optional new description (non-empty if provided).
        pipeline_graph: Optional new graph; must be non-empty and valid.
        parameters: Optional new default parameters for the pipeline.

    Example:
        .. code-block:: json

            {
              "description": "Updated pipeline description",
              "parameters": {
                "default": {
                  "max-runtime": 120
                }
              }
            }
    """

    name: Optional[str] = None
    description: Optional[str] = None
    pipeline_graph: Optional[PipelineGraph] = None
    parameters: Optional[PipelineParameters] = None


class PipelineValidation(BaseModel):
    """
    Request body for pipeline validation.

    Attributes:
        type: Pipeline type (default is GStreamer).
        pipeline_graph: Structured graph representation of the pipeline.
        parameters: Optional parameter set for validation (for example
            ``{"max-runtime": 10}``).

    Example:
        .. code-block:: json

            {
              "type": "GStreamer",
              "pipeline_graph": {
                "nodes": [...],
                "edges": [...]
              },
              "parameters": {
                "max-runtime": 10
              }
            }
    """

    type: PipelineType = PipelineType.GSTREAMER
    pipeline_graph: PipelineGraph
    parameters: Optional[Dict[str, Any]] = Field(
        default=None, examples=[{"max-runtime": 10}]
    )


class ValidationJobResponse(BaseModel):
    """
    Simple envelope with a new validation job identifier.

    Used as response body when a validation job is created.
    """

    job_id: str = Field(
        ...,
        description="Identifier of the created validation job.",
        examples=["val001"],
    )


class PipelineRequestOptimize(BaseModel):
    """
    Request body for starting a pipeline optimization job.

    Attributes:
        type: Optimization type:
            * ``preprocess`` – run only preprocessing.
            * ``optimize`` – run full optimization with search/sampling.
        parameters: Optional dictionary with optimizer-specific settings.

    Example:
        .. code-block:: json

            {
              "type": "optimize",
              "parameters": {
                "search_duration": 300,
                "sample_duration": 10
              }
            }
    """

    type: OptimizationType
    parameters: Optional[Dict[str, Any]]


class EncoderDeviceConfig(BaseModel):
    """
    Encoder device configuration used in video output settings.

    Attributes:
        device_name: Name of the encoder device (for example ``"GPU"``).
        gpu_id: Optional GPU index when applicable.

    Example:
        .. code-block:: json

            {
              "device_name": "GPU",
              "gpu_id": 0
            }
    """

    device_name: str = Field(
        default="GPU",
        description="Name of the encoder device (e.g., 'GPU', 'CPU', 'NPU')",
        examples=["GPU", "CPU", "NPU"],
    )
    gpu_id: Optional[int] = Field(
        default=None,
        description="GPU device index (only applicable when device_name indicates a GPU)",
        examples=[0, 1],
    )


class VideoOutputConfig(BaseModel):
    """
    Generic configuration of optional encoded video output.

    Attributes:
        enabled: Flag to enable or disable video output generation.
        encoder_device: EncoderDeviceConfig used when video output is enabled.

    Example:
        .. code-block:: json

            {
              "enabled": false,
              "encoder_device": {
                "device_name": "GPU",
                "gpu_id": 0
              }
            }
    """

    enabled: bool = Field(
        default=False, description="Flag to enable or disable video output generation."
    )
    encoder_device: EncoderDeviceConfig = Field(
        default=EncoderDeviceConfig(device_name="GPU", gpu_id=0),
        description="Encoder device configuration (only applicable when video output is enabled).",
        examples=[{"device_name": "GPU", "gpu_id": 0}],
    )


class PerformanceTestSpec(BaseModel):
    """
    Request body for starting a performance test.

    Attributes:
        pipeline_performance_specs: List of pipelines and their stream counts.
        video_output: Optional configuration for storing encoded video outputs.
    """

    pipeline_performance_specs: list[PipelinePerformanceSpec] = Field(
        ...,
        description="List of pipelines with number of streams for each.",
        examples=[
            [
                {"id": "pipeline-1", "streams": 8},
                {"id": "pipeline-2", "streams": 8},
            ]
        ],
    )
    video_output: VideoOutputConfig = Field(
        default=VideoOutputConfig(
            enabled=False,
            encoder_device=EncoderDeviceConfig(device_name="GPU", gpu_id=0),
        ),
        description="Video output configuration.",
        examples=[
            {"enabled": False, "encoder_device": {"device_name": "GPU", "gpu_id": 0}}
        ],
    )


class DensityTestSpec(BaseModel):
    """
    Request body for starting a density test.

    Attributes:
        fps_floor: Minimum acceptable FPS per stream.
        pipeline_density_specs: List of pipelines with relative stream_rate ratios.
        video_output: Optional configuration for storing encoded video outputs.
    """

    fps_floor: int = Field(
        ge=0,
        description="Minimum acceptable FPS per stream.",
        examples=[30],
    )
    pipeline_density_specs: list[PipelineDensitySpec] = Field(
        ...,
        description="List of pipelines with relative stream_rate percentages that must sum to 100.",
        examples=[
            [
                {"id": "pipeline-1", "stream_rate": 50},
                {"id": "pipeline-2", "stream_rate": 50},
            ]
        ],
    )
    video_output: VideoOutputConfig = Field(
        default=VideoOutputConfig(
            enabled=False,
            encoder_device=EncoderDeviceConfig(device_name="GPU", gpu_id=0),
        ),
        description="Video output configuration.",
        examples=[
            {"enabled": False, "encoder_device": {"device_name": "GPU", "gpu_id": 0}}
        ],
    )


class TestJobResponse(BaseModel):
    """
    Simple envelope with a new test job identifier.

    Used as response body when performance or density test job is created.
    """

    job_id: str = Field(
        ...,
        description="Identifier of the created test job.",
        examples=["job123"],
    )


class TestsJobStatus(BaseModel):
    """
    Base status fields shared by performance and density jobs.

    Attributes:
        id: Job identifier.
        start_time: Start time in milliseconds since epoch.
        elapsed_time: Elapsed time in milliseconds.
        state: Current job state.
        total_fps: Total FPS across all streams (may be null).
        per_stream_fps: Average FPS per stream (may be null).
        total_streams: Number of active streams (may be null).
        streams_per_pipeline: List of stream counts per pipeline.
        video_output_paths: Mapping from pipeline id to list of output file paths.
        error_message: Error description when state is ERROR or ABORTED.
    """

    id: str
    start_time: int
    elapsed_time: int
    state: TestJobState
    total_fps: Optional[float]
    per_stream_fps: Optional[float]
    total_streams: Optional[int]
    streams_per_pipeline: Optional[List[PipelinePerformanceSpec]]
    video_output_paths: Optional[Dict[str, List[str]]]
    error_message: Optional[str]


class PerformanceJobStatus(TestsJobStatus):
    """
    Status of a performance test job.

    Inherits all fields from TestsJobStatus without changes.
    """

    pass


class DensityJobStatus(TestsJobStatus):
    """
    Status of a density test job.

    Inherits all fields from TestsJobStatus without changes.
    """

    pass


class PerformanceJobSummary(BaseModel):
    """
    Short summary for a performance test job.

    Attributes:
        id: Job identifier.
        request: Original PerformanceTestSpec used to start the job.
    """

    id: str
    request: PerformanceTestSpec


class DensityJobSummary(BaseModel):
    """
    Short summary for a density test job.

    Attributes:
        id: Job identifier.
        request: Original DensityTestSpec used to start the job.
    """

    id: str
    request: DensityTestSpec


class OptimizationJobResponse(BaseModel):
    """
    Simple envelope with a new optimization job identifier.

    Used as response body when an optimization job is created.
    """

    job_id: str = Field(
        ...,
        description="Identifier of the created optimization job.",
        examples=["opt789"],
    )


class OptimizationJobStatus(BaseModel):
    """
    Detailed status of an optimization job.

    Attributes:
        id: Job identifier.
        type: Optimization type (PREPROCESS or OPTIMIZE).
        start_time: Start time in milliseconds since epoch.
        elapsed_time: Elapsed time in milliseconds.
        state: Current job state.
        total_fps: Measured FPS for optimized pipeline (for OPTIMIZE).
        original_pipeline_graph: Original pipeline graph before optimization.
        optimized_pipeline_graph: Optimized pipeline graph (if available).
        original_pipeline_description: Original GStreamer pipeline string.
        optimized_pipeline_description: Optimized GStreamer pipeline string (if any).
        error_message: Error details when state is ERROR or ABORTED.
    """

    id: str
    type: Optional[OptimizationType]
    start_time: int
    elapsed_time: int
    state: OptimizationJobState
    total_fps: Optional[float]
    original_pipeline_graph: PipelineGraph
    optimized_pipeline_graph: Optional[PipelineGraph]
    original_pipeline_description: str
    optimized_pipeline_description: Optional[str]
    error_message: Optional[str]


class OptimizationJobSummary(BaseModel):
    """
    Short summary for an optimization job.

    Attributes:
        id: Job identifier.
        request: Original PipelineRequestOptimize used to start the job.
    """

    id: str
    request: PipelineRequestOptimize


class ValidationJobStatus(BaseModel):
    """
    Detailed status of a validation job.

    Attributes:
        id: Job identifier.
        start_time: Start time in milliseconds since epoch.
        elapsed_time: Elapsed time in milliseconds.
        state: Current validation job state.
        is_valid: Final validation result (true/false) when completed.
        error_message: Optional list of validation error descriptions.
    """

    id: str
    start_time: int
    elapsed_time: int
    state: ValidationJobState
    is_valid: Optional[bool]
    error_message: Optional[List[str]]


class ValidationJobSummary(BaseModel):
    """
    Short summary for a validation job.

    Attributes:
        id: Job identifier.
        request: Original PipelineValidation request.
    """

    id: str
    request: PipelineValidation


class Device(BaseModel):
    """
    Hardware device description used by multiple APIs.

    This model is a simplified view of the device information returned
    by the runtime (for example OpenVINO) and is suitable for UI consumption.

    Attributes:
        device_name: Short identifier used when selecting the device
            (for example ``"CPU"``, ``"GPU"``, ``"GPU.0"``, ``"NPU"``).
        full_device_name: Human readable device name (CPU/GPU/NPU model).
        device_type: High level device type (``INTEGRATED`` or ``DISCRETE``).
        device_family: Hardware family (``CPU``, ``GPU``, ``NPU``).
        gpu_id: Optional GPU index when applicable; null for non-GPU devices.

    Example:
        .. code-block:: json

            {
              "device_name": "GPU.0",
              "full_device_name": "Intel(R) Arc(TM) Graphics (iGPU) (GPU.0)",
              "device_type": "INTEGRATED",
              "device_family": "GPU",
              "gpu_id": 0
            }
    """

    device_name: str
    full_device_name: str
    device_type: DeviceType
    device_family: DeviceFamily
    gpu_id: Optional[int]


class Model(BaseModel):
    """
    Description of a single model exposed by the models API.

    Attributes:
        name: Internal model identifier used by the backend.
        display_name: Human readable model name suitable for UI.
        category: Logical model category (classification, detection), or null
            when the type from configuration is unknown or unsupported.
        precision: Model precision string (for example "FP32", "INT8"), or null
            when not specified.

    Example:
        .. code-block:: json

            {
              "name": "vehicle-detection-0202",
              "display_name": "Vehicle Detection",
              "category": "detection",
              "precision": "FP32"
            }
    """

    name: str
    display_name: str
    category: Optional[ModelCategory]
    precision: Optional[str]


class MetricSample(BaseModel):
    """
    Single metric sample used in streaming metrics APIs.

    Attributes:
        name: Metric name (for example ``"total_fps"`` or ``"cpu_usage"``).
        description: Short human-readable description of the metric.
        timestamp: Unix timestamp in milliseconds when the sample was taken.
        value: Numeric value of the metric.

    Example:
        .. code-block:: json

            {
              "name": "total_fps",
              "description": "Total FPS over all streams",
              "timestamp": 1715000000000,
              "value": 512.4
            }
    """

    name: str
    description: str
    timestamp: int
    value: float


class Video(BaseModel):
    """
    Metadata for a single input video file.

    Attributes:
        filename: Base name of the video file located under RECORDINGS_PATH.
        width: Frame width in pixels.
        height: Frame height in pixels.
        fps: Frames per second for the stream.
        frame_count: Total number of frames in the file.
        codec: Normalized codec name (for example ``"h264"`` or ``"h265"``).
        duration: Approximate duration in seconds.

    Example:
        .. code-block:: json

            {
              "filename": "traffic_1080p_h264.mp4",
              "width": 1920,
              "height": 1080,
              "fps": 30.0,
              "frame_count": 900,
              "codec": "h264",
              "duration": 30.0
            }
    """

    filename: str
    width: int
    height: int
    fps: float
    frame_count: int
    codec: str
    duration: float
