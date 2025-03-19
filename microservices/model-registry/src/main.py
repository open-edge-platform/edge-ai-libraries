# pylint: disable=global-statement, invalid-name, consider-using-f-string, logging-format-interpolation
"""Main application"""
import os
import ssl
from contextlib import asynccontextmanager
from typing import List, Optional, Annotated
import uvicorn
from fastapi import FastAPI, Response, status, Request, Depends
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from routers import geti
from utils.logging_config import logger
from utils.app_utils import get_version_info, check_required_env_vars, get_bool, get_exception_response, validate_resource_id, ResourceType
from models.registered_model import RegisteredModelOut, ModelIn, UpdateModelIn
from managers.mlflow_manager import MLflowManager
from managers.minio_manager import MinioManager

IS_HTTPS_MODE_ENABLED = get_bool(os.getenv("ENABLE_HTTPS_MODE", "True"), ignore_empty=True)
IS_DEV_MODE_ENABLED = get_bool(os.getenv("ENABLE_DEV_MODE", "False"),
                               "ENABLE_DEV_MODE")

ModelIDDep = Annotated[str, Depends(validate_resource_id(ResourceType.MODEL))]

@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Manages the application's lifespan and displays log messages when the service starts up 
    and stops.

    Args:
        application: The FastAPI application instance.

    Yields:
        None: Indicates the start of the application lifespan.
    """
    logger.info("=============== Model Registry STARTED ===============")
    logger.debug("API Reachable via %s", "HTTPS" if IS_HTTPS_MODE_ENABLED else "HTTP")
    yield
    logger.info("=============== Model Registry STOPPED ===============")

DESCRIPTION = """
This microservice enables users to access Intel® Geti projects and trained models' metadata, download and store models as well as make them accessible for downstream applications and services.\n\n

