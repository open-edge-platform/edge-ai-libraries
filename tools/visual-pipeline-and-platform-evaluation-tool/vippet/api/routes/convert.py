import logging

from graph import Graph

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.api_schemas import (
    MessageResponse,
    PipelineDescription,
    PipelineGraph,
    PipelineGraphResponse,
)

router = APIRouter()
logger = logging.getLogger("api.routes.convert")


@router.post(
    "/to-graph",
    operation_id="to_graph",
    summary="Convert pipeline description to pipeline graphs (both views)",
    responses={
        200: {
            "description": "Conversion successful",
            "model": PipelineGraphResponse,
        },
        400: {"description": "Invalid pipeline description", "model": MessageResponse},
        500: {"description": "Internal server error", "model": MessageResponse},
    },
)
def to_graph(request: PipelineDescription):
    """
    **Convert GStreamer-like pipeline description into structured pipeline graphs.**

    ## Operation
    Parses the textual pipeline description, validates it, and builds both an advanced view
    (with all technical elements) and a simple view (with only meaningful elements).

    1. Parse pipeline description string
    2. Validate syntax and resolve references (models, videos)
    3. Build advanced graph with all elements including technical plumbing
    4. Generate simplified view with only visible elements (sources, inference, sinks)
    5. Return both graph representations

    ## Request Body
    **`PipelineDescription`** with:
    - `pipeline_description` *(required)* - GStreamer-like pipeline string

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `PipelineGraphResponse` with both `pipeline_graph` and `pipeline_graph_simple` |
    | 400 | `MessageResponse` - Invalid or unparsable pipeline description |
    | 500 | `MessageResponse` - Unexpected internal error |

    ## Conditions

    ### ✅ Success
    - Pipeline description is syntactically correct
    - All referenced models and input videos can be resolved
    - Description maps to non-empty, acyclic graph with at least one start node
    - Simple view can be generated from advanced view

    ### ❌ Failure
    - Invalid or unparsable pipeline description (syntax error, unsupported token) → 400
    - Missing required data, unknown model/video → 400
    - Unexpected internal error → 500

    ## Examples

    ### Request
    ```json
    {
      "pipeline_description": "videotestsrc ! videoconvert ! autovideosink"
    }
    ```

    ### Success Response (200)
    ```json
    {
      "pipeline_graph": {
        "nodes": [
          {"id": "0", "type": "videotestsrc", "data": {}},
          {"id": "1", "type": "videoconvert", "data": {}},
          {"id": "2", "type": "autovideosink", "data": {}}
        ],
        "edges": [
          {"id": "0", "source": "0", "target": "1"},
          {"id": "1", "source": "1", "target": "2"}
        ]
      },
      "pipeline_graph_simple": {
        "nodes": [
          {"id": "0", "type": "videotestsrc", "data": {}},
          {"id": "2", "type": "autovideosink", "data": {}}
        ],
        "edges": [
          {"id": "0", "source": "0", "target": "2"}
        ]
      }
    }
    ```

    ### Error Response (400)
    ```json
    {
      "message": "Invalid pipeline description: Unrecognized token in pipeline description: '??'"
    }
    ```
    """
    try:
        # Parse into advanced graph
        graph = Graph.from_pipeline_description(request.pipeline_description)
        pipeline_graph = PipelineGraph.model_validate(graph.to_dict())

        # Generate simple view
        simple_graph = graph.to_simple_view()
        pipeline_graph_simple = PipelineGraph.model_validate(simple_graph.to_dict())

        return PipelineGraphResponse(
            pipeline_graph=pipeline_graph,
            pipeline_graph_simple=pipeline_graph_simple,
        )
    except ValueError as e:
        logger.error("Invalid pipeline description received: %s", e)
        return JSONResponse(
            content=MessageResponse(
                message=f"Invalid pipeline description: {str(e)}"
            ).model_dump(),
            status_code=400,
        )
    except Exception as e:
        logger.error("Failed to convert pipeline description to graph", exc_info=True)
        return JSONResponse(
            content=MessageResponse(message=str(e)).model_dump(),
            status_code=500,
        )


@router.post(
    "/to-description",
    operation_id="to_description",
    summary="Convert pipeline graph to pipeline description",
    responses={
        200: {"description": "Conversion successful", "model": PipelineDescription},
        400: {"description": "Invalid graph", "model": MessageResponse},
        500: {"description": "Internal server error", "model": MessageResponse},
    },
)
def to_description(request: PipelineGraph):
    """
    **Convert structured pipeline graph into GStreamer-like pipeline description string.**

    ## Operation
    Validates the input graph (advanced view) and serializes its nodes and edges
    back into a single pipeline description line.

    1. Validate input graph structure
    2. Check for start nodes and acyclic structure
    3. Map model and video display names back to real paths
    4. Serialize nodes and edges into pipeline description string

    > **Note:** The input should be an advanced view graph containing all technical elements.

    ## Request Body
    **`PipelineGraph`** with:
    - `nodes` *(required)* - Array of pipeline nodes (advanced view expected)
    - `edges` *(required)* - Array of edges connecting the nodes

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 200 | `PipelineDescription` with textual pipeline description |
    | 400 | `MessageResponse` - Invalid graph structure |
    | 500 | `MessageResponse` - Unexpected internal error |

    ## Conditions

    ### ✅ Success
    - Graph is non-empty and contains at least one start node
    - Graph is a valid directed acyclic graph (no unresolved references, no circular graph)
    - All model and input video display names can be mapped back to real paths

    ### ❌ Failure
    - Invalid graph structure (no start nodes, circular graph, missing nodes) → 400
    - Unknown model/video or empty graph → 400
    - Unexpected internal error → 500

    ## Examples

    ### Request
    ```json
    {
      "nodes": [
        {"id": "0", "type": "videotestsrc", "data": {}},
        {"id": "1", "type": "videoconvert", "data": {}},
        {"id": "2", "type": "autovideosink", "data": {}}
      ],
      "edges": [
        {"id": "0", "source": "0", "target": "1"},
        {"id": "1", "source": "1", "target": "2"}
      ]
    }
    ```

    ### Success Response (200)
    ```json
    {
      "pipeline_description": "videotestsrc ! videoconvert ! autovideosink"
    }
    ```

    ### Error Response (400)
    ```json
    {
      "message": "Invalid graph: circular graph detected or no start nodes found"
    }
    ```
    """
    try:
        graph = Graph.from_dict(request.model_dump())
        pipeline_description = graph.to_pipeline_description()
        return PipelineDescription(pipeline_description=pipeline_description)
    except ValueError as e:
        logger.error("Invalid pipeline graph received: %s", e)
        return JSONResponse(
            content=MessageResponse(message=f"Invalid graph: {str(e)}").model_dump(),
            status_code=400,
        )
    except Exception as e:
        logger.error("Failed to convert pipeline graph to description", exc_info=True)
        return JSONResponse(
            content=MessageResponse(message=str(e)).model_dump(), status_code=500
        )
