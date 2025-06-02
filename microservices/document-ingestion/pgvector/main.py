# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import requests
import psycopg
import logging
import ipaddress
from urllib.parse import urlparse
import socket
from requests.exceptions import HTTPError
from http import HTTPStatus
from pathlib import Path
from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel
from typing import Annotated, List, Optional
from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    INDEX_NAME,
    PG_CONNECTION_STRING,
    SUPPORTED_FORMATS,
    TEI_ENDPOINT,
    DATASTORE_DATA_ENDPOINT,
    LOCAL_STORE_PREFIX,
    APP_TITLE,
    APP_DESC,
    BATCH_SIZE,
    EMBEDDING_MODEL_NAME,
    ALLOWED_HOSTS
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import UnstructuredFileLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_postgres.vectorstores import PGVector
from db_config import get_db_connection_pool, pool_execution
from fastapi.middleware.cors import CORSMiddleware

from utils import get_separators, parse_html


logging.basicConfig(
    format="%(asctime)s: %(name)s: %(levelname)s: %(message)s", level=logging.INFO
)
app = FastAPI(title=APP_TITLE, description=APP_DESC, root_path="/v1/dataprep")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(
        ","
    ),  # Adjust this to your needs
    allow_credentials=True,
    allow_methods=os.getenv("CORS_ALLOW_METHODS", "*").split(","),
    allow_headers=os.getenv("CORS_ALLOW_HEADERS", "*").split(","),
)


class DocumentIn(BaseModel):
    file_name: str


pool = get_db_connection_pool()


async def save_temp_file(file: UploadFile, bucket_name: str, filename: str) -> str:
    """Reads the uploaded file and saves it at a temporary location.

    Args:
        file (UploadFile): The uploaded file received at Fastapi route
        bucket_name (string): Name of the bucket in the datastore service
        filename (string): Name of the file being uploaded to datastore service

    Returns:
        temp_path (pathlib.Path): Path object for the location where file is saved temporarily
    """

    # Get a location path in /tmp directory, based on bucketname and filename
    temp_path = Path(LOCAL_STORE_PREFIX) / bucket_name / filename
    if not temp_path.parent.exists():
        temp_path.parent.mkdir(parents=True, exist_ok=True)

    # Read the uploaded file and save it at temp location
    with temp_path.open("wb") as fout:
        try:
            await file.seek(0)
            content = await file.read()
            fout.write(content)
        except Exception as ex:
            logging.error(f"Error while saving file : {ex}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"Write file {temp_path} failed."
            )

    return temp_path