Please be advised that this Swagger page is intended for educational purposes only. While it provides a valuable resource for learning and understanding API functionalities, we do not recommend testing API endpoints through this interface. For testing, please utilize the appropriate tools such as Command Prompt, Terminal, Postman, etc.\n\nThank you for your understanding.
"""
try:
    service_ver = get_version_info()
except Exception as exc0:
    service_ver = "unknown"

app = FastAPI(title="Model Registry",
              summary="""The Model Registry microservice provides a comprehensive set of endpoints
     to manage machine learning models in a locally deployed environment.""",
              description=DESCRIPTION,
              version=service_ver, lifespan=lifespan)


@app.get("/health", summary="Health Check.")
def health_check():
    """
    Get the health status of the service. 
    """
    log_msg_prefix = "GET /health"
    logger.info(f"{log_msg_prefix} endpoint started.")
    logger.info(f"{log_msg_prefix} successful. Returned health status.")
    return {"status": "ok"}

@app.get("/models",
         summary="Get all registered model(s)",
         tags=["models"],
         response_model=List[RegisteredModelOut],
          responses={})
def get_registered_models(request: Request,
                          name: Optional[str] = None,
                          project_name: Optional[str] = None,
                          category: Optional[str] = None,
                          version: Optional[str] = None,
                          architecture: Optional[str] = None,
                          precision: Optional[str] = None):
    """Get all registered model(s). """
    try:
        log_msg_prefix = "GET /models"
        logger.info(f"{log_msg_prefix} endpoint started.")
        # Check if the request query parameters is allowed
        allowed_q_params = ["name", "project_name", "category", "architecture", "precision", "version"]
        keys = request.query_params.keys()
        invalid_q_params = [key for key in keys if key not in allowed_q_params]
        if len(invalid_q_params):
            s_code = status.HTTP_422_UNPROCESSABLE_ENTITY
            resp_content = "Invalid query parameter(s): " + ", ".join(list(invalid_q_params))
            logger.error(f"{log_msg_prefix} failed with status code: {s_code}. {resp_content}")
            return Response(resp_content+"\n", status_code=s_code)

        mlflow_manager = MLflowManager()
        models = mlflow_manager.get_models(keys=["name", "project_name", "category", "architecture", "precision", "version"], values=[name, project_name, category, architecture, precision, version])

        if len(models) == 0 and any([name, project_name, category, architecture, precision, version]):
            s_code = status.HTTP_404_NOT_FOUND
            resp_content = "Model(s) not found."
            logger.warning(f"{log_msg_prefix} failed with status code: {s_code}. {resp_content}")
            return Response(resp_content+"\n", status_code=s_code)

        logger.info(f"{log_msg_prefix} successful. Returned models' details.")
        return models
    except Exception as exc:
        return get_exception_response(log_msg_prefix, exc)


@app.get("/models/{model_id}",
         summary="Get a registered model by ID",
         tags=["models"],
         response_model=RegisteredModelOut,
         responses={
             404: {
                 "description": "Not Found",
                 "content": {
                     "text/plain": {
                         "example": "Model not found."
                     }
                 }
             }})
def get_registered_model_by_id(model_id: ModelIDDep):
    """Get a registered model by ID. """
    log_msg_prefix=f"GET /models/{model_id}"
    logger.info(f"{log_msg_prefix} endpoint started.")
    mlflow_manager = MLflowManager()
    registered_models = mlflow_manager.get_models(model_id=model_id)

    if len(registered_models) == 0:
        s_code = status.HTTP_404_NOT_FOUND
        resp_content = "Model not found."
        logger.warning(f"{log_msg_prefix} failed with status code: {s_code}. {resp_content}")
        return Response(resp_content+"\n", status_code=s_code)

    logger.info(f"{log_msg_prefix} successful. Returned model details.")
    return registered_models[0]

@app.post("/models",
    summary="Store the metadata and artifacts for a model into the registry.",
    tags=["models"],
    status_code=201,
    response_class=PlainTextResponse,
    responses={
        201: {
            "description": "Created",
            "content": {
                "text/plain": {
                    "example": "model_id"
                }
            }
        },
        409: {
            "description": "Conflict",
            "content": {
                "text/plain": {
                    "example": "Model ID {id} is already in use."
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
        }
    })
async def store_model(request: Request,
                      model: ModelIn = Depends()):
    """
    Store the metadata and artifacts for a model. 
    """
    log_msg_prefix = "POST /models"
    logger.info(f"{log_msg_prefix} endpoint started.")
    model_id = ""

    supported_keys = ("name", "precision", "version", "score", "target_device",
                    "format", "id", "created_date", "size", "origin", "project_id",
                    "project_name", "category", "target_device_type", "overview", 
                    "optimization_capabilities", "labels", "architecture", "file")
    supported_file_content_types = ["application/zip", "multipart/x-zip",
                                    "application/zip-compressed", "application/x-zip-compressed",
                                    "application/x-zip"]

    form_data = await request.form()
    form_data_dict = dict(form_data)
    unsupported_keys = set(form_data.keys()) - set(supported_keys)
    file_content_type = model.file.content_type
    form_data_dict["size"] = model.file.size
    validation_error_msg = ""

    if unsupported_keys:
        validation_error_msg = f"Unsupported key(s) found: {', '.join(unsupported_keys)}"
    elif not file_content_type in supported_file_content_types:
        validation_error_msg = f"Unsupported file type found: {file_content_type}"

    if validation_error_msg:
        s_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        logger.error(f"{log_msg_prefix} failed with status code: {s_code}. {validation_error_msg}")
        return Response(validation_error_msg+"\n", status_code=s_code)

    mlflow_manager = MLflowManager()

    if "precision" in form_data_dict.keys() and form_data_dict.get("precision", "") != "":
        form_data_dict["precision"] = form_data_dict["precision"].lower()
        if not form_data_dict["precision"] in ['fp32', 'fp16', 'int8', 'int4']:
            s_code = status.HTTP_400_BAD_REQUEST
            resp_content = f"{form_data_dict['precision']} is not a supported precision."
            logger.error(f"{log_msg_prefix} failed with status code: {s_code}. {resp_content}")
            return Response(resp_content+"\n", status_code=s_code)

    # Register the model using MLflow
    try:
        file_data = model.file.file
        del form_data_dict["file"]

        model_id, is_duplicate_model, msg = mlflow_manager.register_model(metadata=form_data_dict, file_content=file_data, file_name=model.file.filename)

        if is_duplicate_model:
            s_code = status.HTTP_409_CONFLICT
            conflict_reason = msg
            resp_content = "The requested action could not be completed due to a conflict with model " + conflict_reason
            logger.error(f"{log_msg_prefix} failed with status code: {s_code}. {resp_content}")
            return Response(resp_content, status_code=s_code)

        if "error" in msg.lower():
            raise RuntimeError(msg)

    except Exception as exc:
        return get_exception_response(log_msg_prefix, exc)

    logger.info(f"{log_msg_prefix} successful. Registered Model Name: {form_data_dict['name']}, Version: {form_data_dict['version']}, ID: {model_id}.")
    return model_id

@app.put("/models/{model_id}",
    summary="Update the specified properties of a registered model.",
    tags=["models"],
    status_code=status.HTTP_200_OK,
    response_class=JSONResponse,
    responses={
        200: {
            "description": "OK",
            "content": {
                "application/json": {
                    "example": {
                        "status": "completed"
                    }
                }
            }
        },
        400: {
            "description": "Bad Request",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Invalid request. Check the request body and ensure at least 1 supported field is provided."
                    }
                }
            }
        },
        404: {
            "description": "Not Found",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Model not found."
                    }
                }
            }
        },
        500: {
            "description": "Internal Server Error",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "string"
                    }
                }
            }
        }
    })
async def update_model(model_id: ModelIDDep,
                      update_data: UpdateModelIn = Depends()):
    """
    Update the specified properties of a registered model.
    
    The ability to update a model's stored compressed `file`, and `id` is not supported. 

    If you would like to update any of these properties, you will need to delete the existing model (`DELETE /models`) and submit a `POST /models` request to store a model with the desired properties.
    """
    s_code = 200
    log_msg_prefix = f"PUT /models/{model_id}"
    logger.info(f"{log_msg_prefix} endpoint started.")
    response = None
    try:
        update_data_dict = update_data.__dict__
        update_data_dict = {k:v for k, v in update_data_dict.items() if v}

        if update_data_dict == {}:
            s_code = status.HTTP_400_BAD_REQUEST
            msg = "Invalid request. Check the request body " \
                "and ensure at least 1 supported field is provided."
            logger.error(f"{log_msg_prefix} failed with status code: {s_code}. {msg}")
            rsp_content = {"status": "error", "message": msg}
            return JSONResponse(rsp_content, status_code=s_code)

        # Get the model associated to the model_id
        registered_model = get_registered_model_by_id(model_id=model_id)

        if isinstance(registered_model, Response):
            response = registered_model
            resp_content = response.body.decode()
            logger.warning(f"{log_msg_prefix} failed with status code: {response.status_code}. {resp_content}")
            return response

        # Update the respective properties of an existing model
        mlflow_manager = MLflowManager()
        is_update_completed, is_duplicate_model, msg = mlflow_manager.update_model(model_id=registered_model.id,
                                                          metadata=update_data_dict)

        if is_duplicate_model:
            s_code = status.HTTP_409_CONFLICT
            conflict_reason = msg
            resp_content = "The requested action could not be completed due to a conflict with model " + conflict_reason
            logger.error(f"{log_msg_prefix} failed with status code: {s_code}. {resp_content}")
            return Response(resp_content, status_code=s_code)

        if "error" in msg.lower():
            raise RuntimeError(msg)

        if is_update_completed:
            logger.info(f"{log_msg_prefix} successful. Updated model metadata.")
            rsp_content = {"status": "completed"}
            return JSONResponse(rsp_content, status_code=s_code)

    except Exception as exc:
        return get_exception_response(log_msg_prefix, exc)


@app.delete("/models/{model_id}",
            summary="Delete a registered model by ID",
            tags=["models"],
            status_code=status.HTTP_204_NO_CONTENT,
            response_class=PlainTextResponse,
            responses={
                204: {
                    "description": "No Content",
                    "content": {
                        "text/plain": {
                            "example": ""
                        }
                    }
                },
                404: {
                    "description": "Not Found",
                    "content": {
                        "text/plain": {
                            "example": "Model not found."
                        }
                    }
                }})
def delete_registered_model_by_id(response: Response, model_id: ModelIDDep):
    """Delete a registered model by ID. """
    try:
        log_msg_prefix=f"DELETE /models/{model_id}"
        logger.info(f"{log_msg_prefix} endpoint started.")
        msg = ""
        mlflow_manager = MLflowManager()
        is_model_deleted = mlflow_manager.delete_model(m_id=model_id)

        if not is_model_deleted:
            response.status_code = status.HTTP_404_NOT_FOUND
            msg = "Model not found.\n"

        if response.status_code == status.HTTP_404_NOT_FOUND:
            logger.warning(f"{log_msg_prefix} failed with status code: {response.status_code}. {msg}")
        else:
            logger.info(f"{log_msg_prefix} successful. Model deleted.")
        return msg
    except Exception as exc:
        return get_exception_response(log_msg_prefix, exc)


@app.get("/models/{model_id}/files",
         summary="Get a ZIP file containing the artifacts (files) for a registered model",
         tags=["models"],
         responses={
             200: {
                 "description": "OK",
                 "content": {
                     "application/zip": {
                         "example": ""
                     }
                 }
             },
             404: {
                 "description": "Not Found",
                 "content": {
                     "text/plain": {
                         "example": "Model not found."
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
             }})
def get_zip_for_registered_model_by_id(request: Request, model_id: ModelIDDep):
    """Get a ZIP file containing the artifacts (files) for a registered model. """
    log_msg_prefix = f"GET /models/{model_id}/files"
    logger.info(f"{log_msg_prefix} endpoint started.")
    response = None
    try:
        # Get the model associated to the model_id
        registered_model = get_registered_model_by_id(model_id=model_id)

        if isinstance(registered_model, Response):
            response = registered_model
            resp_content = response.body.decode()
            logger.warning(f"{log_msg_prefix} failed with status code: {response.status_code}. {resp_content}")
            return response

        # Get the file from minio and send it back to the client
        download_url = registered_model.file_url.replace("minio://", "")
        download_url_strs = download_url.split("/")
        prefix_dir_obj_name = "/".join(download_url_strs[1:3])

        minio_manager = MinioManager()

        object_bytes = minio_manager.get_object(
            object_name=prefix_dir_obj_name)

        if object_bytes:
            # Set the content type
            content_type = 'application/zip'

            is_req_from_swagger_page = request.headers.get("referer","").endswith(app.docs_url)
            if is_req_from_swagger_page:
                content_type = "application/octet-stream"

            # Return the object's data as the Response
            logger.info(f"{log_msg_prefix} successful. Returned model files.")
            return Response(object_bytes, status_code=status.HTTP_200_OK, media_type=content_type)

    except Exception as exc:
        return get_exception_response(log_msg_prefix, exc)

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request, exc):
    """Catch the http related errors/exceptions

    Args:
        request (Request): HTTP request received
        exc (HTTPException): Validation error associated to the request
    """
    logger.error(f"{request.method} {request.url.path} failed. {exc.detail}")
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Catch the validation related errors/exceptions

    Args:
        request (Request): HTTP request received
        exc (RequestValidationError): Validation error associated to the request
    """
    logger.error(f"{request.method} {request.url.path} failed. {exc.errors()}")
    return await request_validation_exception_handler(request, exc)

