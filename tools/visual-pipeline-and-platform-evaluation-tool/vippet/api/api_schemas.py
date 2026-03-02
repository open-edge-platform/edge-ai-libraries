from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Literal

from enum import Enum
from pydantic import BaseModel, Field, model_validator


# # Enums based on OpenAPI schema
class PipelineSource(str, Enum):
    """
    **Source of a pipeline definition.**

    ## Values
    - `PREDEFINED` - Pipeline is predefined by the system
    - `USER_CREATED` - Pipeline was created by the user
    - `TEMPLATE` - Pipeline is a template

    ### Example
    ```json
    "USER_CREATED"
    ```
    """

    PREDEFINED = "PREDEFINED"
    USER_CREATED = "USER_CREATED"
    TEMPLATE = "TEMPLATE"


class AppStatus(str, Enum):
    """
    **Application status enum for tracking initialization progress.**

    ## Values
    - `STARTING` - Application is starting, no initialization yet
    - `INITIALIZING` - Application is initializing resources (e.g., loading videos)
    - `READY` - Application is fully initialized and ready to serve requests
    - `SHUTDOWN` - Application is shutting down

    ### Example
    ```json
    "ready"
    ```
    """

    STARTING = "starting"
    INITIALIZING = "initializing"
    READY = "ready"
    SHUTDOWN = "shutdown"


class TestJobState(str, Enum):
    """
    **Generic state of a long-running test job (performance or density).**

    ## Values
    - `RUNNING` - Job is still executing
    - `COMPLETED` - Job finished successfully
    - `FAILED` - Job finished unsuccessfully

    ### Example
    ```json
    "RUNNING"
    ```
    """

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OptimizationJobState(str, Enum):
    """
    **Generic state of an optimization job.**

    ## Values
    - `RUNNING` - Optimization is in progress
    - `COMPLETED` - Optimization finished successfully
    - `FAILED` - Optimization finished unsuccessfully

    ### Example
    ```json
    "RUNNING"
    ```
    """

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ValidationJobState(str, Enum):
    """
    **Generic state of a validation job.**

    ## Values
    - `RUNNING` - Validation is in progress
    - `COMPLETED` - Validation finished successfully (pipeline is valid)
    - `FAILED` - Validation finished unsuccessfully (pipeline is invalid, or encountered an error)

    ### Example
    ```json
    "RUNNING"
    ```
    """

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DeviceType(str, Enum):
    """
    **High level type of hardware device.**

    ## Values
    - `DISCRETE` - Standalone accelerator board (for example a dedicated GPU)
    - `INTEGRATED` - Device integrated into CPU or SoC

    ### Example
    ```json
    "DISCRETE"
    ```
    """

    DISCRETE = "DISCRETE"
    INTEGRATED = "INTEGRATED"


class DeviceFamily(str, Enum):
    """
    **Hardware family of a device used for inference.**

    ## Values
    - `CPU` - Central Processing Unit
    - `GPU` - Graphics Processing Unit
    - `NPU` - Neural Processing Unit / AI accelerator

    ### Example
    ```json
    "CPU"
    ```
    """

    CPU = "CPU"
    GPU = "GPU"
    NPU = "NPU"


class ModelCategory(str, Enum):
    """
    **Model category for classification or detection tasks.**

    ## Values
    - `CLASSIFICATION` - Classification model
    - `DETECTION` - Detection model

    ### Example
    ```json
    "detection"
    ```
    """

    CLASSIFICATION = "classification"
    DETECTION = "detection"


class OptimizationType(str, Enum):
    """
    **Type of optimization operation.**

    ## Values
    - `PREPROCESS` - Run only preprocessing
    - `OPTIMIZE` - Run full optimization with search/sampling

    ### Example
    ```json
    "optimize"
    ```
    """

    PREPROCESS = "preprocess"
    OPTIMIZE = "optimize"


class CameraType(str, Enum):
    """
    **Type of camera device.**

    ## Values
    - `USB` - USB camera connected directly to the system
    - `NETWORK` - Network camera accessible via IP protocols

    ### Example
    ```json
    "USB"
    ```
    """

    USB = "USB"
    NETWORK = "NETWORK"


class HealthResponse(BaseModel):
    """
    **Response model for health endpoint.**

    Used by Docker healthcheck and monitoring systems to verify
    application health status.

    ## Attributes
    - `healthy` - True if application is healthy (not shutdown)

    ### Example
    ```json
    {
      "healthy": true
    }
    ```
    """

    healthy: bool


class StatusResponse(BaseModel):
    """
    **Response model for status endpoint.**

    Provides detailed information about application initialization state
    and readiness to serve requests.

    ## Attributes
    - `status` - Current application status (STARTING, INITIALIZING, READY, or SHUTDOWN)
    - `message` - Optional message describing current activity or initialization progress
    - `ready` - True if application is ready to serve API requests

    ### Example
    ```json
    {
      "status": "ready",
      "message": null,
      "ready": true
    }
    ```
    """

    status: AppStatus
    message: Optional[str]
    ready: bool


class Node(BaseModel):
    """
    **Single node in a generic pipeline graph.**

    ## Attributes
    - `id` - Node identifier, unique within a single graph
    - `type` - Element type, usually a framework-specific element name (e.g., GStreamer element)
    - `data` - Key/value properties for the element (e.g., element arguments or configuration)
      - Reserved key: `__node_kind__` - Optional internal discriminator for special node types. When equal to "caps", represents a GStreamer caps string (e.g., "video/x-raw,width=320,height=240") instead of a regular element. Stored in `data` to avoid breaking existing API contracts.
    """

    id: str
    type: str
    data: Dict[str, str]


class Edge(BaseModel):
    """
    **Directed connection between two nodes in a generic pipeline graph.**

    ## Attributes
    - `id` - Edge identifier, unique within a single graph
    - `source` - ID of the source node
    - `target` - ID of the target node
    """

    id: str
    source: str
    target: str


