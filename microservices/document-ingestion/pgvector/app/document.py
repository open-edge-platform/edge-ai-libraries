# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import psycopg
from fastapi import UploadFile, HTTPException
from http import HTTPStatus
from pathlib import Path
from typing import Optional
from langchain_community.document_loaders import UnstructuredFileLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_postgres.vectorstores import PGVector
from .logger import logger
from .config import Settings
from .db_config import pool_execution
from .utils import get_separators

config = Settings()

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
    temp_path = Path(config.LOCAL_STORE_PREFIX) / bucket_name / filename
    if not temp_path.parent.exists():
        temp_path.parent.mkdir(parents=True, exist_ok=True)

    # Read the uploaded file and save it at temp location
    with temp_path.open("wb") as fout:
        try:
            await file.seek(0)
            content = await file.read()
            fout.write(content)
        except Exception as ex:
            logger.error(f"Error while saving file : {ex}")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"Write file {temp_path} failed."
            )

    return temp_path


async def get_documents_embeddings() -> list:
    """
    Retrieves a list of document embeddings from the database, including file names and bucket names.
    This function queries the database to fetch distinct file sources and bucket names
    associated with a specific index name. The results are processed to extract the file
    names and bucket names, which are returned as a list of dictionaries.

    Returns:
        list: A list of dictionaries, where each dictionary contains:
            - file_name (str): The name of the file extracted from the source path.
            - bucket_name (str): The name of the bucket associated with the file.

    Raises:
        Exception: If there is an issue with the database query or execution.
    """

    file_list = []
    query = "SELECT DISTINCT \
    lpc.cmetadata ->> 'source' as source, lpc.cmetadata ->> 'bucket' as bucket \
    FROM \
    langchain_pg_embedding lpc JOIN langchain_pg_collection lpcoll \
    ON lpc.collection_id = lpcoll.uuid WHERE lpcoll.name = %(index_name)s \
    AND lpc.cmetadata ->> 'source' IS NOT NULL \
    AND lpc.cmetadata ->> 'bucket' IS NOT NULL"

    params = {"index_name": config.INDEX_NAME}
    result_rows = pool_execution(query, params)

    # Extract bucket name and filenames from returned query result
    file_list = [
        {"file_name": row[0].split("/")[-1], "bucket_name": row[1]} for row in result_rows
    ]

    return file_list


def ingest_to_pgvector(doc_path: Path, bucket: str):
    """
    Ingests a document into a PostgreSQL database with PGVector extension for vector embeddings.
    This function processes a document, splits it into chunks, generates embeddings for each chunk,
    and uploads the embeddings to a PGVector collection in batches.

    Args:
        doc_path (Path): The file path to the document to be ingested.
        bucket (str): The name of the bucket associated with the document metadata.

    Raises:
        HTTPException: If no text is found in the document or if an error occurs during ingestion.
    """


    try:
        if doc_path.suffix.lower() == ".pdf":
            loader = PyPDFLoader(doc_path)
        else:
            loader = UnstructuredFileLoader(doc_path, mode="paged", strategy="fast")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP, add_start_index=True,separators=get_separators()
        )

        chunks = loader.load_and_split(text_splitter)
        if not chunks:
            raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="No text found in the document for ingestion.")

        documents = [
            Document(
                page_content=chunk.page_content,
                metadata={"bucket": bucket, "filename": doc_path.name, **chunk.metadata},
            )
            for chunk in chunks
        ]

        embedder = OpenAIEmbeddings(
            openai_api_key="EMPTY",
            openai_api_base="{}".format(config.TEI_ENDPOINT_URL),
            model=config.EMBEDDING_MODEL_NAME,
            tiktoken_enabled=False
        )

        # Batch upload documents to handle large files
        batch_size = config.BATCH_SIZE
        for i in range(0, len(documents), batch_size):
            batch_documents = documents[i : i + batch_size]

            _ = PGVector.from_documents(
                documents=batch_documents,
                embedding=embedder,
                collection_name=config.INDEX_NAME,
                connection=config.PG_CONNECTION_STRING,
                use_jsonb=True
            )

            logger.info(
                f"Processed batch {i // batch_size + 1}/{(len(documents) - 1) // batch_size + 1}"
            )

    except HTTPException as e:
        raise e

    except Exception as e:
        logger.error(f"Error during ingestion: {e}")
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Internal Server Error")


async def delete_embeddings(
    bucket_name: str, file_name: Optional[str], delete_all: bool = False
) -> bool:
    """
    Deletes embeddings from the database based on the specified criteria.
    If `delete_all` is True, all embeddings associated with the given bucket
    will be deleted. If `delete_all` is False, a `file_name` must be provided,
    and only embeddings associated with the specified file in the given bucket
    will be deleted.

    Args:
        bucket_name (str): The name of the bucket containing the embeddings.
        file_name (Optional[str]): The name of the file whose embeddings are to
            be deleted. Required if `delete_all` is False.
        delete_all (bool): Flag indicating whether to delete all embeddings
            in the specified bucket. Defaults to False.

    Returns:
        bool: True if the embeddings were successfully deleted, False otherwise.

    Raises:
        ValueError: If `delete_all` is False and `file_name` is not provided.
        HTTPException: If a database error occurs or an internal server error
            is encountered.
    """
    try:
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
            params = {"indexname": config.INDEX_NAME, "bucket": bucket_name}

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
                "indexname": config.INDEX_NAME,
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