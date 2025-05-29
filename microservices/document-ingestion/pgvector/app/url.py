# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import requests
import psycopg
from http import HTTPStatus
from fastapi import HTTPException
from typing import List, Optional
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_postgres.vectorstores import PGVector
from .logger import logger
from .config import Settings
from .db_config import pool_execution
from .utils import get_separators, parse_html

config = Settings()

async def get_urls_embedding() -> List[str]:
    """
    Retrieve a list of distinct URLs from the database based on the specified index name.
    This function executes a SQL query to fetch distinct URLs from the `langchain_pg_embedding`
    table by joining it with the `langchain_pg_collection` table. The URLs are filtered based
    on the collection name specified in the configuration.

    Returns:
        List[str]: A list of distinct URLs retrieved from the database.
    """

    url_list = []
    query = "SELECT DISTINCT \
    lpc.cmetadata ->> 'url' as url FROM \
    langchain_pg_embedding lpc JOIN langchain_pg_collection lpcoll \
    ON lpc.collection_id = lpcoll.uuid WHERE lpcoll.name = %(index_name)s"

    params = {"index_name": config.INDEX_NAME}
    result_rows = pool_execution(query, params)

    url_list = [row[0] for row in result_rows if row[0]]

    return url_list


def ingest_url_to_pgvector(url_list: List[str]) -> None:
    """
    Ingests a list of URLs into a PGVector database by fetching their content,
    splitting it into chunks, generating embeddings, and storing them.

    Args:
        url_list (List[str]): A list of URLs to be ingested.

    Raises:
        HTTPException: If there are issues with SSL, HTTP response status,
            HTML parsing, or any other errors during the ingestion process.
    """


    try:
        invalid_urls = 0
        for url in url_list:
            response = requests.get(url, timeout=5, allow_redirects=True)
            if response.status_code != 200:
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
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
            add_start_index=True,
            separators=get_separators(),
        )

        embedder = OpenAIEmbeddings(
            openai_api_key="EMPTY",
            openai_api_base="{}".format(config.TEI_ENDPOINT_URL),
            model=config.EMBEDDING_MODEL_NAME,
            tiktoken_enabled=False
        )

        for url in url_list:
            try:
                content = parse_html(
                    [url], chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
                )
            except Exception as e:
                logger.error(f"Error while parsing HTML content for URL - {url}: {e}")
                raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"Error while parsing URL")

            logger.info(f"[ ingest url ] url: {url} content: {content}")
            metadata = [{"url": url}]

            chunks = text_splitter.split_text(content)
            batch_size = config.BATCH_SIZE

            for i in range(0, len(chunks), batch_size):
                batch_texts = chunks[i : i + batch_size]

                _ = PGVector.from_texts(
                    texts=batch_texts,
                    embedding=embedder,
                    metadatas=metadata,
                    collection_name=config.INDEX_NAME,
                    connection=config.PG_CONNECTION_STRING,
                    use_jsonb=True
                )

                logger.info(
                    f"Processed batch {i // batch_size + 1}/{(len(chunks) - 1) // batch_size + 1}"
                )

    except Exception as e:
        logger.error(f"Error during ingestion : {e}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=f"Error during URL ingestion to PGVector."
        )


async def delete_embeddings_url(url: Optional[str], delete_all: bool = False) -> bool:
    """
    Deletes embeddings from the database based on the provided URL or deletes all embeddings.

    Args:
        url (Optional[str]): The URL whose embeddings should be deleted. Required if `delete_all` is False.
        delete_all (bool): If True, deletes embeddings for all URLs in the database. Defaults to False.

    Returns:
        bool: True if the deletion was successful, False otherwise.

    Raises:
        HTTPException: If no URLs are present in the database when `delete_all` is True.
        ValueError: If the provided URL does not exist in the database or if invalid arguments are provided.
        HTTPException: If a database error occurs during the operation.
    """


    try:
        url_list = await get_urls_embedding()

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

            params = {"indexname": config.INDEX_NAME}

        elif url:
            if url not in url_list:
                raise ValueError(f"URL {url} does not exist in the database.")
            else:
                query = "DELETE FROM \
                langchain_pg_embedding WHERE \
                collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = %(indexname)s) \
                AND cmetadata ->> 'url' = %(link)s"

                params = {"indexname": config.INDEX_NAME, "link": url}

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