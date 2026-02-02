"""Router for Geti workspace related endpoints"""
# pylint: disable=broad-exception-caught
from typing import List, Annotated
from fastapi import APIRouter, Response, status, Depends
from fastapi.responses import PlainTextResponse
from managers.mlflow_manager import MLflowManager
from managers.geti_sdk import GetiSdk
from models.project import ProjectOut
from models.model_identifiers import ModelIdentifiersIn
from utils.logging_config import logger
from utils.app_utils import get_exception_response, validate_resource_id, ResourceType

router = APIRouter()

ProjectIDDep = Annotated[str, Depends(validate_resource_id(ResourceType.PROJECT))]

@router.get("/projects",
         summary="Get projects in a remote Intel® Geti workspace",
         tags=["projects"],
         response_model=List[ProjectOut])
def get_projects():
    """Get projects in a remote Intel® Geti workspace.\n\n
    In order to execute successful requests to this endpoint, the following environment variables are
    required to be set before starting the model registry microservice: `GETI_HOST` and `GETI_TOKEN`."""
    log_msg_prefix = "GET /projects"
    logger.info(f"{log_msg_prefix} endpoint started.")
    geti_sdk = GetiSdk()
    try:
        projects = geti_sdk.get_projects()
    except Exception as exc:
        return get_exception_response(log_msg_prefix, exc)
    logger.info(f"{log_msg_prefix} successful. Returned Intel Geti projects' details.")
    return projects

@router.get("/projects/{project_id}",
         summary="Get a project by ID in a remote Intel® Geti workspace",
         tags=["projects"],
         response_model=ProjectOut,
         responses={
             404: {
                 "description": "Not Found",
                 "content": {
                     "text/plain": {
                         "example": "Project not found"
                     }
                 }
             }})
def get_project_by_id(project_id: ProjectIDDep):
    """Get a project by ID in a remote Intel® Geti workspace.\n\n
    In order to execute successful requests to this endpoint, the following environment variables are
    required to be set before starting the model registry microservice: `GETI_HOST` and `GETI_TOKEN`."""
    log_msg_prefix = f"GET /projects/{project_id}"
    logger.info(f"{log_msg_prefix} endpoint started.")
    geti_sdk = GetiSdk()
    try:
        projects = geti_sdk.get_projects(project_id=project_id)

        if len(projects) == 0:
            s_code = status.HTTP_404_NOT_FOUND
            resp_content = "Project not found."
            logger.warning(f"{log_msg_prefix} failed with status code: {s_code}. {resp_content}")
            return Response(resp_content+"\n", status_code=s_code)

    except Exception as exc:
        return get_exception_response(log_msg_prefix, exc)

    logger.info(f"{log_msg_prefix} successful. Returned Intel Geti project details.")
    return projects[0]


@router.post("/projects/{project_id}/geti-models/download",
          summary="Store the metadata and artifacts for 1 or more OpenVINO\
           optimized model(s) from a remote Intel® Geti workspace into the registry",
          tags=["projects"],
          status_code=201,
          response_class=PlainTextResponse,
          responses={
              201: {
                  "description": "Created",
                  "content": {
                      "text/plain": {
                          "example": "Model(s): 1, 2, 3 are registered.\nNote: Only OpenVINO optimized active models are supported at this time."
                      }
                  }
              },
              409: {
                  "description": "Conflict",
                  "content": {
                      "text/plain": {
                          "example": "Model(s): 1 is already registered. No model(s) registered.\nTip: Delete the previously mentioned model(s) or remove the id(s) from the request body then try again."
                      }
                  }
              },
              500: {
                  "description": "Internal Server Error",
                  "content": {
                      "text/plain": {
                          "example": ""
                      }
                  }
              },
              403: {
                  "description": "Forbidden",
                  "content": {
                      "text/plain": {
                          "example": "Model(s): 0 can not be registered.\nNote: Only OpenVINO optimized active models are supported at this time."
                      }
                  }
              },
              404: {
                  "description": "Not Found",
                  "content": {
                      "text/plain": {
                          "example": "Project or model id not found. No model(s) registered."
                      }
                  }
              },
          })
