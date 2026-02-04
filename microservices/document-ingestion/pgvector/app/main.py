# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import psycopg
import uvicorn
from http import HTTPStatus
from pathlib import Path
from fastapi import FastAPI, HTTPException, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BeforeValidator
from typing import Annotated, List, Optional
from .logger import logger
from .config import Settings
from .db_config import get_db_connection_pool
from .document import get_documents_embeddings, ingest_to_pgvector, save_temp_file, delete_embeddings
from .url import get_urls_embedding, ingest_url_to_pgvector, delete_embeddings_url
from .utils import check_tables_exist, Validation
from .store import DataStore

config = Settings()
pool = get_db_connection_pool()

app = FastAPI(title=config.APP_DISPLAY_NAME, description=config.APP_DESC, root_path="/v1/dataprep")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOW_ORIGINS.split(","),  # Adjust this to your needs
    allow_credentials=True,
    allow_methods=config.ALLOW_METHODS.split(","),
    allow_headers=config.ALLOW_HEADERS.split(","),
)

@app.get(
    "/health",
    tags=["Status APIs"],
    summary="Check the health of the API service"
)
async def check_health():
    """
    Checks the health status of the application.
    This asynchronous function is used to verify that the application is running
    and healthy by returning a simple status message.

    Returns:
        dict: A dictionary containing the health status of the application.
    """

    return {"status": "ok"}


@app.get(
    "/documents",
    tags=["Data Preparation APIs"],
    summary="Get list of files for which embeddings have been stored.",
    response_model=List[dict],
)
async def get_documents() -> List[dict]:
    """
    Retrieve a list of all distinct document filenames.

    Returns:
        List[dict]: A list of document filenames.
    """
    try:
        # Check if the tables exist
        if not check_tables_exist():
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="There are no embeddings created yet.",
            )

        # Get the list of files for which embeddings have been stored
        file_list = await get_documents_embeddings()

        return file_list

    except psycopg.Error as err:
        logger.error(f"Error while fetching data from DB: {err}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Some error occured. Please try later!"
        )

    except ValueError as e:
        raise e

    except Exception as ex:
        logger.error(f"Internal error: {ex}")
        raise HTTPException(
            status_code=ex.status_code if hasattr(ex, 'status_code') else HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=ex.detail if hasattr(ex, 'detail') else "Internal Server Error"
        )


@app.post(
    "/documents",
    tags=["Data Preparation APIs"],
    summary="Upload documents to create and store embeddings. Store documents in Object Storage.",
    response_model=dict,
)
async def ingest_document(
    files: Annotated[
        list[UploadFile],
        File(description="Select single or multiple PDF, docx or pdf file(s)."),
    ]
) -> dict:
    """
    Ingest documents into the system.

    Args:
        files (list[UploadFile]): A file or multiple files to be ingested.

    Returns:
        dict: A status message indicating the result of the ingestion.
    """
    try:
        if files:
            if not isinstance(files, list):
                files = [files]

            for file in files:
                fileName = os.path.basename(file.filename)
                file_extension = os.path.splitext(fileName)[1].lower()
                if file_extension not in config.SUPPORTED_FORMATS:
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail=f"Unsupported file format: {file_extension}. Supported formats are: pdf, txt, docx",
                    )
                else:
                    logger.info(
                        f"file: {file.filename} uploaded to DataStore successfully!"
                    )

                # Upload files to Data Store
                try:
                    result = DataStore.upload_document(file)
                    bucket_name = result["bucket"]
                    uploaded_filename = result["file"]

                except Exception as ex:
                    logger.error(f"Internal Error: {ex}")
                    raise HTTPException(
                        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                        detail="Some unknown error ocurred. Please try later!",
                    )

                try:
                    # Save file in temporary file on disk to ingest it
                    temp_path: Path = await save_temp_file(
                        file, bucket_name, uploaded_filename
                    )
                    logger.info(f"Temporary path of saved file: {temp_path}")
                    ingest_to_pgvector(doc_path=temp_path, bucket=bucket_name)

                except Exception as e:
                    raise HTTPException(
                        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                        detail=f"Unexpected error while ingesting data. Exception: {e}",
                    )

                finally:
                    # Delete temporary file after ingestion
                    if "temp_path" in locals():  # check if temp_path variable exist
                        Path(temp_path).unlink()
                        logger.info("Temporary file cleaned up!")

        result = {"status": 200, "message": "Data preparation succeeded"}

        return result

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))