class MessageResponse(BaseModel):
    """
    **Generic message payload used as a simple response body.**

    This model is used mainly for non-2xx responses to provide a plain
    English description of what happened (error or informational status).

    ## Attributes
    - `message` - Human-readable error or status message

    ### Example
    ```json
    {
      "message": "Performance job job123 not found"
    }
    ```
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
    **Response body returned after a new pipeline is created.**

    ## Attributes
    - `id` - Identifier of the created pipeline

    ### Example
    ```json
    {
      "id": "pipeline-a3f5d9e1"
    }
    ```
    """

    id: str


class PipelineDescription(BaseModel):
    """
    **Request or response body containing a GStreamer pipeline string.**

    The pipeline_description field contains a complete GStreamer launch line
    with elements separated by '!' symbols.

    ## Attributes
    - `pipeline_description` - Complete GStreamer pipeline string to be converted or executed (elements separated by '!')

    ### Example
    ```json
    {
      "pipeline_description": "filesrc location=input.mp4 ! decodebin ! videoconvert ! autovideosink"
    }
    ```
    """

    pipeline_description: str = Field(
        ...,
        description="GStreamer pipeline string with elements separated by '!'.",
        examples=["videotestsrc ! videoconvert ! autovideosink"],
    )


class PipelineGraph(BaseModel):
    """
    **Request or response body containing the structured pipeline graph.**

    This is a generic representation used by multiple endpoints
    (conversion, validation, optimization).

    ## Attributes
    - `nodes` - List of graph nodes
    - `edges` - Directed connections between nodes
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


class Variant(BaseModel):
    """
    **Single variant of a pipeline for different hardware targets.**

    ## Attributes
    - `id` - Unique variant identifier generated by the backend (not used when creating or updating variants)
    - `name` - Variant name (e.g., "CPU", "GPU", "NPU")
    - `read_only` - Whether the variant is read-only (defaults to false, can only be true for PREDEFINED pipeline variants)
    - `pipeline_graph` - Advanced graph representation for this variant
    - `pipeline_graph_simple` - Simplified graph representation for this variant
    - `created_at` - Creation timestamp as UTC datetime (set by backend only, not modifiable via API)
    - `modified_at` - Last modification timestamp as UTC datetime (updated when variant is modified, set by backend only)
    """

    id: str = Field(
        ...,
        description="Unique variant identifier generated by the backend.",
    )
    name: str = Field(
        ...,
        min_length=1,
        description="Variant name identifying the hardware target.",
        examples=["CPU", "GPU", "NPU"],
    )
    read_only: bool = Field(
        default=False,
        description="Whether the variant is read-only. Can only be true for PREDEFINED or TEMPLATE pipelines.",
    )
    pipeline_graph: PipelineGraph = Field(
        ...,
        description="Advanced graph view with all pipeline elements for this variant.",
    )
    pipeline_graph_simple: PipelineGraph = Field(
        ...,
        description="Simplified graph view for this variant.",
    )
    created_at: datetime = Field(
        ...,
        description="Creation timestamp as UTC datetime. Set by backend only.",
    )
    modified_at: datetime = Field(
        ...,
        description="Last modification timestamp as UTC datetime. Set by backend only.",
    )


class VariantCreate(BaseModel):
    """
    **Input model for creating a new variant.**

    The id and read_only fields are not included as they are
    generated/set by the backend.

    ## Attributes
    - `name` - Variant name (required, non-empty)
    - `pipeline_graph` - Advanced graph representation (required)
    - `pipeline_graph_simple` - Simplified graph representation (required)
    """

    name: str = Field(
        ...,
        min_length=1,
        description="Variant name identifying the hardware target.",
        examples=["CPU", "GPU", "NPU"],
    )
    pipeline_graph: PipelineGraph = Field(
        ...,
        description="Advanced graph view with all pipeline elements for this variant.",
    )
    pipeline_graph_simple: PipelineGraph = Field(
        ...,
        description="Simplified graph view for this variant.",
    )


class VariantUpdate(BaseModel):
    """
    **Input model for updating an existing variant.**

    All fields are optional, but at least one must be provided.
    Only one of pipeline_graph or pipeline_graph_simple can be provided per request.
    String fields (name) must be non-empty after trimming whitespace.

    Validation is performed in model_validator to fail fast on invalid input.

    ## Attributes
    - `name` - Optional new variant name (non-empty after trim if provided)
    - `pipeline_graph` - Optional advanced graph (mutually exclusive with pipeline_graph_simple)
    - `pipeline_graph_simple` - Optional simplified graph (mutually exclusive with pipeline_graph)
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        description="New variant name.",
    )
    pipeline_graph: Optional[PipelineGraph] = Field(
        default=None,
        description="New advanced graph (mutually exclusive with pipeline_graph_simple).",
    )
    pipeline_graph_simple: Optional[PipelineGraph] = Field(
        default=None,
        description="New simplified graph (mutually exclusive with pipeline_graph).",
    )

    @model_validator(mode="after")
    def validate_update_fields(self):
        """Ensure at least one field is provided, graphs are exclusive, and strings are non-empty after trim."""
        # Ensure that both graphs are not provided together
        if self.pipeline_graph is not None and self.pipeline_graph_simple is not None:
            raise ValueError(
                "Cannot provide both 'pipeline_graph' and 'pipeline_graph_simple' in the same request."
            )

        # Ensure at least one field is provided
        if (
            self.name is None
            and self.pipeline_graph is None
            and self.pipeline_graph_simple is None
        ):
            raise ValueError(
                "At least one of 'name', 'pipeline_graph', or 'pipeline_graph_simple' must be provided."
            )

        # Check that string fields are non-empty after trim
        if self.name is not None and self.name.strip() == "":
            raise ValueError("Field 'name' must not be empty.")

        return self