def save_project_and_models_by_ids(response: Response,
                                   p: ModelIdentifiersIn,
                                   project_id: ProjectIDDep):
    """
    Store the metadata and artifacts for 1 or more OpenVINO optimized model(s) from a remote Intel® Geti workspace into the registry. \n\n
    In order to execute successful requests to this endpoint, the following environment variables are
    required to be set before starting the model registry microservice: `GETI_HOST` and `GETI_TOKEN`.\n\n

    For more information about these environment variables, review the [get_server_details_from_env](https://github.com/openvinotoolkit/geti-sdk/blob/675d1e39c1bea7173934bb81db358efa2c40e813/geti_sdk/utils/credentials_helpers.py#L52C5-L52C32) function in the Intel® Geti™ SDK.

    If the `models` object contains a list of contains 1 or more `{"id":"<model_identifier>", "group_id": "model_group_identifier"}`, 1 or more models
      will be downloaded and registered.
    """
    log_msg_prefix = f"POST /projects/{project_id}/geti-models/download"
    logger.info(f"{log_msg_prefix} endpoint started.")
    geti_sdk = GetiSdk()
    try:
        # Get the projects and their models from Geti
        projects = geti_sdk.get_projects(project_id=project_id)

        if len(projects) == 1:
            project = projects[0]
            # Get all of the model ids for the project
            project_openvino_model_ids = []
            for model_group in project.model_groups:
                for mv in model_group.model_versions:
                    for om in mv.openvino_models:
                        project_openvino_model_ids.append(om.id)

            should_register_models = True

            requested_model_ids = [m.id for m in p.models]

            should_register_models = all(id in project_openvino_model_ids for id in requested_model_ids)

            if should_register_models:
                # Check if any of the requested models are already registered
                # 1. Get the ids of all of the models that are already registered
                mlflow_manager = MLflowManager()
                registered_models = mlflow_manager.get_models()
                registered_model_ids = [rm.id for rm in registered_models]

                registered_mi_set = set(registered_model_ids)
                requested_mi_set = set(requested_model_ids)

                # 2. Check if any of the requested models are on this list
                already_registered_mi_set = registered_mi_set & requested_mi_set
                if already_registered_mi_set:
                    auxiliary_verb = "are" if len(
                        already_registered_mi_set) > 1 else 'is'
                    response.status_code = status.HTTP_409_CONFLICT
                    # 3. Return response message: " ..., ..., are already registered."
                    resp_content = "Model(s): "+", ".join(already_registered_mi_set) + \
                        " " + auxiliary_verb + " already registered. No model(s) registered." + \
                        "\nTip: Delete the previously mentioned model(s) or remove the id(s) " + \
                        "from the request body then try again."
                    logger.error(f"{log_msg_prefix} failed with status code: {response.status_code}. {resp_content}")
                    return resp_content+"\n"

                result = geti_sdk.save_models(project_id=project_id, model_identifiers_in=p)

                if result is None:
                    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
                    logger.critical(f"Unknown exception occurred during {log_msg_prefix}.")
                    return "\n"

                if isinstance(result, list):
                    if len(result) == 0:
                        response.status_code = status.HTTP_403_FORBIDDEN
                        resp_content = f"Model(s): {', '.join(requested_model_ids)} can not be registered.\nNote: Only OpenVINO optimized active models are supported at this time."
                        logger.error(f"{log_msg_prefix} failed with status code: {response.status_code}. {resp_content}")
                        return resp_content+"\n"

                    resp_content = f"Model(s): {', '.join(result)} registered."
                    logger.info(f"{log_msg_prefix} successful. {resp_content}")
                    return resp_content+"\nNote: Only OpenVINO optimized active models are supported at this time.\n"

    except Exception as exc:
        return get_exception_response(log_msg_prefix, exc)

    # Set the response model and status code
    s_code = status.HTTP_404_NOT_FOUND
    response.status_code = s_code
    resp_content = "Project or model id not found. No model(s) registered."
    logger.warning(f"{log_msg_prefix} failed with status code: {s_code}. {resp_content}")
    return resp_content+"\n"