@app.delete(
    "/documents",
    tags=["Data Preparation APIs"],
    summary="Delete embeddings and associated files from VectorDB and Object Storage",
    status_code=HTTPStatus.NO_CONTENT,
)
async def delete_documents(
    bucket_name: Annotated[
        str, BeforeValidator(Validation.sanitize_input), Query(min_length=3)
    ] = config.DEFAULT_BUCKET,
    file_name: Annotated[
        Optional[str], BeforeValidator(Validation.sanitize_input)
    ] = None,
    delete_all: bool = False
) -> None:
    """
    Delete a document or all documents from storage and their embeddings from Vector DB.

    Args:
        bucket_name (str): Bucket name where file to be deleted is stored
        file_name(str): Name of file to be deleted
        delete_all (bool): Flag to indicate delete all files. Set "True" to delete all files.
        If "False", delete only the file specified in file_name. Default set to "False".

    Returns:
        HTTPStatus: HTTP status code(NO_CONTENT) indicating the result of the deletion.
    """

    try:
        # PS: Delete request does not inform about non-existence of a file.
        # Check if the tables exist
        if not check_tables_exist():
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="There are no embeddings created yet.",
            )

        # Delete embeddings from Vector DB
        if not await delete_embeddings(bucket_name, file_name, delete_all):
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Failed to delete embeddings from vector database.")


        DataStore.delete_document(bucket_name, file_name, delete_all)

    except ValueError as err:
        logger.error(f"Error: {err}")
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(err)
        )

    except FileNotFoundError as err:
        logger.error(f"Error: {err}")
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail=str(err)
        )

    except AssertionError:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Failed to delete embeddings from the database."
        )

    except HTTPException as e:
        raise e

    except Exception as ex:
        logger.error(f"Internal error: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Internal Server Error"
        )


@app.get(
    "/documents/{file_name}",
    tags=["Data Preparation APIs"],
    summary="Download document from Object Storage",
    response_class=StreamingResponse,
)
async def download_documents(
    bucket_name: Annotated[
        str, BeforeValidator(Validation.sanitize_input), Query(min_length=3)
    ] = config.DEFAULT_BUCKET,
    file_name: Annotated[
        str, BeforeValidator(Validation.sanitize_input)
    ] = None,
):
    """
    Downloads a document from a specified bucket and returns it as a streaming response.
    Args:
        bucket_name (str): The name of the bucket to download the document from.
        Must have a minimum length of 3 characters. Defaults to `config.DEFAULT_BUCKET`.
        file_name (str): The name of the file to download.

    Returns:
        StreamingResponse: A streaming response containing the file content with
        the appropriate media type and headers for file download.

    Raises:
        HTTPException: If the file is not found, raises an exception with a 404 status code.
        HTTPException: If an internal error occurs, raises an exception with a 500 status code.
    """
    try:
        file_size = DataStore.get_document_size(bucket_name, file_name)

        file_stream = await DataStore.download_document(bucket_name, file_name)

        headers = {
            "Content-Length": f"{file_size}",
            "Content-Disposition": f"attachment; filename={file_name}"
        }

        return StreamingResponse(file_stream,
                                 media_type="application/octet-stream",
                                 headers=headers,
        )

    except FileNotFoundError as err:
        logger.error(f"Error: {err}")
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail=str(err)
        )

    except Exception as ex:
        logger.error(f"Internal error: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Internal Server Error"
        )


@app.get(
    "/urls",
    tags=["Data Preparation APIs"],
    summary="Get list of URLs for which embeddings have been stored.",
    response_model=List[str],
)
async def get_urls() -> List[str]:
    """
    Retrieve a list of all distinct URLs.

    Returns:
        List[str]: A list of document URLs.
    """
    try:
        # Check if the tables exist
        if not check_tables_exist():
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="There are no embeddings created yet.",
            )

        url_list = await get_urls_embedding()

        return url_list

    except psycopg.Error as err:
        logger.error(f"Error while fetching data from DB: {err}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Some error occured. Please try later!"
        )

    except ValueError as e:
        raise e

    except Exception as ex:
        logger.error(f"Internal error: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Internal Server Error"
        )


@app.post(
    "/urls",
    tags=["Data Preparation APIs"],
    summary="Upload URLs to create and store embeddings.",
    response_model=dict,
)
async def ingest_links(urls: list[str]) -> dict:
    """
    Ingest documents into the system.

    Args:
        urls (list[str]): An URL or multiple URLs to be ingested.

    Returns:
        dict: A status message indicating the result of the ingestion.
    """
    try:
        if not urls:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail="No URLs provided for ingestion."
            )

        result = ingest_url_to_pgvector(urls)

        return {
            "status": 200,
            "message": f"Data preparation completed: {result['successful']}/{result['total_urls']} URLs succeeded",
        }

    except HTTPException as e:
        raise

    except Exception as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))


@app.delete(
    "/urls",
    tags=["Data Preparation APIs"],
    summary="Delete embeddings and associated URLs from VectorDB",
    status_code=HTTPStatus.NO_CONTENT,
)
async def delete_urls(
    url: Optional[str] = None, delete_all: Optional[bool] = False
) -> None:
    """
    Delete a URL or all URLs from storage and their embeddings from Vector DB.

    Args:
        url (str): URL to be deleted

    Returns:
        response (dict): A status message indicating the result of the deletion.
    """

    try:
        # Check if the tables exist
        if not check_tables_exist():
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="There are no embeddings created yet.",
            )

        # Delete embeddings from Vector DB
        if not await delete_embeddings_url(url, delete_all):
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Failed to delete URL embeddings from vector database.")

    except ValueError as err:
        logger.error(f"Error: {err}")
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(err)
        )

    except AssertionError:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Failed to delete embeddings from the database."
        )

    except HTTPException as e:
        raise e

    except Exception as ex:
        logger.error(f"Internal error: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Internal Server Error"

        )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)