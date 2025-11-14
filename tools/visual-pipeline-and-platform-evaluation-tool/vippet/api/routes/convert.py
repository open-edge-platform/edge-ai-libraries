from graph import Graph
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.api_schemas import PipelineGraph, PipelineDescription, MessageResponse

router = APIRouter()


@router.post(
    "/to-graph",
    operation_id="to_graph",
    summary="Convert pipeline description to pipeline graph",
    responses={
        200: {"description": "Conversion successful", "model": PipelineGraph},
        400: {"description": "Invalid pipeline description", "model": MessageResponse},
        500: {"description": "Internal server error", "model": MessageResponse},
    },
)
def to_graph(request: PipelineDescription):
    try:
        graph = Graph.from_pipeline_description(request.pipeline_description)
        return PipelineGraph.model_validate(graph.to_dict())
    except ValueError as e:
        return JSONResponse(
            content=MessageResponse(
                message=f"Invalid pipeline description: {str(e)}"
            ).model_dump(),
            status_code=400,
        )
    except Exception as e:
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
    try:
        graph = Graph.from_dict(request.model_dump())
        pipeline_description = graph.to_pipeline_description()
        return PipelineDescription(pipeline_description=pipeline_description)
    except ValueError as e:
        return JSONResponse(
            content=MessageResponse(message=f"Invalid graph: {str(e)}").model_dump(),
            status_code=400,
        )
    except Exception as e:
        return JSONResponse(
            content=MessageResponse(message=str(e)).model_dump(), status_code=500
        )
