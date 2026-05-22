# SPDX-License-Identifier: Apache-2.0
"""HTTP routes for the ``/models`` API.

This module is intentionally thin: all business logic lives in
:class:`managers.model_manager.ModelManager`. Routes here only convert
between API schemas and internal types.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

import api.api_schemas as schemas
from internal_types import (
    InternalModelCategory,
    InternalModelUploadSpec,
    InternalSupportedModel,
)
from managers.model_manager import ModelManager

router = APIRouter()
logger = logging.getLogger("api.routes.models")


# ----------------------------------------------------------------------
# Internal -> API converters (kept local: only this route returns models)
# ----------------------------------------------------------------------


def _internal_model_to_api(model: InternalSupportedModel) -> schemas.Model:
    """Convert an :class:`InternalSupportedModel` into the API ``Model``."""
    return schemas.Model(
        name=model.name,
        display_name=model.display_name,
        category=(
            schemas.ModelCategory(model.category.value) if model.category else None
        ),
        source=schemas.ModelSource(model.source.value),
        install_status=schemas.ModelInstallStatus(model.install_status.value),
        variants=[
            schemas.ModelVariant(
                name=v.name,
                display_name=v.display_name,
                precision=v.precision,
                installed=v.installed,
            )
            for v in model.variants
        ],
        used_by_pipelines=list(model.used_by_pipelines),
        default=model.default,
        unsupported_devices=model.unsupported_devices,
    )


# ----------------------------------------------------------------------
# GET /models
# ----------------------------------------------------------------------


@router.get(
    "",
    operation_id="get_models",
    summary="List All Models",
    response_model=list[schemas.Model],
    response_description="List of all installed and available models",
)
async def get_models():
    """
    # List Models

    Return every model known to vippet-app: entries from
    `supported_models.yaml` plus user-uploaded custom models.

    ## Response

    | Code | Description |
    |------|-------------|
    | 200  | JSON array of `Model` objects |
    | 500  | Unexpected error |

    The `install_status` field reflects the current state on disk (and
    in-flight jobs). The `used_by_pipelines` array lists predefined
    pipelines that reference each model; an empty array means the model
    is not currently used by any predefined pipeline.
    """
    try:
        models = ModelManager().list_models()
        return [_internal_model_to_api(m) for m in models]
    except Exception:
        logger.error("Failed to list models", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while listing models"
            ).model_dump(),
            status_code=500,
        )


# ----------------------------------------------------------------------
# POST /models/upload
# ----------------------------------------------------------------------


@router.post(
    "/upload",
    operation_id="upload_model",
    summary="Upload a custom model",
    responses={
        201: {
            "description": "Model uploaded successfully",
            "model": schemas.ModelUploadResponse,
        },
        400: {"description": "Invalid upload", "model": schemas.MessageResponse},
        409: {
            "description": "Model already exists",
            "model": schemas.MessageResponse,
        },
        413: {
            "description": "File too large",
            "model": schemas.MessageResponse,
        },
        500: {"description": "Unexpected error", "model": schemas.MessageResponse},
        502: {
            "description": "Upstream model-download error",
            "model": schemas.MessageResponse,
        },
    },
)
async def upload_model(
    model_name: Annotated[str, Form(..., min_length=1)],
    category: Annotated[schemas.ModelCategory, Form(...)],
    file: Annotated[UploadFile, File(...)],
):
    """
    # Upload Model

    Upload a ZIP file with ``model.xml`` + ``model.bin`` at its root.
    The upload is streamed to the model-download microservice and the
    resulting model is registered locally as a `custom` model so it
    appears immediately in `GET /models`.

    ## Form fields

    - **`model_name`** *(required)* - Canonical identifier for the model
    - **`category`** *(required)* - Logical model category
      (`classification`, `detection`, `genai`)
    - **`file`** *(required)* - ZIP file containing the OpenVINO IR

    ## Response Codes

    | Code | Description |
    |------|-------------|
    | 201  | `ModelUploadResponse` with the newly registered model |
    | 400  | Invalid form fields or ZIP contents |
    | 409  | A model with the same `model_name` already exists |
    | 413  | Uploaded file exceeds the configured size limit |
    | 502  | model-download microservice returned an error |
    | 500  | Unexpected error |
    """
    tmp_path: str | None = None
    try:
        # Stream the upload to disk so we can forward it without holding
        # the whole file in memory.
        tmp_path = ModelManager.write_upload_to_tempfile(
            file.file, file.filename or f"{model_name}.zip"
        )
        spec = InternalModelUploadSpec(
            model_name=model_name,
            category=InternalModelCategory(category.value),
            file_path=tmp_path,
            original_filename=file.filename or f"{model_name}.zip",
        )
        model, status, message = ModelManager().upload_model(spec)
        if model is None:
            return JSONResponse(
                content=schemas.MessageResponse(message=message).model_dump(),
                status_code=status,
            )
        api_model = _internal_model_to_api(model)
        return JSONResponse(
            content=schemas.ModelUploadResponse(model=api_model).model_dump(),
            status_code=status,
        )
    except Exception:
        logger.error("Unexpected error while uploading model", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while uploading model"
            ).model_dump(),
            status_code=500,
        )
    finally:
        ModelManager.cleanup_tempfile(tmp_path)


# ----------------------------------------------------------------------
# POST /models/download
# ----------------------------------------------------------------------


@router.post(
    "/download",
    operation_id="start_model_download",
    summary="Start one or more model download jobs",
    responses={
        202: {
            "description": "All requested downloads accepted",
            "model": schemas.ModelDownloadJobResponse,
        },
        207: {
            "description": (
                "Multi-Status: some downloads accepted, some rejected. "
                "Inspect `jobs[<name>].status_code` for per-model outcome."
            ),
            "model": schemas.ModelDownloadJobResponse,
        },
        400: {
            "description": (
                "All requested models were rejected with the same "
                "client error (e.g. missing `download_request`)."
            ),
            "model": schemas.ModelDownloadJobResponse,
        },
        404: {
            "description": (
                "All requested models are unknown (not present in "
                "`supported_models.yaml`)."
            ),
            "model": schemas.ModelDownloadJobResponse,
        },
        409: {
            "description": (
                "All requested models are already installed or have a "
                "download job already running."
            ),
            "model": schemas.ModelDownloadJobResponse,
        },
        422: {
            "description": "Request body validation failed (e.g. duplicate names).",
            "model": schemas.MessageResponse,
        },
        500: {
            "description": "Unexpected error",
            "model": schemas.MessageResponse,
        },
    },
)
async def start_model_download(body: schemas.ModelDownloadRequest):
    """
    # Start Model Downloads

    Start an asynchronous download job for each model in the request.
    Each entry of `names` is processed **independently** and produces
    its own per-model entry in the response map `jobs`. Names must be
    declared in `supported_models.yaml`; OMZ models are downloaded
    locally by vippet-app because model-download has no OMZ plugin yet.

    Each accepted name spawns a background worker right away — the
    endpoint does **not** wait for any download to finish, so adding
    more names does not delay the others.

    ## Request Body

    - **`names`** *(required)* - Non-empty list of unique supported-model
      names to install.

    ## Response Body

    A `ModelDownloadJobResponse` whose `jobs` map is keyed by the
    requested model name. Each value carries the per-model
    `job_id` / `status_code` / `message`.

    ## Response Codes

    | Code | When |
    |------|------|
    | 202  | Every requested model accepted (`status_code=202` for all entries) |
    | 207  | Some accepted, some rejected (mixed `status_code` values) |
    | 400  | All requested models share the same client error (e.g. no `download_request`) |
    | 404  | All requested models are unknown |
    | 409  | All requested models are already installed or in progress |
    | 422  | Body validation failed (empty list, duplicate names, ...) |
    | 500  | Unexpected error |
    """
    manager = ModelManager()
    try:
        items: dict[str, schemas.ModelDownloadJobItem] = {}
        for name in body.names:
            job_id, status, message = manager.start_download(name)
            items[name] = schemas.ModelDownloadJobItem(
                name=name,
                job_id=job_id,
                status_code=status,
                message=message,
            )
    except Exception:
        logger.error("Unexpected error while starting download(s)", exc_info=True)
        return JSONResponse(
            content=schemas.MessageResponse(
                message="Unexpected error while starting download"
            ).model_dump(),
            status_code=500,
        )

    outer_status = _aggregate_status(items)
    return JSONResponse(
        content=schemas.ModelDownloadJobResponse(jobs=items).model_dump(),
        status_code=outer_status,
    )


def _aggregate_status(
    items: dict[str, schemas.ModelDownloadJobItem],
) -> int:
    """Combine per-model status codes into a single HTTP status.

    * All accepted (202) → ``202``.
    * Some accepted, some rejected → ``207`` Multi-Status.
    * All rejected with the same client error code → that code.
    * All rejected with mixed client error codes → the *worst* one,
      with ``400 > 404 > 409`` as the precedence used by the route.
    """
    codes = [item.status_code for item in items.values()]
    if not codes:
        # Body validation guarantees a non-empty list, but be defensive.
        return 202
    if all(code == 202 for code in codes):
        return 202
    if any(code == 202 for code in codes):
        return 207
    # All rejected — pick the most specific client error.
    for preferred in (400, 404, 409):
        if preferred in codes:
            return preferred
    # Fallback: return the first error code as-is.
    return codes[0]
