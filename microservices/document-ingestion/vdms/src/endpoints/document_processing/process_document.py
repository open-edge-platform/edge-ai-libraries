# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from src.common import DataPrepException, Strings, logger
from src.core.embedding import generate_text_embedding
from src.core.util import get_minio_client
from src.common.schema import DataPrepResponse, DocumentRequest

router = APIRouter(tags=["Data Preparation APIs"])


@router.post(
    "/documents",
    summary="Process text document with video timestamp references for embedding generation.",
    status_code=HTTPStatus.CREATED,
    response_model_exclude_none=True,
)
async def process_document(
    document_request: Annotated[DocumentRequest, Body(description="Document processing parameters")]
) -> DataPrepResponse:
    """
    ### Process text document with video timestamp references for embedding generation.

    This endpoint takes a text summary and video timestamp references, validates that the video exists,
    and stores the text embedding in the VDMS vector database with the associated video metadata.

    #### Body Params:
    - **document_request (DocumentRequest) :** Contains processing parameters:
       - **bucket_name (str) :** The bucket name where the referenced video is stored
       - **video_id (str) :** The video ID (directory) containing the referenced video
       - **text_summary (str) :** The text summary or document content to be embedded
       - **video_start_time (float) :** The start timestamp in seconds for the video segment related to this document
       - **video_end_time (float) :** The end timestamp in seconds for the video segment related to this document

    #### Raises:
    - **400 Bad Request :** If required parameters are missing or invalid.
    - **404 Not Found :** If the specified video cannot be found in Minio.
    - **502 Bad Gateway :** When something unpleasant happens at Minio storage.
    - **500 Internal Server Error :** When some internal error occurs at DataPrep API server.

    Returns:
    - **response (json) :** A response JSON containing status and message.
    """

    try:
        # Validate that video exists in Minio
        bucket_name = document_request.bucket_name
        video_id = document_request.video_id
        text_summary = document_request.text_summary
        video_start_time = document_request.video_start_time
        video_end_time = document_request.video_end_time

        # Validate time ranges
        if video_start_time < 0:
            raise DataPrepException(
                status_code=HTTPStatus.BAD_REQUEST,
                msg="video_start_time must be greater than or equal to 0",
            )
        
        if video_end_time <= video_start_time:
            raise DataPrepException(
                status_code=HTTPStatus.BAD_REQUEST,
                msg="video_end_time must be greater than video_start_time",
            )

        # Get the Minio client and ensure the bucket exists
        minio_client = get_minio_client()
        minio_client.ensure_bucket_exists(bucket_name)

        # Verify that the video_id exists
        if not minio_client.directory_exists(bucket_name, video_id):
            raise DataPrepException(
                status_code=HTTPStatus.NOT_FOUND,
                msg=f"Video directory '{video_id}' not found in bucket '{bucket_name}'",
            )

        # Process document and generate text embeddings
        ids = await generate_text_embedding(
            bucket_name=bucket_name,
            video_id=video_id,
            text_summary=text_summary,
            video_start_time=video_start_time,
            video_end_time=video_end_time,
        )

        logger.info(f"Text embedding created with ids: {ids}")
        return DataPrepResponse(message="Document embedding created successfully")

    except DataPrepException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)

    except ValueError as ex:
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(ex))

    except Exception as ex:
        logger.error(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )
