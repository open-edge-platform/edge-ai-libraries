import tempfile
from typing import List
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from managers.pipeline_manager import PipelineManager
from managers.instance_manager import InstanceManager

TEMP_DIR = tempfile.gettempdir()

router = APIRouter()
pipeline_manager = PipelineManager()
instance_manager = InstanceManager()


@router.get("", operation_id="get_pipelines", response_model=List[schemas.Pipeline])
def get_pipelines():
    return pipeline_manager.get_pipelines()


@router.post(
    "",
    operation_id="create_pipeline",
    status_code=201,
    responses={
        201: {
            "description": "Pipeline created",
            "headers": {
                "Location": {
                    "description": "URL of the created pipeline",
                    "schema": {"type": "string"},
                }
            },
            "content": {
                "application/json": {"example": {"message": "Pipeline created"}}
            },
        },
        500: {"description": "Internal server error"},
    },
)
def create_pipeline(body: schemas.PipelineDefinition):
    """Create a custom pipeline from a launch string."""
    # TODO: Validate the launch string
    try:
        pipeline_manager.add_pipeline(body)

        location = f"/pipelines/{body.name}/{body.version}"
        return JSONResponse(
            content={"message": "Pipeline created"},
            status_code=201,
            headers={"Location": location},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create pipeline: {str(e)}"
        )


@router.post(
    "/validate",
    operation_id="validate_pipeline",
    status_code=200,
    responses={
        200: {"description": "Pipeline is valid"},
        400: {"description": "Invalid launch string"},
    },
)
def validate_pipeline(body: schemas.PipelineValidation):
    """Validate launch string pipeline."""
    # TODO: Implement actual validation logic
    return JSONResponse(content={"message": "Pipeline valid"}, status_code=200)


@router.get(
    "/status",
    operation_id="get_pipeline_statuses",
    response_model=List[schemas.PipelineInstanceStatus],
)
def get_pipeline_statuses():
    """Get status of all pipeline instances."""
    return instance_manager.get_all_instance_statuses()


@router.get(
    "/{instance_id}",
    operation_id="get_pipeline_instance_summary",
    response_model=schemas.PipelineInstanceSummary,
)
def get_instance_summary(instance_id: str):
    """Get summary of a specific pipeline instance."""
    summary = instance_manager.get_instance_summary(instance_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    return summary


@router.get(
    "/{instance_id}/status",
    operation_id="get_pipeline_instance_status",
    response_model=schemas.PipelineInstanceStatus,
)
def get_pipeline_instance_status(instance_id: str):
    """Get status of a specific pipeline instance."""
    status = instance_manager.get_instance_status(instance_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    return status


@router.get(
    "/{name}/{version}", operation_id="get_pipeline", response_model=schemas.Pipeline
)
def get_pipeline(name: str, version: str):
    try:
        return pipeline_manager.get_pipeline_by_name_and_version(name, version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post(
    "/{name}/{version}",
    operation_id="run_pipeline",
    responses={
        202: {
            "description": "Pipeline execution started",
            "content": {
                "application/json": {"example": {"instance_id": "a1b2c3d4e5f6"}}
            },
        },
    },
)
def run_pipeline(name: str, version: str, body: schemas.PipelineRequestRun):
    """Run a pipeline."""
    instance_id = instance_manager.run_pipeline(name, version, body)
    return JSONResponse(content={"instance_id": instance_id}, status_code=202)


@router.post("/{name}/{version}/benchmark", operation_id="benchmark_pipeline")
def benchmark_pipeline(name: str, version: str, body: schemas.PipelineRequestBenchmark):
    """Benchmark a pipeline."""
    benchmark_id = instance_manager.benchmark_pipeline(name, version, body)
    return JSONResponse(content={"benchmark_id": benchmark_id}, status_code=202)


@router.post("/{name}/{version}/optimize", operation_id="optimize_pipeline")
def optimize_pipeline(
    name: str, version: str, request: schemas.PipelineRequestOptimize
):
    return {"message": "Optimization started"}


@router.delete(
    "/{name}/{version}",
    operation_id="delete_pipeline",
    status_code=200,
    responses={
        200: {"description": "Pipeline deleted"},
        400: {"description": "Cannot delete pipeline"},
    },
)
def delete_pipeline(name: str, version: str):
    return {"message": "Pipeline deleted"}


@router.delete(
    "/{instance_id}",
    operation_id="stop_pipeline_instance",
    response_model=List[schemas.PipelineInstanceStatus],
)
def stop_pipeline_instance(instance_id: str):
    return []