class PipelineGraphResponse(BaseModel):
    """
    **Response body containing both advanced and simple views of a pipeline graph.**

    Used by the /convert/to-graph endpoint to return both representations
    at once.

    ## Attributes
    - `pipeline_graph` - Advanced view with all technical elements including queues, converters, caps nodes, and other plumbing elements. Contains the complete pipeline structure as parsed from the pipeline description
    - `pipeline_graph_simple` - Simplified view showing only meaningful elements such as sources, inference nodes (gva*), and sinks. Technical plumbing elements are hidden and edges are reconnected to show direct connections between visible nodes

    ### Example
    ```json
    {
      "pipeline_graph": {
        "nodes": [
          {"id": "0", "type": "filesrc", "data": {"location": "input.mp4"}},
          {"id": "1", "type": "decodebin", "data": {}},
          {"id": "2", "type": "queue", "data": {}},
          {"id": "3", "type": "gvadetect", "data": {"model": "yolo"}},
          {"id": "4", "type": "fakesink", "data": {}}
        ],
        "edges": [
          {"id": "0", "source": "0", "target": "1"},
          {"id": "1", "source": "1", "target": "2"},
          {"id": "2", "source": "2", "target": "3"},
          {"id": "3", "source": "3", "target": "4"}
        ]
      },
      "pipeline_graph_simple": {
        "nodes": [
          {"id": "0", "type": "filesrc", "data": {"location": "input.mp4"}},
          {"id": "3", "type": "gvadetect", "data": {"model": "yolo"}},
          {"id": "4", "type": "fakesink", "data": {}}
        ],
        "edges": [
          {"id": "0", "source": "0", "target": "3"},
          {"id": "1", "source": "3", "target": "4"}
        ]
      }
    }
    ```
    """

    pipeline_graph: PipelineGraph = Field(
        ...,
        description="Advanced graph view with all pipeline elements including technical plumbing.",
    )
    pipeline_graph_simple: PipelineGraph = Field(
        ...,
        description="Simplified graph view showing only sources, inference nodes, and sinks.",
    )


class VariantReference(BaseModel):
    """
    **Reference to an existing pipeline variant by IDs.**

    Used when specifying a pipeline for tests by referencing an existing
    stored variant instead of providing an inline graph.

    ## Attributes
    - `source` - Discriminator field, always "variant" for this type
    - `pipeline_id` - ID of the pipeline containing the variant
    - `variant_id` - ID of the variant to use

    ### Example
    ```json
    {
      "source": "variant",
      "pipeline_id": "pipeline-a3f5d9e1",
      "variant_id": "variant-abc123"
    }
    ```
    """

    source: Literal["variant"] = "variant"
    pipeline_id: str = Field(
        ...,
        description="ID of the pipeline containing the variant.",
        examples=["pipeline-a3f5d9e1"],
    )
    variant_id: str = Field(
        ...,
        description="ID of the variant within the pipeline.",
        examples=["variant-abc123"],
    )


class GraphInline(BaseModel):
    """
    **Inline pipeline graph definition.**

    Used when specifying a pipeline for tests by providing the graph
    directly instead of referencing an existing variant.

    ## Attributes
    - `source` - Discriminator field, always "graph" for this type
    - `pipeline_graph` - Complete pipeline graph to use
    - `graph_id` - Optional custom identifier for this inline graph (if provided, used instead of generating a hash-based ID; must be URL-safe with only lowercase letters, numbers, and dashes; if not provided, synthetic ID generated from graph content hash)

    ### Example (without graph_id - uses generated hash)
    ```json
    {
      "source": "graph",
      "pipeline_graph": {
        "nodes": [...],
        "edges": [...]
      }
    }
    ```

    ### Example (with custom graph_id)
    ```json
    {
      "source": "graph",
      "graph_id": "my-custom-pipeline",
      "pipeline_graph": {
        "nodes": [...],
        "edges": [...]
      }
    }
    ```
    """

    source: Literal["graph"] = "graph"
    graph_id: Optional[str] = Field(
        default=None,
        description="Optional custom identifier for inline graph. Must be URL-safe.",
        examples=["my-custom-pipeline", "detection-gpu-v2"],
    )
    pipeline_graph: PipelineGraph = Field(
        ...,
        description="Inline pipeline graph to use for the test.",
    )


class PipelineDescriptionSource(BaseModel):
    """
    **Pipeline source from GStreamer pipeline description string.**

    Used when specifying a pipeline for tests by providing a GStreamer
    pipeline description string that will be parsed into a graph.

    ## Attributes
    - `source` - Discriminator field, always "description" for this type
    - `pipeline_description` - GStreamer pipeline string with elements separated by '!' (must be non-empty)
    - `description_id` - Optional custom identifier for this pipeline description (if provided, used instead of generating a hash-based ID; must be URL-safe with only lowercase letters, numbers, and dashes; if not provided, synthetic ID generated from description content hash)

    ### Example (without description_id - uses generated hash)
    ```json
    {
      "source": "description",
      "pipeline_description": "videotestsrc ! videoconvert ! fakesink"
    }
    ```

    ### Example (with custom description_id)
    ```json
    {
      "source": "description",
      "description_id": "my-test-pipeline",
      "pipeline_description": "videotestsrc ! videoconvert ! fakesink"
    }
    ```
    """

    source: Literal["description"] = "description"
    pipeline_description: str = Field(
        ...,
        min_length=1,
        description="GStreamer pipeline string with elements separated by '!'.",
        examples=["videotestsrc ! videoconvert ! fakesink"],
    )
    description_id: Optional[str] = Field(
        default=None,
        description="Optional custom identifier for pipeline description. Must be URL-safe.",
        examples=["my-test-pipeline", "detection-cpu-v1"],
    )


# Discriminated union for graph source
GraphSource = Union[VariantReference, GraphInline, PipelineDescriptionSource]


class PipelineStreamSpec(BaseModel):
    """
    **Simple representation of pipeline stream count with pipeline identifier.**

    Used in test job results to report which pipelines were executed and how many
    streams were allocated to each.

    The id field format depends on the pipeline source:
    - For variant reference: "/pipelines/{pipeline_id}/variants/{variant_id}"
    - For inline graph: "__graph-{16-char-hash}"

    ## Attributes
    - `id` - Pipeline identifier (either variant path or synthetic graph ID)
    - `streams` - Number of streams allocated to this pipeline

    ### Example (Variant reference)
    ```json
    {
      "id": "/pipelines/pipeline-a3f5d9e1/variants/variant-abc123",
      "streams": 4
    }
    ```

    ### Example (Inline graph)
    ```json
    {
      "id": "__graph-1a2b3c4d5e6f7g8h",
      "streams": 2
    }
    ```
    """

    id: str = Field(
        ...,
        description="Pipeline identifier - variant path or synthetic graph ID.",
        examples=[
            "/pipelines/pipeline-a3f5d9e1/variants/variant-abc123",
            "__graph-1a2b3c4d5e6f7g8h",
        ],
    )
    streams: int = Field(
        ...,
        ge=0,
        description="Number of streams allocated to this pipeline.",
        examples=[4],
    )