def check_tables_exist() -> bool:
    """Check if the required tables exist in the database."""
    check_tables_query = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'langchain_pg_embedding'
                ) AND EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'langchain_pg_collection'
                );
                """
    tables_exist = pool_execution(check_tables_query, {})
    return tables_exist[0][0]


def ingest_to_pgvector(doc_path: Path, bucket: str):
    """Ingest document to PGVector."""

    try:

        if doc_path.suffix.lower() == ".pdf":
            loader = PyPDFLoader(doc_path)
        else:
            loader = UnstructuredFileLoader(doc_path, mode="paged", strategy="fast")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True,separators=get_separators()
        )

        chunks = loader.load_and_split(text_splitter)
        if not chunks:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="No text found in the document for ingestion.")

        documents = [
            Document(
                page_content=chunk.page_content,
                metadata={"bucket": bucket, **chunk.metadata},
            )
            for chunk in chunks
        ]

        embedder = OpenAIEmbeddings(
            openai_api_key="EMPTY",
            openai_api_base="{}".format(TEI_ENDPOINT),
            model=EMBEDDING_MODEL_NAME,
            tiktoken_enabled=False
        )

        # Batch upload documents to handle large files
        batch_size = BATCH_SIZE
        for i in range(0, len(documents), batch_size):
            batch_documents = documents[i : i + batch_size]

            _ = PGVector.from_documents(
                documents=batch_documents,
                embedding=embedder,
                collection_name=INDEX_NAME,
                connection=PG_CONNECTION_STRING,
                use_jsonb=True
            )

            logging.info(
                f"Processed batch {i // batch_size + 1}/{(len(documents) - 1) // batch_size + 1}"
            )

    except HTTPException as e:
        raise e

    except Exception as e:
        logging.error(f"Error during ingestion: {e}")
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Internal Server Error")


def is_public_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_global  # True if public, False if private/reserved

    except ValueError:
        return False  # Invalid IPs are treated as non-public


def validate_url(url: str) -> bool:
    """Validate the URL against a whitelist and ensure it resolves to a public IP."""
    try:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ["http", "https"]:
            return False

        ip = socket.gethostbyname(parsed_url.hostname)
        if not is_public_ip(ip):
            return False

        # If ALLOWED_HOSTS is empty, allow all public URLS else check against ALLOWED_HOSTS
        if ALLOWED_HOSTS:
            if parsed_url.hostname not in ALLOWED_HOSTS:
                return False
        else:
            # If ALLOWED_HOSTS is empty, allow all public URLs
            return True
    except Exception:
        return False

def ingest_url_to_pgvector(url_list: List[str]) -> None:
    """Ingest URL to PGVector."""

    try:
        invalid_urls = 0
        for url in url_list:
            if validate_url(url):
                response = requests.get(url, timeout=5, allow_redirects=False)
                if response.status_code == 200:
                    continue
            invalid_urls += 1

        if invalid_urls > 0:
            raise Exception(
                f"{invalid_urls} / {len(url_list)} URL(s) are invalid.",
                response.status_code
            )

    # If the domain name is wrong, SSLError will be thrown
    except requests.exceptions.SSLError as e:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail=f"SSL Error: {str(e)}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=e.args[1], detail=e.args[0]
        )

    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            add_start_index=True,
            separators=get_separators(),
        )

        embedder = OpenAIEmbeddings(
            openai_api_key="EMPTY",
            openai_api_base="{}".format(TEI_ENDPOINT),
            model=EMBEDDING_MODEL_NAME,
            tiktoken_enabled=False
        )

        for url in url_list:
            try:
                content = parse_html(
                    [url], chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
                )
            except Exception as e:
                logging.error(f"Error while parsing HTML content for URL - {url}: {e}")
                raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"Error while parsing URL")

            logging.info(f"[ ingest url ] url: {url} content: {content}")
            metadata = [{"url": url}]

            chunks = text_splitter.split_text(content)
            batch_size = BATCH_SIZE

            for i in range(0, len(chunks), batch_size):
                batch_texts = chunks[i : i + batch_size]

                _ = PGVector.from_texts(
                    texts=batch_texts,
                    embedding=embedder,
                    metadatas=metadata,
                    collection_name=INDEX_NAME,
                    connection=PG_CONNECTION_STRING,
                    use_jsonb=True
                )

                logging.info(
                    f"Processed batch {i // batch_size + 1}/{(len(chunks) - 1) // batch_size + 1}"
                )

    except Exception as e:
        logging.error(f"Error during ingestion : {e}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"Error during URL ingestion to PGVector."
        )


async def delete_embeddings(
    bucket_name: str, file_name: Optional[str], delete_all: bool = False
) -> bool:
    """Delete embeddings for a given file or delete all embeddings."""

    try:
        # Check if the tables exist
        if not check_tables_exist():
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="There are no embeddings created yet.",
            )

        # If `delete_all` is True, embeddings for all files in given bucket will be deleted,
        # irrespective of whether a `file_name` is provided or not.
        if delete_all:
            query = """
            DELETE FROM langchain_pg_embedding WHERE EXISTS (
                SELECT * FROM langchain_pg_collection WHERE
                langchain_pg_embedding.collection_id = langchain_pg_collection.uuid AND
                langchain_pg_collection.name = %(indexname)s AND
                langchain_pg_embedding.cmetadata ->> 'bucket' = %(bucket)s
            )
            """
            params = {"indexname": INDEX_NAME, "bucket": bucket_name}

        elif file_name:
            query = """
            DELETE FROM langchain_pg_embedding WHERE EXISTS (
                SELECT 1 FROM langchain_pg_collection WHERE
                langchain_pg_embedding.collection_id = langchain_pg_collection.uuid AND
                langchain_pg_collection.name = %(indexname)s AND
                langchain_pg_embedding.cmetadata ->> 'filename' = %(filename)s AND
                langchain_pg_embedding.cmetadata ->> 'bucket' = %(bucket)s
            )
            """
            params = {
                "indexname": INDEX_NAME,
                "filename": file_name,
                "bucket": bucket_name,
            }

        else:
            raise ValueError(
                "Invalid Arguments: file_name is required if delete_all is False."
            )

        result = pool_execution(query, params)
        if result:
            return bool(result)
        else:
            raise ValueError(result)

    except psycopg.Error as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"PSYCOPG Error: {e}")

    except ValueError as e:
        raise e

    except HTTPException as e:
        raise e


async def delete_embeddings_url(url: Optional[str], delete_all: bool = False) -> bool:
    """Delete embeddings for a given URL or delete all embeddings."""

    try:
        # Check if the tables exist
        if not check_tables_exist():
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="There are no embeddings created yet.",
            )

        url_list = await get_urls()

        # If `delete_all` is True, embeddings for all urls will deleted,
        #  irrespective of whether a `url` is provided or not.
        if delete_all:
            if not url_list:
               raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="No URLs present in the database.",
            )

            query = "DELETE FROM \
            langchain_pg_embedding WHERE \
            collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = %(indexname)s) \
            AND cmetadata ? 'url'"

            params = {"indexname": INDEX_NAME}

        elif url:
            if url not in url_list:
                raise ValueError(f"URL {url} does not exist in the database.")
            else:
                query = "DELETE FROM \
                langchain_pg_embedding WHERE \
                collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = %(indexname)s) \
                AND cmetadata ->> 'url' = %(link)s"

                params = {"indexname": INDEX_NAME, "link": url}

        else:
            raise ValueError(
                "Invalid Arguments: url is required if delete_all is False."
            )

        result = pool_execution(query, params)
        if result:
            return True
        else:
            return False

    except psycopg.Error as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"PSYCOPG Error: {e}")

    except ValueError as e:
        raise e


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

        file_list = []
        query = "SELECT DISTINCT \
        lpc.cmetadata ->> 'source' as source, lpc.cmetadata ->> 'bucket' as bucket \
        FROM \
        langchain_pg_embedding lpc JOIN langchain_pg_collection lpcoll \
        ON lpc.collection_id = lpcoll.uuid WHERE lpcoll.name = %(index_name)s \
        AND lpc.cmetadata ->> 'source' IS NOT NULL \
        AND lpc.cmetadata ->> 'bucket' IS NOT NULL"

        params = {"index_name": INDEX_NAME}
        result_rows = pool_execution(query, params)

        # Extract bucket name and filenames from returned query result
        file_list = [
            {"file_name": row[0].split("/")[-1], "bucket_name": row[1]} for row in result_rows
        ]
        return file_list

    except psycopg.Error as err:
        logging.error(f"Error while fetching data from DB: {err}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Some error occured. Please try later!"
        )

    except ValueError as e:
        raise e

    except Exception as ex:
        logging.error(f"Internal error: {ex}")
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

        url_list = []
        query = "SELECT DISTINCT \
        lpc.cmetadata ->> 'url' as url FROM \
        langchain_pg_embedding lpc JOIN langchain_pg_collection lpcoll \
        ON lpc.collection_id = lpcoll.uuid WHERE lpcoll.name = %(index_name)s"

        params = {"index_name": INDEX_NAME}
        result_rows = pool_execution(query, params)

        url_list = [row[0] for row in result_rows if row[0]]
        return url_list

    except psycopg.Error as err:
        logging.error(f"Error while fetching data from DB: {err}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Some error occured. Please try later!"
        )

    except ValueError as e:
        raise e

    except Exception as ex:
        logging.error(f"Internal error: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Internal Server Error"
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
                if file_extension not in SUPPORTED_FORMATS:
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail=f"Unsupported file format: {file_extension}. Supported formats are: pdf, txt, docx",
                    )

                # Upload files to Data Store Service
                try:
                    file_tuple = (file.filename, file.file, file.content_type)
                    response = requests.post(
                        DATASTORE_DATA_ENDPOINT, files={"file": file_tuple}
                    )
                    response.raise_for_status()
                    result = response.json()
                    uploaded_filename = result["files"][0]
                    bucket_name = result["bucket_name"]
                except HTTPError as ex:
                    logging.error(f"HTTP Error while hitting DataStore : {ex}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Some error ocurred at Data Storage Service. Please try later!",
                    )
                except Exception as ex:
                    logging.error(f"Internal Error: {ex}")
                    raise HTTPException(
                        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                        detail="Some unknown error ocurred. Please try later!",
                    )
                else:
                    logging.info(
                        f"file: {file.filename} uploaded to DataStore successfully!"
                    )

                try:
                    # Save file in temporary file on disk to ingest it
                    temp_path: Path = await save_temp_file(
                        file, bucket_name, uploaded_filename
                    )
                    logging.info(f"Temporary path of saved file: {temp_path}")
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
                        logging.info("Temporary file cleaned up!")

        result = {"status": 200, "message": "Data preparation succeeded"}

        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e))


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

        # Delete embeddings from Vector DB
        if not await delete_embeddings(bucket_name, file_name, delete_all):
            raise HTTPException(status_code=500, detail="Failed to delete embeddings from vector database.")

        # Delete files or bucket from object store as requested.
        delete_req = {
            "bucket_name": bucket_name,
            "file_name": file_name,
            "delete_all": delete_all,
        }

        response = requests.delete(DATASTORE_DATA_ENDPOINT, params=delete_req)
        response.raise_for_status()

    except HTTPError as ex:
        logging.error(f"Error while hitting DataStore : {ex}")
        # Display error message from DataStore only if it is because of request error.
        # Do not display error messages for internal errors.
        result = response.json()
        if result and response.status_code < 500:
            error_msg = result["message"]
        else:
            error_msg = "Some error occurred at Data Storage Service!"

        raise HTTPException(status_code=response.status_code, detail=error_msg)

    except ValueError as err:
        logging.error(f"Error: {err}")
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
        logging.error(f"Internal error: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Internal Server Error"
        )


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
        # Delete embeddings from Vector DB
        if not await delete_embeddings_url(url, delete_all):
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Failed to delete URL embeddings from vector database.")

    except ValueError as err:
        logging.error(f"Error: {err}")
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
        logging.error(f"Internal error: {ex}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Internal Server Error"

        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000)
