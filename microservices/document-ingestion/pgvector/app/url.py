# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import requests
import psycopg
import ipaddress
import socket
import os
from fnmatch import fnmatch
from urllib.parse import urlparse
from http import HTTPStatus
from fastapi import HTTPException
from typing import List, Optional
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_postgres.vectorstores import PGVector
from .logger import logger
from .config import Settings
from .db_config import pool_execution
from .utils import get_separators, parse_html_content
import idna

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


def is_public_ip(ip: str) -> bool:
    """
    Determines whether the given IP address is a public (global) IP address.
    Args:
        ip (str): The IP address to check.
    Returns:
        bool: True if the IP address is public (global), False if it is private, loopback,
              link-local, reserved, multicast, unspecified, or invalid.
    """

    try:
        ip_obj = ipaddress.ip_address(ip)

        return (
            ip_obj.is_global
            and not ip_obj.is_private
            and not ip_obj.is_loopback
            and not ip_obj.is_link_local
            and not ip_obj.is_reserved
            and not ip_obj.is_multicast
            and not ip_obj.is_unspecified
        )

    except ValueError:
        return False


def validate_url(url: str) -> bool:
    """
    Validates a given URL based on scheme, canonical hostname, IP resolution, and allowed hosts, and prevents DNS rebinding attacks and encoding tricks.

    Args:
        url (str): The URL to validate.

    Returns:
        bool: True if the URL is valid, False otherwise.
    """
    try:
        # Remove leading/trailing whitespace and control chars from the URL
        url_cleaned = url.strip().replace('\r', '').replace('\n', '')

        # Parse the cleaned URL
        parsed_url = urlparse(url_cleaned)
        # Ensure the URL are secure (https only)
        if parsed_url.scheme != "https":
            return False

        hostname = parsed_url.hostname
        if not hostname:
            return False

        # Normalize the hostname: lower-case, strip trailing dot, and apply IDNA encoding
        normalized_hostname = hostname.lower().rstrip('.').strip()
        try:
            normalized_hostname = idna.encode(normalized_hostname).decode("utf-8")
        except idna.IDNAError:
            logger.error(f"Invalid IDNA encoding for hostname: {hostname}")
            return False

        # Check against the allowed hosts domains
        allowed_domains = [d.lower().rstrip('.') for d in config.ALLOWED_DOMAINS] if config.ALLOWED_DOMAINS else []
        if not allowed_domains:
            logger.error("No ALLOWED_DOMAINS configured; refusing all URLs to prevent SSRF.")
            return False

        # Check if hostname matches allowed domains (supports wildcards like *.example.com)
        if not any(fnmatch(normalized_hostname, pattern) for pattern in allowed_domains):
            logger.info(f"URL hostname {normalized_hostname} is not in the whitelisted domains {allowed_domains}.")
            return False

        # Resolve ALL IPs for the hostname
        try:
            infos = socket.getaddrinfo(normalized_hostname, None)
            resolved_ips = {info[4][0] for info in infos}
        except (socket.gaierror, socket.error) as e:
            logger.error(f"DNS resolution failed for {normalized_hostname}: {e}")
            return False

        # Ensure the resolved IP is public
        for ip in resolved_ips:
            if not is_public_ip(ip):
                logger.warning(f"Non-public IP blocked: {ip} for host {normalized_hostname}")
                return False

        return True

    except Exception as e:
        logger.error(f"URL validation failed: {e}")
        return False

def safe_fetch_url(validated_url: str, headers: dict):
    """
    Securely fetches a URL while mitigating SSRF vulnerabilities.

    This function uses the validated URL for the request. Redirects are disabled
    to prevent redirect-based SSRF attacks.

    Args:
        validated_url (str): The validated and pinned URL.
        headers (dict): A dictionary of HTTP headers to include in the request.

    Returns:
        Response: The HTTP response object from the `requests` library.

    Raises:
        ValueError: If the URL is invalid or DNS resolution fails.
        requests.RequestException: For any issues during the HTTP request.
    """

    # Send the request to the validated URL to prevent SSRF
    response = requests.get(
        validated_url,
        headers=headers,
        timeout=5,
        allow_redirects=False,  # prevent redirect SSRF
        verify=True  # enforce SSL verification
    )

    return response

def ingest_url_to_pgvector(url_list: List[str]) -> dict:
    """
    Securely ingests URLs into PGVector.
    SECURITY INVARIANT:
    - Exactly ONE fetch per URL
    - All network access goes through safe_fetch_url
    """

    default_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/117.0.0.0 Safari/537.36"
    )

    headers = {
        "User-Agent": os.getenv("USER_AGENT_HEADER", default_user_agent)
    }

    # Initialize text splitter and embedder once
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        add_start_index=True,
        separators=get_separators(),
    )

    embedder = OpenAIEmbeddings(
        openai_api_key="EMPTY",
        openai_api_base=str(config.TEI_ENDPOINT_URL),
        model=config.EMBEDDING_MODEL_NAME,
        tiktoken_enabled=False,
    )

    invalid_urls = 0

    for url in url_list:
        try:
            # Validate URL
            if not validate_url(url):
                logger.info(f"Invalid URL skipped: {url}")
                invalid_urls += 1
                continue

            # Fetch ONCE (safe)
            response = safe_fetch_url(url, headers)

            if response.status_code != HTTPStatus.OK:
                logger.info(f"Fetch failed {url}: {response.status_code}")
                invalid_urls += 1
                continue

            # Parse HTML from fetched content (NO re-fetch!)
            content = parse_html_content(response.text, url)

            if not content.strip():
                logger.info(f"No parsable content for {url}")
                invalid_urls += 1
                continue

            # Chunk + embed
            chunks = text_splitter.split_text(content)
            metadata = [{"url": url}] * len(chunks)
            batch_size = config.BATCH_SIZE

            for i in range(0, len(chunks), batch_size):
                batch_texts = chunks[i : i + batch_size]
                batch_metadata = metadata[i : i + batch_size]

                PGVector.from_texts(
                    texts=batch_texts,
                    embedding=embedder,
                    metadatas=batch_metadata,
                    collection_name=config.INDEX_NAME,
                    connection=config.PG_CONNECTION_STRING,
                    use_jsonb=True,
                )

                logger.info(
                    f"Processed batch {i // batch_size + 1}/"
                    f"{(len(chunks) - 1) // batch_size + 1} for {url}"
                )

        except requests.exceptions.SSLError as e:
            logger.error(f"SSL Error while fetching {url}: {e}")
            invalid_urls += 1
            continue

        except Exception as e:
            logger.exception(f"Error ingesting URL {url}")
            invalid_urls += 1
            continue

    if invalid_urls == len(url_list):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                f"All URLs failed ingestion. "
                f"Invalid: {invalid_urls}/{len(url_list)}. "
            ),
        )
    
    return {
    "total_urls": len(url_list),
    "successful": len(url_list) - invalid_urls,
    "failed": invalid_urls,
    }


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