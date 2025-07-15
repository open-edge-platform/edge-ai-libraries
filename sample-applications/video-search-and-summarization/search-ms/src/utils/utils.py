# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import re
import time
from urllib.parse import urlparse

import requests
from src.utils.common import logger, settings

uploaded_files = set()


def sanitize_file_path(file_path):
    file_name = os.path.basename(file_path)
    sanitized_name = re.sub(r"[^a-zA-Z0-9_\-./]", "_", file_name)
    return sanitized_name


def should_use_no_proxy(url: str) -> bool:
    no_proxy = settings.no_proxy_env
    hostname = urlparse(url).hostname
    logger.debug(
        f"Checking no_proxy for hostname: {hostname} against no_proxy domains: {no_proxy}"
    )
    if hostname:
        for domain in no_proxy.split(","):
            if hostname.endswith(domain):
                logger.debug(f"Hostname {hostname} matches no_proxy domain {domain}")
                return True
    logger.debug(f"Hostname {hostname} does not match any no_proxy domains")
    return False


def upload_single_video_with_retry(file_path, max_retries=3):
    """Upload a single video with retry mechanism"""
    retry_count = 1
    sanitized_name = sanitize_file_path(file_path)

    while retry_count < max_retries:
        try:
            with open(file_path, "rb") as file:
                use_no_proxy = should_use_no_proxy(settings.VIDEO_UPLOAD_ENDPOINT)
                logger.debug(
                    f"Using no_proxy: {use_no_proxy} for URL: {settings.VIDEO_UPLOAD_ENDPOINT}"
                )

                # Step 1: Upload video to get ID
                upload_response = requests.post(
                    f"{settings.VIDEO_UPLOAD_ENDPOINT}/videos",
                    files={"video": (sanitized_name, file, "video/mp4")},
                    proxies=(
                        None
                        if use_no_proxy
                        else {
                            "http": settings.http_proxy,
                            "https": settings.https_proxy,
                        }
                    ),
                )
                upload_response.raise_for_status()

                # Extract video ID from response
                video_data = upload_response.json()
                video_id = video_data.get("videoId")
                if not video_id:
                    raise ValueError("No video ID returned from upload")

                logger.info(
                    f"Successfully uploaded {file_path}, received ID: {video_id}"
                )

                # Step 2: Process video for search embeddings
                embedding_response = requests.post(
                    f"{settings.VIDEO_UPLOAD_ENDPOINT}/videos/search-embeddings/{video_id}",
                    proxies=(
                        None
                        if use_no_proxy
                        else {
                            "http": settings.http_proxy,
                            "https": settings.https_proxy,
                        }
                    ),
                )
                embedding_response.raise_for_status()

                logger.info(
                    f"Successfully processed {file_path} for search embeddings."
                )
                return True  # Successfully processed
        except (requests.exceptions.HTTPError, Exception) as e:
            retry_count += 1

            # Determine if we should retry or exit
            if retry_count > max_retries:
                # Log error with additional context for HTTP errors
                if isinstance(e, requests.exceptions.HTTPError):
                    status_code = (
                        e.response.status_code if hasattr(e, "response") else "unknown"
                    )
                    logger.error(
                        f"HTTP error {status_code} occurred while processing {file_path} after {max_retries} retries: {str(e)}"
                    )
                else:
                    logger.error(
                        f"Error occurred while processing {file_path} after {max_retries} retries: {str(e)}"
                    )
                return False

            # Calculate backoff time and retry
            backoff_time = 2**retry_count  # Exponential backoff 2,4,8,...
            error_type = (
                "HTTP error"
                if isinstance(e, requests.exceptions.HTTPError)
                else "Error"
            )
            logger.warning(
                f"{error_type} on attempt {retry_count}/{max_retries} for {file_path}: {str(e)}. Retrying in {backoff_time} seconds..."
            )
            time.sleep(backoff_time)

    # This should never be reached due to the return statements above, but adding as a safety measure
    return False


def upload_videos_to_dataprep(file_paths):
    all_success = True
    for file_path in file_paths:
        if file_path in uploaded_files:
            continue

        success = upload_single_video_with_retry(file_path)

        if success:
            uploaded_files.add(file_path)
            if settings.DELETE_PROCESSED_FILES:
                os.remove(file_path)
                logger.info(f"Deleted processed file {file_path}")
        else:
            all_success = False

    return all_success