class PipelinePerformanceSpec(BaseModel):
    """
    **Per-pipeline configuration for performance and density tests.**

    The pipeline can be specified in two ways:
    - `variant` - Reference to an existing pipeline variant by pipeline_id and variant_id
    - `graph` - Inline pipeline graph provided directly

    ## Attributes
    - `pipeline` - Graph source (either a reference to existing variant or inline graph; discriminated by 'source' field: \"variant\" or \"graph\")
    - `streams` - Number of parallel streams to run for this pipeline

    ### Example (Variant reference)
    ```json
    {
      "pipeline": {
        "source": "variant",
        "pipeline_id": "pipeline-a3f5d9e1",
        "variant_id": "variant-abc123"
      },
      "streams": 4
    }
    ```

    ### Example (Inline graph)
    ```json
    {
      "pipeline": {
        "source": "graph",
        "pipeline_graph": {
          "nodes": [...],
          "edges": [...]
        }
      },
      "streams": 4
    }
    ```
    """

    pipeline: GraphSource = Field(
        ...,
        discriminator="source",
        description="Graph source - either a reference to existing variant or inline graph.",
    )
    streams: int = Field(
        default=1,
        ge=0,
        description="Number of parallel streams for this pipeline.",
        examples=[1, 4, 16],
    )


class PipelineDensitySpec(BaseModel):
    """
    **Per-pipeline configuration for density tests.**

    The pipeline can be specified in two ways:
    - `variant` - Reference to an existing pipeline variant by pipeline_id and variant_id
    - `graph` - Inline pipeline graph provided directly

    Used in DensityTestSpec to describe how total streams are split between
    pipelines based on relative ratios.

    ## Attributes
    - `pipeline` - Graph source (either a reference to existing variant or inline graph; discriminated by 'source' field: \"variant\" or \"graph\")
    - `stream_rate` - Relative share of total streams for this pipeline expressed as percentage (all stream_rate values in the request must sum to 100)

    ### Example (Variant reference)
    ```json
    {
      "pipeline": {
        "source": "variant",
        "pipeline_id": "pipeline-a3f5d9e1",
        "variant_id": "variant-abc123"
      },
      "stream_rate": 50
    }
    ```

    ### Example (Inline graph)
    ```json
    {
      "pipeline": {
        "source": "graph",
        "pipeline_graph": {
          "nodes": [...],
          "edges": [...]
        }
      },
      "stream_rate": 50
    }
    ```
    """

    pipeline: GraphSource = Field(
        ...,
        discriminator="source",
        description="Graph source - either a reference to existing variant or inline graph.",
    )
    stream_rate: int = Field(
        default=100,
        ge=0,
        description="Relative share of total streams for this pipeline (percentage).",
        examples=[50],
    )


class Pipeline(BaseModel):
    """
    **Full pipeline definition exposed by the pipelines API.**

    ## Attributes
    - `id` - Unique pipeline identifier generated by the backend
    - `name` - Logical pipeline name
    - `description` - Human-readable text describing what the pipeline does
    - `source` - Origin of the pipeline (PREDEFINED or USER_CREATED)
    - `tags` - List of tags for categorizing the pipeline
    - `variants` - List of pipeline variants for different hardware targets (each variant has its own pipeline_graph and pipeline_graph_simple)
    - `thumbnail` - Base64-encoded image for pipeline preview (only available for PREDEFINED pipelines with valid thumbnail file; redacted when printing)
    - `created_at` - Creation timestamp as UTC datetime (set by backend only, not modifiable via API)
    - `modified_at` - Last modification timestamp as UTC datetime (updated when pipeline or its variants are modified; set by backend only)

    ### Example
    ```json
    {
      "id": "pipeline-a3f5d9e1",
      "name": "vehicle-detection",
      "description": "Simple vehicle detection pipeline",
      "source": "USER_CREATED",
      "tags": ["detection", "vehicle"],
      "variants": [
        {
          "id": "variant-1",
          "name": "CPU",
          "read_only": false,
          "pipeline_graph": {...},
          "pipeline_graph_simple": {...},
          "created_at": "2026-02-05T14:30:45.123000+00:00",
          "modified_at": "2026-02-05T14:30:45.123000+00:00"
        }
      ],
      "thumbnail": null,
      "created_at": "2026-02-05T14:30:45.123000+00:00",
      "modified_at": "2026-02-05T14:30:45.123000+00:00"
    }
    ```
    """

    id: str
    name: str
    description: str
    source: PipelineSource
    tags: List[str] = Field(
        default=[],
        description="List of tags for categorizing the pipeline.",
    )
    variants: List[Variant] = Field(
        ...,
        min_length=1,
        description="List of pipeline variants for different hardware targets.",
    )
    thumbnail: Optional[str] = Field(
        default=None,
        repr=False,
        description="Base64-encoded thumbnail image. Only for PREDEFINED pipelines. Redacted in logs.",
    )
    created_at: datetime = Field(
        ...,
        description="Creation timestamp as UTC datetime. Set by backend only.",
    )
    modified_at: datetime = Field(
        ...,
        description="Last modification timestamp as UTC datetime. Set by backend only.",
    )


class PipelineDefinition(BaseModel):
    """
    **Input model used to create a new pipeline via the API.**

    ## Attributes
    - `name` - Non-empty pipeline name
    - `description` - Non-empty human-readable text describing what the pipeline does
    - `source` - Pipeline source (for create endpoint this value is overwritten to USER_CREATED)
    - `tags` - List of tags for categorizing the pipeline
    - `variants` - List of pipeline variants for different hardware targets (each variant requires name, pipeline_graph, and pipeline_graph_simple)

    ### Example
    ```json
    {
      "name": "vehicle-detection",
      "description": "Simple vehicle detection pipeline",
      "tags": ["detection", "vehicle"],
      "variants": [
        {
          "name": "CPU",
          "pipeline_graph": {...},
          "pipeline_graph_simple": {...}
        }
      ]
    }
    ```
    """

    name: str = Field(..., min_length=1, description="Non-empty pipeline name.")
    description: str = Field(
        ...,
        min_length=1,
        description="Non-empty human-readable text describing what the pipeline does.",
    )
    source: PipelineSource = PipelineSource.USER_CREATED
    tags: List[str] = Field(
        default=[],
        description="List of tags for categorizing the pipeline.",
    )
    variants: List[VariantCreate] = Field(
        ...,
        min_length=1,
        description="List of pipeline variants for different hardware targets.",
    )


