# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from logging.config import dictConfig
from http import HTTPStatus
from typing import Optional, Annotated
import logging
import pathlib

from pydantic import BeforeValidator
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Query, Path, Header
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi import UploadFile, File
from minio.error import S3Error
from minio.deleteobjects import DeleteObject

from minio_store.store import DataStore
from minio_store.util import DataStoreException, Settings, Strings, Validation
from minio_store.schema import (
    DataStoreResponse,
    DataStoreErrorResponse,
    FileListResponse,
    Logger,
    StatusEnum,
)

settings = Settings()
dictConfig(Logger().model_dump())
logger = logging.getLogger(settings.APP_NAME)

app = FastAPI(title=settings.APP_DISPLAY_NAME, description=settings.APP_DESC, root_path="/v1/datastore")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=settings.ALLOW_METHODS.split(","),
    allow_headers=settings.ALLOW_HEADERS.split(","),
)


# Setting up custom error message format
@app.exception_handler(HTTPException)
async def custom_exception_handler(request, exc):
    error_res = DataStoreResponse(status=StatusEnum.error, message=exc.detail)
    return JSONResponse(content=error_res.model_dump(), status_code=exc.status_code)


"""
API Endpoints
"""

# TODO
# Implement directory batch uploads in DataStore service

@app.get("/health", tags=["Status APIs"], summary="Check the health of the API service")
async def check_health():
    return {"status": "ok"}

@app.post(
    "/data",
    tags=["Storage APIs"],
    summary="Upload resources, files or documents.",
    status_code=HTTPStatus.CREATED,
    response_model_exclude_none=True,
)
async def upload_data(
    file: Annotated[UploadFile, File(description="Select a file to be uploaded.")],
    bucket_name: Annotated[
        str, BeforeValidator(Validation.sanitize_input), Query(min_length=3)
    ] = settings.DEFAULT_BUCKET,
    dest_file_name: Annotated[
        Optional[str],
        BeforeValidator(Validation.sanitize_input),
        Query(description="An optional destination file name"),
    ] = None,
) -> FileListResponse:
    """Upload resources or files/documents to Storage Server"""
    try:

        client = DataStore.get_client()

        # Create filename used to save file on storage server based on either source file or 
        # a provided destination file name.
        source_filename = file.filename
        destination_filename = DataStore.get_destination_file(dest_file_name or source_filename)
        logger.info(f"Filename to be saved as : {destination_filename}")
        # Create bucket if bucket doesnot exist
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logger.info(f"Bucket Created : {bucket_name}")

        client.put_object(
            bucket_name=bucket_name,
            object_name=destination_filename,
            data=file.file,
            length=file.size,
        )
        logger.info("File uploaded successfully!")

        return FileListResponse(
            status=StatusEnum.success,
            bucket_name=bucket_name,
            files=[destination_filename],
        )

    except S3Error as ex:
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail=Strings.s3_error_msg)

    except Exception as ex:
        logger.error(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )


@app.get(
    "/data",
    tags=["Storage APIs"],
    summary="Get list of available resources, files or documents.",
    response_model_exclude_none=True,
)
async def get_data(
    bucket_name: Annotated[
        str, BeforeValidator(Validation.sanitize_input), Query(min_length=3)
    ] = settings.DEFAULT_BUCKET,
    prefix: Annotated[
        str,
        BeforeValidator(Validation.strip_input),
        Query(
            description="An optional filter for bucket to get files starting with particular prefix. \
                Prefix value could be directory name in which file resides on server."
        ),
    ] = "",
    list_no_prefix: Annotated[
        bool,
        Query(
            description="File listing, by default, does not have prefix added to file names. Switch it \
                to False to show prefix with each filename."
        ),
    ] = True,
) -> FileListResponse:
    """Get the list of resources or files/documents stored on Storage Server"""

    try:
        client = DataStore.get_client()

        if not client.bucket_exists(bucket_name):
            raise DataStoreException(msg=Strings.invalid_bucket, status_code=HTTPStatus.NOT_FOUND)

        complete_prefix = str(pathlib.Path(prefix) / settings.OBJECT_PREFIX)
        files = client.list_objects(bucket_name, prefix=complete_prefix)

        filelist = [
            file.object_name.replace(prefix, "") if list_no_prefix else file.object_name
            for file in files
        ]

        return FileListResponse(status=StatusEnum.success, bucket_name=bucket_name, files=filelist)

    except S3Error as ex:
        logger.error(ex)
        raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail=Strings.s3_error_msg)

    except DataStoreException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)

    except Exception as ex:
        logger.error(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )


