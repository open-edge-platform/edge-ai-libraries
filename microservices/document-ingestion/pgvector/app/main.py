# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import requests
import psycopg
from requests.exceptions import HTTPError
from http import HTTPStatus
from pathlib import Path
from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel
from typing import Annotated, List, Optional
from fastapi.middleware.cors import CORSMiddleware
from .logger import logger
from .config import Settings
from .db_config import get_db_connection_pool
from .document import get_documents_embeddings, ingest_to_pgvector, save_temp_file, delete_embeddings
from .url import get_urls_embedding, ingest_url_to_pgvector, delete_embeddings_url
from .utils import check_tables_exist

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


class DocumentIn(BaseModel):
    file_name: str


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

                # Upload files to Data Store Service
                try:
                    file_tuple = (file.filename, file.file, file.content_type)
                    response = requests.post(
                        config.DATASTORE_DATA_ENDPOINT, files={"file": file_tuple}
                    )
                    response.raise_for_status()
                    result = response.json()
                    uploaded_filename = result["files"][0]
                    bucket_name = result["bucket_name"]
                except HTTPError as ex:
                    logger.error(f"HTTP Error while hitting DataStore : {ex}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Some error ocurred at Data Storage Service. Please try later!",
                    )
                except Exception as ex:
                    logger.error(f"Internal Error: {ex}")
                    raise HTTPException(
                        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                        detail="Some unknown error ocurred. Please try later!",
                    )
                else:
                    logger.info(
                        f"file: {file.filename} uploaded to DataStore successfully!"
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
    bucket_name: str, file_name: Optional[str] = None, delete_all: bool = False
) -> None:
    """
    Delete a document or all documents from storage and their embeddings from Vector DB.

    Args:
        bucket_name (str): Bucket name where file to be deleted is stored
        filename(str): Name of file to be deleted
        file_path (str): The path of the file to delete, or "all" to delete all files.

    Returns:
        response (dict): A status message indicating the result of the deletion.
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
            raise HTTPException(status_code=500, detail="Failed to delete embeddings from vector database.")

        # Delete files or bucket from object store as requested.
        delete_req = {
            "bucket_name": bucket_name,
            "file_name": file_name,
            "delete_all": delete_all,
        }

        response = requests.delete(config.DATASTORE_DATA_ENDPOINT, params=delete_req)
        response.raise_for_status()

    except HTTPError as ex:
        logger.error(f"Error while hitting DataStore : {ex}")
        # Display error message from DataStore only if it is because of request error.
        # Do not display error messages for internal errors.
        result = response.json()
        if result and response.status_code < 500:
            error_msg = result["message"]
        else:
            error_msg = "Some error occurred at Data Storage Service!"

        raise HTTPException(status_code=response.status_code, detail=error_msg)

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
        if urls:
            ingest_url_to_pgvector(urls)

        result = {"status": 200, "message": "Data preparation succeeded"}
        return result

    except HTTPException as e:
        raise e
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
    Delete a document or all documents from storage and their embeddings from Vector DB.

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
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