class PipelineUpdate(BaseModel):
    """
    **Partial update model for an existing pipeline.**

    All fields are optional, but at least one must be provided when calling
    the update endpoint. String fields (name, description) must be non-empty
    after trimming whitespace.

    Validation is performed in model_validator to fail fast on invalid input.

    ## Attributes
    - `name` - Optional new pipeline name (non-empty after trim if provided)
    - `description` - Optional new human-readable text describing what the pipeline does (non-empty after trim if provided)
    - `tags` - Optional list of tags (if provided, can be empty)

    ### Example
    ```json
    {
      "description": "Updated pipeline with better preprocessing",
      "tags": ["updated", "v2"]
    }
    ```
    """

    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None

    @model_validator(mode="after")
    def validate_update_fields(self):
        """Ensure at least one field is provided and strings are non-empty after trim."""
        # Check that at least one field is provided
        if self.name is None and self.description is None and self.tags is None:
            raise ValueError(
                "At least one of 'name', 'description', or 'tags' must be provided."
            )

        # Check that string fields are non-empty after trim
        if self.name is not None and self.name.strip() == "":
            raise ValueError("Field 'name' must not be empty.")

        if self.description is not None and self.description.strip() == "":
            raise ValueError("Field 'description' must not be empty.")

        return self


class PipelineValidation(BaseModel):
    """
    **Request body for pipeline validation.**

    ## Attributes
    - `pipeline_graph` - Structured graph representation of the pipeline
    - `parameters` - Optional parameter set for validation (e.g., `{"max-runtime": 10}`)

    ### Example
    ```json
    {
      "pipeline_graph": {
        "nodes": [...],
        "edges": [...]
      },
      "parameters": {
        "max-runtime": 10
      }
    }
    ```
    """

    pipeline_graph: PipelineGraph
    parameters: Optional[Dict[str, Any]] = Field(
        default=None, examples=[{"max-runtime": 10}]
    )


class ValidationJobResponse(BaseModel):
    """
    **Simple envelope with a new validation job identifier.**

    Used as response body when a validation job is created.

    ## Attributes
    - `job_id` - Identifier of the created validation job

    ### Example
    ```json
    {
      "job_id": "val001"
    }
    ```
    """

    job_id: str = Field(
        ...,
        description="Identifier of the created validation job.",
        examples=["val001"],
    )


class PipelineRequestOptimize(BaseModel):
    """
    **Request body for starting a pipeline optimization job.**

    ## Attributes
    - `type` - Optimization type: `preprocess` (run only preprocessing) or `optimize` (run full optimization with search/sampling)
    - `parameters` - Optional dictionary with optimizer-specific settings

    ### Example
    ```json
    {
      "type": "optimize",
      "parameters": {
        "search_duration": 300,
        "sample_duration": 10
      }
    }
    ```
    """

    type: OptimizationType
    parameters: Optional[Dict[str, Any]]


class OutputMode(str, Enum):
    """
    **Mode for pipeline output generation.**

    ## Values
    - `DISABLED` - No output generation (default)
    - `FILE` - Save output to file
    - `LIVE_STREAM` - Stream output live to media server

    ### Example
    ```json
    "disabled"
    ```
    """

    DISABLED = "disabled"
    FILE = "file"
    LIVE_STREAM = "live_stream"


class ExecutionConfig(BaseModel):
    """
    **Configuration for pipeline execution behavior.**

    This configuration controls both output generation and runtime limits
    for test pipelines.

    ## Attributes
    - `output_mode` - Mode for pipeline output generation:
      - `disabled` - No output (fakesink remains, default)
      - `file` - Save video to file (only allowed with max_runtime=0)
      - `live_stream` - Stream output live to media server
    - `max_runtime` - Maximum runtime in seconds for the pipeline:
      - 0: Run until natural completion (EOS), no time limit (default)
      - >0: Stop pipeline after this duration, with looping if EOS comes early (only allowed with output_mode=disabled or output_mode=live_stream)
      - <0: Not allowed (will be rejected)

    ### Example (disabled output, no runtime limit)
    ```json
    {
      "output_mode": "disabled",
      "max_runtime": 0
    }
    ```

    ### Example (save to file, run until EOS)
    ```json
    {
      "output_mode": "file",
      "max_runtime": 0
    }
    ```

    ### Example (live streaming with 60 second limit)
    ```json
    {
      "output_mode": "live_stream",
      "max_runtime": 60
    }
    ```
    """

    output_mode: OutputMode = Field(
        default=OutputMode.DISABLED,
        description="Mode for pipeline output generation.",
    )
    max_runtime: float = Field(
        default=0.0,
        ge=0.0,
        description="Maximum runtime in seconds (0 = run until EOS, >0 = time limit with looping for live_stream/disabled).",
    )


class PerformanceTestSpec(BaseModel):
    """
    **Request body for starting a performance test.**

    ## Attributes
    - `pipeline_performance_specs` - List of pipelines and their stream counts
    - `execution_config` - Configuration for output generation and runtime limits

    ### Example
    ```json
    {
      "pipeline_performance_specs": [
        {
          "pipeline": {
            "source": "variant",
            "pipeline_id": "pipeline-a3f5d9e1",
            "variant_id": "variant-abc123"
          },
          "streams": 4
        }
      ],
      "execution_config": {
        "output_mode": "disabled",
        "max_runtime": 0
      }
    }
    ```
    """

    pipeline_performance_specs: list[PipelinePerformanceSpec] = Field(
        ...,
        description="List of pipelines with number of streams for each.",
        examples=[
            [
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-a3f5d9e1",
                        "variant_id": "variant-abc123",
                    },
                    "streams": 4,
                },
            ]
        ],
    )
    execution_config: ExecutionConfig = Field(
        default=ExecutionConfig(),
        description="Execution configuration for output and runtime.",
        examples=[{"output_mode": "disabled", "max_runtime": 0}],
    )


