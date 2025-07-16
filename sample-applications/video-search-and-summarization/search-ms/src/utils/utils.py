# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import re
import requests
from src.utils.common import settings, logger
from urllib.parse import urlparse

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


def upload_videos_to_dataprep(file_paths):
    all_success = True
    for file_path in file_paths:
        if file_path in uploaded_files:
            continue
        try:
            sanitized_name = sanitize_file_path(file_path)
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

                logger.info(f"Successfully uploaded {file_path}, received ID: {video_id}")

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

                uploaded_files.add(file_path)
                logger.info(f"Successfully processed {file_path} for search embeddings.")

                if settings.DELETE_PROCESSED_FILES:
                    os.remove(file_path)
                    logger.info(f"Deleted processed file {file_path}")

        except requests.exceptions.HTTPError as http_err:
            all_success = False
            if hasattr(http_err, "response") and http_err.response.status_code == 422:
                logger.error(
                    f"Failed to process {file_path}: {http_err.response.status_code} Client Error: Unprocessable Entity for url: {http_err.response.url}"
                )
            else:
                logger.error(
                    f"HTTP error occurred while processing {file_path}: {http_err}"
                )
        except Exception as e:
            all_success = False
            logger.error(f"Failed to process {file_path}: {str(e)}")
    return all_success
