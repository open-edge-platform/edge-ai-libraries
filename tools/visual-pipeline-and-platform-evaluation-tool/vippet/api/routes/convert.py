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
    Convert a GStreamer-like pipeline description string into structured pipeline graphs.

    This endpoint parses the textual pipeline description, validates it and builds both
    an advanced view (with all technical elements) and a simple view (with only meaningful
    elements like sources, inference nodes, and sinks).

    Args:
        request: PipelineDescription body containing the ``pipeline_description`` string
            to be converted.

    Returns:
        PipelineGraphResponse: On success (HTTP 200) both graph representations:
            - pipeline_graph: Advanced view with all elements including technical plumbing
            - pipeline_graph_simple: Simplified view with only visible elements
        MessageResponse: On client or server error (HTTP 400 or 500) a message describing
            the failure.

    Success criteria:
        * The pipeline description is syntactically correct and all referenced models
          and input videos can be resolved.
        * The description can be mapped to a non-empty, acyclic graph with at least one
          start node.
        * Simple view can be generated from the advanced view.

    Failure cases:
        * 400 – invalid or unparsable pipeline description (syntax error, unsupported
          token, missing required data, unknown model/video).
        * 500 – unexpected internal error while converting the description.

    Request example:
        .. code-block:: json

            {
              "pipeline_description": "videotestsrc ! videoconvert ! autovideosink"
            }

    Successful response example (200):
        .. code-block:: json

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

    Error response example (400):
        .. code-block:: json

            {
              "message": "Invalid pipeline description: Unrecognized token in pipeline description: '??'"
            }
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
    Convert a structured pipeline graph into a GStreamer-like pipeline description string.

    This endpoint validates the input graph (advanced view) and serializes its nodes
    and edges back into a single pipeline description line. The input should be an
    advanced view graph containing all technical elements.

    Args:
        request: PipelineGraph body containing nodes and edges that define the pipeline
            (advanced view expected).

    Returns:
        PipelineDescription: On success (HTTP 200) a textual ``pipeline_description``
            that can be used to run the pipeline.
        MessageResponse: On client or server error (HTTP 400 or 500) a message describing
            the failure.

    Success criteria:
        * The graph is non-empty and contains at least one start node.
        * The graph is a valid directed acyclic graph for a pipeline (no unresolved
          references, no fully circular graph).
        * All model and input video display names can be mapped back to real paths.

    Failure cases:
        * 400 – invalid graph structure (no start nodes, circular graph, missing nodes
          for edges, unknown model/video, or empty graph).
        * 500 – unexpected internal error while converting the graph.

    Request example:
        .. code-block:: json

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

    Successful response example (200):
        .. code-block:: json

            {
              "pipeline_description": "videotestsrc ! videoconvert ! autovideosink"
            }

    Error response example (400):
        .. code-block:: json

            {
              "message": "Invalid graph: circular graph detected or no start nodes found"
            }
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