class DensityTestSpec(BaseModel):
    """
    **Request body for starting a density test.**

    ## Attributes
    - `fps_floor` - Minimum acceptable FPS per stream
    - `pipeline_density_specs` - List of pipelines with relative stream_rate ratios
    - `execution_config` - Configuration for output generation and runtime limits

    ### Example
    ```json
    {
      "fps_floor": 30,
      "pipeline_density_specs": [
        {
          "pipeline": {
            "source": "variant",
            "pipeline_id": "pipeline-a3f5d9e1",
            "variant_id": "variant-abc123"
          },
          "stream_rate": 50
        },
        {
          "pipeline": {
            "source": "variant",
            "pipeline_id": "pipeline-b4c6e2f8",
            "variant_id": "variant-def456"
          },
          "stream_rate": 50
        }
      ],
      "execution_config": {
        "output_mode": "disabled",
        "max_runtime": 0
      }
    }
    ```
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
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-a3f5d9e1",
                        "variant_id": "variant-abc123",
                    },
                    "stream_rate": 50,
                },
                {
                    "pipeline": {
                        "source": "variant",
                        "pipeline_id": "pipeline-b7c2e114",
                        "variant_id": "variant-def456",
                    },
                    "stream_rate": 50,
                },
            ]
        ],
    )
    execution_config: ExecutionConfig = Field(
        default=ExecutionConfig(),
        description="Execution configuration for output and runtime.",
        examples=[{"output_mode": "disabled", "max_runtime": 0}],
    )


class TestJobResponse(BaseModel):
    """
    **Simple envelope with a new test job identifier.**

    Used as response body when performance or density test job is created.

    ## Attributes
    - `job_id` - Identifier of the created test job

    ### Example
    ```json
    {
      "job_id": "job123"
    }
    ```
    """

    job_id: str = Field(
        ...,
        description="Identifier of the created test job.",
        examples=["job123"],
    )


class TestsJobStatus(BaseModel):
    """
    **Base status fields shared by performance and density jobs.**

    ## Attributes
    - `id` - Job identifier
    - `start_time` - Start time in milliseconds since epoch
    - `elapsed_time` - Elapsed time in milliseconds
    - `state` - Current job state
    - `details` - List of human-readable messages explaining why the job reached its current state. Cleared when the job transitions to a new state, then new entries are appended. Examples: ["Pipeline completed successfully"], ["Cancelled by user"], ["Cancelled by user", "Pipeline exited with non-zero exit code: 1"], ["Pipeline runtime error: ..."]
    - `total_fps` - Total FPS across all streams (may be null)
    - `per_stream_fps` - Average FPS per stream (may be null)
    - `total_streams` - Number of active streams (may be null)
    - `streams_per_pipeline` - List of pipeline IDs with stream counts (each entry contains: id (pipeline identifier: variant path or synthetic graph ID) and streams (number of streams for this pipeline))
    - `video_output_paths` - Mapping from pipeline id to list of output file paths (keys use the same id format as streams_per_pipeline entries)

    > **Note:** live_stream_urls is intentionally not included here because density tests
    > do not support live-streaming. PerformanceJobStatus adds this field separately.
    """

    id: str
    start_time: int
    elapsed_time: int
    state: TestJobState
    details: list[str]
    total_fps: float | None
    per_stream_fps: float | None
    total_streams: int | None
    streams_per_pipeline: list[PipelineStreamSpec] | None
    video_output_paths: dict[str, list[str]] | None


class PerformanceJobStatus(TestsJobStatus):
    """
    **Status of a performance test job.**

    Inherits all fields from TestsJobStatus and adds live_stream_urls
    for live-streaming output mode support.

    ## Attributes
    - *Inherited from TestsJobStatus* - id, start_time, elapsed_time, state, details, total_fps, per_stream_fps, total_streams, streams_per_pipeline, video_output_paths
    - `live_stream_urls` - Mapping from pipeline id to live stream URL when using live_stream output mode (keys use the same id format as streams_per_pipeline entries; only available for performance tests)
    """

    live_stream_urls: Optional[Dict[str, str]]


class DensityJobStatus(TestsJobStatus):
    """
    **Status of a density test job.**

    Inherits all fields from TestsJobStatus without changes.
    Does not include live_stream_urls because density tests do not support
    live-streaming output mode (only disabled or file modes are allowed).

    ## Attributes
    - *Inherited from TestsJobStatus* - id, start_time, elapsed_time, state, details, total_fps, per_stream_fps, total_streams, streams_per_pipeline, video_output_paths
    """

    pass


class PerformanceJobSummary(BaseModel):
    """
    **Short summary for a performance test job.**

    ## Attributes
    - `id` - Job identifier
    - `request` - Original PerformanceTestSpec used to start the job (stored as dict and validated on output)

    ### Example
    ```json
    {
      "id": "job123",
      "request": {
        "pipeline_performance_specs": [...],
        "execution_config": {...}
      }
    }
    ```
    """

    id: str
    request: Dict[str, Any]


class DensityJobSummary(BaseModel):
    """
    **Short summary for a density test job.**

    ## Attributes
    - `id` - Job identifier
    - `request` - Original DensityTestSpec used to start the job (stored as dict and validated on output)

    ### Example
    ```json
    {
      "id": "job456",
      "request": {
        "fps_floor": 30,
        "pipeline_density_specs": [...],
        "execution_config": {...}
      }
    }
    ```
    """

    id: str
    request: Dict[str, Any]


class OptimizationJobResponse(BaseModel):
    """
    **Simple envelope with a new optimization job identifier.**

    Used as response body when an optimization job is created.

    ## Attributes
    - `job_id` - Identifier of the created optimization job

    ### Example
    ```json
    {
      "job_id": "opt789"
    }
    ```
    """

    job_id: str = Field(
        ...,
        description="Identifier of the created optimization job.",
        examples=["opt789"],
    )


class OptimizationJobStatus(BaseModel):
    """
    **Detailed status of an optimization job.**

    ## Attributes
    - `id` - Job identifier
    - `type` - Optimization type (PREPROCESS or OPTIMIZE)
    - `start_time` - Start time in milliseconds since epoch
    - `elapsed_time` - Elapsed time in milliseconds
    - `state` - Current job state
    - `details` - List of human-readable messages explaining why the job reached its current state. Cleared when the job transitions to a new state, then new entries are appended. Cancellation always results in FAILED state. Examples: ["Optimization completed successfully"], ["Cancelled by user"], ["Optimization failed: ..."]
    - `total_fps` - Measured FPS for optimized pipeline (for OPTIMIZE)
    - `original_pipeline_graph` - Original pipeline graph (advanced view) before optimization
    - `original_pipeline_graph_simple` - Original pipeline graph (simple view) before optimization
    - `optimized_pipeline_graph` - Optimized pipeline graph (advanced view) if available
    - `optimized_pipeline_graph_simple` - Optimized pipeline graph (simple view) if available
    - `original_pipeline_description` - Original GStreamer pipeline string before optimization
    - `optimized_pipeline_description` - Optimized GStreamer pipeline string after optimization (if any)
    """

    id: str
    type: OptimizationType | None
    start_time: int
    elapsed_time: int
    state: OptimizationJobState
    details: list[str]
    total_fps: float | None
    original_pipeline_graph: PipelineGraph
    original_pipeline_graph_simple: PipelineGraph
    optimized_pipeline_graph: PipelineGraph | None
    optimized_pipeline_graph_simple: PipelineGraph | None
    original_pipeline_description: str
    optimized_pipeline_description: str | None


class OptimizationJobSummary(BaseModel):
    """
    **Short summary for an optimization job.**

    ## Attributes
    - `id` - Job identifier
    - `request` - Original PipelineRequestOptimize used to start the job

    ### Example
    ```json
    {
      "id": "opt789",
      "request": {
        "type": "optimize",
        "parameters": {}
      }
    }
    ```
    """

    id: str
    request: PipelineRequestOptimize


class ValidationJobStatus(BaseModel):
    """
    **Detailed status of a validation job.**

    ## Attributes
    - `id` - Job identifier
    - `start_time` - Start time in milliseconds since epoch
    - `elapsed_time` - Elapsed time in milliseconds
    - `state` - Current validation job state
    - `details` - List of human-readable messages explaining why the job reached its current state. Cleared when the job transitions to a new state, then new entries are appended. Examples: ["Pipeline is valid"], ["Pipeline validation failed: no element foo"]
    - `is_valid` - Final validation result (true/false) when completed
    """

    id: str
    start_time: int
    elapsed_time: int
    state: ValidationJobState
    details: list[str]
    is_valid: bool | None


class ValidationJobSummary(BaseModel):
    """
    **Short summary for a validation job.**

    ## Attributes
    - `id` - Job identifier
    - `request` - Original PipelineValidation request

    ### Example
    ```json
    {
      "id": "val001",
      "request": {
        "pipeline_graph": {...},
        "parameters": {}
      }
    }
    ```
    """

    id: str
    request: PipelineValidation


class Device(BaseModel):
    """
    **Hardware device description used by multiple APIs.**

    This model is a simplified view of the device information returned
    by the runtime (e.g., OpenVINO) and is suitable for UI consumption.

    ## Attributes
    - `device_name` - Short identifier used when selecting the device (e.g., "CPU", "GPU", "GPU.0", "NPU")
    - `full_device_name` - Human readable device name (CPU/GPU/NPU model)
    - `device_type` - High level device type (INTEGRATED or DISCRETE)
    - `device_family` - Hardware family (CPU, GPU, NPU)
    - `gpu_id` - Optional GPU index when applicable; null for non-GPU devices

    ### Example
    ```json
    {
      "device_name": "GPU.0",
      "full_device_name": "Intel(R) Arc(TM) Graphics (iGPU) (GPU.0)",
      "device_type": "INTEGRATED",
      "device_family": "GPU",
      "gpu_id": 0
    }
    ```
    """

    device_name: str
    full_device_name: str
    device_type: DeviceType
    device_family: DeviceFamily
    gpu_id: Optional[int]


class Model(BaseModel):
    """
    **Description of a single model exposed by the models API.**

    ## Attributes
    - `name` - Internal model identifier used by the backend
    - `display_name` - Human readable model name suitable for UI
    - `category` - Logical model category (classification, detection), or null when the type from configuration is unknown or unsupported
    - `precision` - Model precision string (e.g., "FP32", "INT8"), or null when not specified

    ### Example
    ```json
    {
      "name": "vehicle-detection-0202",
      "display_name": "Vehicle Detection",
      "category": "detection",
      "precision": "FP32"
    }
    ```
    """

    name: str
    display_name: str
    category: Optional[ModelCategory]
    precision: Optional[str]


class MetricSample(BaseModel):
    """
    **Single metric sample used in streaming metrics APIs.**

    ## Attributes
    - `name` - Metric name (e.g., "total_fps" or "cpu_usage")
    - `description` - Short human-readable description of the metric
    - `timestamp` - Unix timestamp in milliseconds when the sample was taken
    - `value` - Numeric value of the metric

    ### Example
    ```json
    {
      "name": "total_fps",
      "description": "Total FPS over all streams",
      "timestamp": 1715000000000,
      "value": 512.4
    }
    ```
    """

    name: str
    description: str
    timestamp: int
    value: float


class Video(BaseModel):
    """
    **Metadata for a single input video file.**

    ## Attributes
    - `filename` - Base name of the video file located under RECORDINGS_PATH
    - `width` - Frame width in pixels
    - `height` - Frame height in pixels
    - `fps` - Frames per second for the stream
    - `frame_count` - Total number of frames in the file
    - `codec` - Normalized codec name (e.g., "h264" or "h265")
    - `duration` - Approximate duration in seconds

    ### Example
    ```json
    {
      "filename": "traffic_1080p_h264.mp4",
      "width": 1920,
      "height": 1080,
      "fps": 30.0,
      "frame_count": 900,
      "codec": "h264",
      "duration": 30.0
    }
    ```
    """

    filename: str
    width: int
    height: int
    fps: float
    frame_count: int
    codec: str
    duration: float


class CameraDetails(BaseModel):
    """
    **Base class for camera-specific details.**

    This is an abstract base class. Use USBCameraDetails or NetworkCameraDetails
    for specific camera types.
    """

    pass


class V4L2FormatSize(BaseModel):
    """
    **Single supported resolution with available frame rates for a V4L2 format.**

    ## Attributes
    - `width` - Resolution width in pixels
    - `height` - Resolution height in pixels
    - `fps_list` - List of available frame rates for this resolution
    """

    width: int
    height: int
    fps_list: List[float]


class V4L2Format(BaseModel):
    """
    **Single V4L2 pixel format with all supported resolutions and frame rates.**

    ## Attributes
    - `fourcc` - Four-character code identifying the pixel format (e.g., "YUYV", "MJPG")
    - `sizes` - List of supported resolutions with their available frame rates
    """

    fourcc: str
    sizes: List[V4L2FormatSize]


class V4L2BestCapture(BaseModel):
    """
    **Best capture configuration selected from available V4L2 formats.**

    ## Attributes
    - `fourcc` - Selected pixel format four-character code
    - `width` - Selected resolution width in pixels
    - `height` - Selected resolution height in pixels
    - `fps` - Selected frame rate
    """

    fourcc: str
    width: int
    height: int
    fps: float


class USBCameraDetails(CameraDetails):
    """
    **USB camera details including the best capture configuration.**

    Selected by the scoring algorithm from available V4L2 formats.

    ## Attributes
    - `device_path` - System device path (e.g., /dev/video0)
    - `best_capture` - Best capture configuration selected by scoring algorithm (optional)
    """

    device_path: str
    best_capture: Optional[V4L2BestCapture] = None


class NetworkCameraDetails(CameraDetails):
    """
    **Network camera details including ONVIF profiles and best profile.**

    The best profile is selected by the scoring algorithm.

    ## Attributes
    - `ip` - IP address of the camera
    - `port` - Port number for ONVIF communication
    - `profiles` - List of ONVIF profiles available on this camera (populated after authentication)
    - `best_profile` - Best profile selected by scoring algorithm (optional)
    """

    ip: str
    port: int
    profiles: list["CameraProfileInfo"]
    best_profile: Optional["CameraProfileInfo"] = None


class Camera(BaseModel):
    """
    **Camera device information supporting both USB and network cameras.**

    Common attributes apply to all camera types. Type-specific details are stored
    in the details field which contains either USBCameraDetails or NetworkCameraDetails.

    ## Attributes
    - `device_id` - Unique identifier for the camera
    - `device_name` - Human-readable camera name
    - `device_type` - Type of camera (USB or NETWORK)
    - `details` - Type-specific camera details (USBCameraDetails for USB, NetworkCameraDetails for NETWORK)

    ### Example (USB Camera)
    ```json
    {
      "device_id": "usb-camera-0",
      "device_name": "Integrated Camera",
      "device_type": "USB",
      "details": {
        "device_path": "/dev/video0",
        "best_capture": {
          "fourcc": "YUYV",
          "width": 1920,
          "height": 1080,
          "fps": 30
        }
      }
    }
    ```

    ### Example (Network Camera)
    ```json
    {
      "device_id": "network-camera-192.168.1.100-80",
      "device_name": "ONVIF Camera 192.168.1.100",
      "device_type": "NETWORK",
      "details": {
        "ip": "192.168.1.100",
        "port": 80,
        "profiles": [
          {
            "name": "Profile_1",
            "rtsp_url": "rtsp://192.168.1.100:554/stream1",
            "resolution": "1920x1080",
            "encoding": "H264",
            "framerate": 30,
            "bitrate": 4096
          }
        ],
        "best_profile": {
          "name": "Profile_1",
          "rtsp_url": "rtsp://192.168.1.100:554/stream1",
          "resolution": "1920x1080",
          "encoding": "H264",
          "framerate": 30,
          "bitrate": 4096
        }
      }
    }
    ```
    """

    device_id: str
    device_name: str
    device_type: CameraType
    details: Union[USBCameraDetails, NetworkCameraDetails]


class CameraProfilesRequest(BaseModel):
    """
    **Request model for camera profile retrieval.**

    Camera ID is provided in the path parameter.

    ## Attributes
    - `username` - Username for ONVIF authentication
    - `password` - Password for ONVIF authentication

    ### Example
    ```json
    {
      "username": "admin",
      "password": "password123"
    }
    ```
    """

    username: str
    password: str


class CameraProfileInfo(BaseModel):
    """
    **Detailed ONVIF camera profile information.**

    ## Attributes
    - `name` - Profile name
    - `rtsp_url` - RTSP stream URL
    - `resolution` - Video resolution (e.g., "1920x1080")
    - `encoding` - Video encoding format (e.g., "H264", "MPEG4")
    - `framerate` - Frame rate limit
    - `bitrate` - Bitrate limit

    ### Example
    ```json
    {
      "name": "Profile_1",
      "rtsp_url": "rtsp://192.168.1.100:554/stream1",
      "resolution": "1920x1080",
      "encoding": "H264",
      "framerate": 30,
      "bitrate": 4096
    }
    ```
    """

    name: str
    rtsp_url: Optional[str] = None
    resolution: Optional[str] = None
    encoding: Optional[str] = None
    framerate: Optional[int] = None
    bitrate: Optional[int] = None


class CameraAuthResponse(BaseModel):
    """
    **Response model for camera authentication attempt.**

    Returns the authenticated camera with populated ONVIF profiles.
    After successful authentication, the camera's profile list is updated
    with all available ONVIF profiles from the device.

    ## Attributes
    - `camera` - Camera object with updated profile list (includes all ONVIF profiles available on the device)

    ### Example
    ```json
    {
      "camera": {
        "device_id": "network-camera-192.168.1.100-80",
        "device_name": "ONVIF Camera 192.168.1.100",
        "device_type": "NETWORK",
        "details": {
          "ip": "192.168.1.100",
          "port": 80,
          "profiles": [...]
        }
      }
    }
    ```
    """

    camera: Camera = Field(
        ...,
        description="Camera object with populated ONVIF profiles after successful authentication.",
    )