# Include Router for Geti related endpoints
app.include_router(geti.router)

if __name__ == "__main__": # pragma: no cover
    try:
        logger.info("=============== STARTING Model Registry ===============")

        server_private_key = None
        server_certificate = None
        # Python3.10 - Use the highest supported protocol version OR TLS 1.2
        tls_version = ssl.PROTOCOL_TLS_SERVER
        # Preferred ciphers for TLS 1.2 & 1.3
        cipher_suites = "ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-GCM-SHA384:TLS_AES_256_GCM_SHA384"

        is_required_env_vars_set, missing_env_var_names = check_required_env_vars()
        if not is_required_env_vars_set:
            error_msg = f"Required Environment Variables are missing: " \
                f"{', '.join(missing_env_var_names[:-1]) + ' and ' + missing_env_var_names[-1]}."
            raise ValueError(error_msg)

        if IS_HTTPS_MODE_ENABLED:
            server_private_key = os.environ["SERVER_PRIVATE_KEY"]
            server_certificate = os.environ["SERVER_CERT"]

            if not (os.path.exists(server_certificate) and os.path.exists(server_private_key)):
                raise ValueError("The required SSL certificate and private key files are not found. Please provide both for HTTPS connections.")

        server_conf = uvicorn.Config(app="main:app", host="0.0.0.0", port=int(os.environ["SERVER_PORT"]), reload=IS_DEV_MODE_ENABLED,
                        log_level=uvicorn.config.LOG_LEVELS["critical"], ssl_certfile=server_certificate, ssl_keyfile=server_private_key,
                        ssl_version=tls_version, ssl_ciphers=cipher_suites)
        server = uvicorn.Server(config=server_conf)
        server.run()

    except Exception as error:
        logger.error(f"Starting Model Registry failed. {error}")