@app.get(
    "/data/{file_name}",
    tags=["Storage APIs"],
    summary="Download a file from DataStore Service.",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "A downloadable file."},
        404: {"model": DataStoreErrorResponse, "description": "File not found"},
    },
)
async def download_file(
    file_name: Annotated[
        str,
        BeforeValidator(Validation.sanitize_input),
        Path(min_length=3, description="Name of file to be downloaded"),
    ],
    bucket_name: Annotated[
        str, BeforeValidator(Validation.sanitize_input), Query(min_length=3)
    ] = settings.DEFAULT_BUCKET,
    prefix: Annotated[
        str,
        BeforeValidator(Validation.strip_input),
        Query(
            description="Download files starting with an optional prefix. Prefix value could be \
                the directory name in which file resides on server."
        ),
    ] = "",
    range: Optional[str] = Header(None)
):
    """
    ### Downloads a file with given file_name from object storage service.

    #### Params:
    ##### Path Params:
    - **file_name (str) :** Name of the file to be downloaded

    ##### Query Params:
    - **bucket_name (str) :** Name of the bucket where the file to be downloaded is stored

    #### Returns:
    - **File (streaming bytes) :** Streams the file as a response which is downloadable by any browser.
    """

    try:
        client = DataStore.get_client()

        if not client.bucket_exists(bucket_name):
            raise DataStoreException(msg=Strings.invalid_bucket, status_code=HTTPStatus.BAD_REQUEST)

        # Get the complete file object name using prefix (adds directory in which file resides, if needed)
        file_obj = str(pathlib.Path(prefix) / file_name)

        # Get the file size to be sent as response header
        stats = client.stat_object(bucket_name, file_obj)
        file_size = stats.size

        if range:
            logger.debug(f'download_file {file_name} engaged with range header. range: {range}')
            range = range.strip().split("=")[-1]
            range_start, range_end = range.split("-")
            range_start = int(range_start)
            range_end = int(range_end) if range_end else file_size - 1
            content_length = (range_end - range_start) + 1
            content_range = f"bytes {range_start}-{range_end}/{file_size}"

            def range_stream():
                response = client.get_object(bucket_name, file_obj, offset=range_start, length=content_length)
                yield from response.stream(4096)

            headers = {
                "Content-Range": content_range,
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": "application/octet-stream",
                "Content-Disposition": f"attachment; filename={file_name}",
            }

            return StreamingResponse(range_stream(), headers=headers, status_code=206)

        else:
            logger.debug(f'download_file engaged without range')
            def download_streaming_file():
                response = client.get_object(bucket_name, file_obj)
                yield from response.stream(4096)

            headers = {
                "Content-Type": "application/octet-stream",
                "Content-Length": f"{file_size}",
                "Content-Disposition": f"attachment; filename={file_name}",
            }

            return StreamingResponse(download_streaming_file(), headers=headers)

    except S3Error as ex:
        logger.error(ex)
        if ex.code == "NoSuchKey":
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=Strings.file_not_found)
        else:
            raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail=Strings.s3_error_msg)

    except DataStoreException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)

    except Exception as ex:
        logger.error(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )


@app.delete(
    "/data",
    tags=["Storage APIs"],
    summary="Delete resources, files or documents.",
    status_code=HTTPStatus.NO_CONTENT,
)
async def delete_data(
    bucket_name: Annotated[
        str, BeforeValidator(Validation.sanitize_input), Query(min_length=3)
    ] = settings.DEFAULT_BUCKET,
    file_name: Annotated[
        Optional[str],
        BeforeValidator(Validation.sanitize_input),
        Query(description="Name of file to be deleted, required only if not deleting all files."),
    ] = None,
    delete_all: bool = False,
    prefix: Annotated[
        str,
        BeforeValidator(Validation.strip_input),
        Query(
            description="Delete files starting with an optional prefix. Prefix value could be \
                directory name in which file resides on server."
        ),
    ] = "",
) -> None:
    """Delete resources or files/documents stored on Storage Server"""

    try:
        client = DataStore.get_client()

        if not client.bucket_exists(bucket_name):
            raise DataStoreException(msg=Strings.invalid_bucket, status_code=HTTPStatus.NOT_FOUND)

        # complete_prefix is used to find all relevant files in a bucket in particular dir. 
        # It has the provided prefix (generally a dir name) concatenated with OBJECT_PREFIX, 
        # which helps in finding all files with common prefix.
        complete_prefix = str(pathlib.Path(prefix) / settings.OBJECT_PREFIX)

        # file_obj is the full name of file concatenated with a prefix (generally a parent directory)
        file_obj = str(pathlib.Path(prefix) / (file_name or ""))

        # If single file needs to deleted, delete it and return immediately.
        if not delete_all:
            if not file_name:
                raise DataStoreException(
                    msg=Strings.del_req_validation_error,
                    status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                )

            # Check whether file exists, raises error if file doesnot exist
            _ = client.stat_object(bucket_name, file_obj)
            client.remove_object(bucket_name, file_obj)
            return

        # If all files need to be deleted, get all files in the bucket

        all_objects = client.list_objects(bucket_name, prefix=complete_prefix)

        # Get a list out of iterable returned by list_objects method. This is required to find the num of items
        # in bucket and then iterate, again over it to create DeleteObjects. As num of items increase in bucket,
        # this won't be very effective method. We will better call the list_objects 2 times, instead.

        all_objects_list: list = list(all_objects)

        # If bucket is empty raise 404
        if not len(all_objects_list):
            raise DataStoreException(msg=Strings.bucket_empty, status_code=HTTPStatus.NOT_FOUND)

        # Create s3 DeleteObject out of object names present in the bucket
        delete_list = map(lambda x: DeleteObject(x.object_name), all_objects_list)
        errors = client.remove_objects(bucket_name, delete_list)
        error_list = [err for err in errors]
        if error_list:
            logger.error(error_list)
            raise DataStoreException(msg=Strings.delete_error, status_code=HTTPStatus.BAD_GATEWAY)

    except S3Error as ex:
        logger.error(ex)
        # If key (file or resource) not found then raise 404 else raise BAD_GATEWAY
        if ex.code == "NoSuchKey":
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=Strings.file_not_found)
        else:
            raise HTTPException(status_code=HTTPStatus.BAD_GATEWAY, detail=Strings.s3_error_msg)

    except DataStoreException as ex:
        logger.error(ex)
        raise HTTPException(status_code=ex.status_code, detail=ex.message)

    except Exception as ex:
        logger.error(ex)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=Strings.server_error
        )
