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
                use_no_proxy = should_use_no_proxy(settings.DATAPREP_UPLOAD_URL)
                logger.debug(
                    f"Using no_proxy: {use_no_proxy} for URL: {settings.DATAPREP_UPLOAD_URL}"
                )
                response = requests.post(
                    settings.DATAPREP_UPLOAD_URL,
                    files={"files": (sanitized_name, file, "video/mp4")},
                    data={
                        "chunk_duration": settings.CHUNK_DURATION,
                        "clip_duration": settings.CHUNK_DURATION,
                    },
                    proxies=(
                        None
                        if use_no_proxy
                        else {
                            "http": settings.http_proxy,
                            "https": settings.https_proxy,
                        }
                    ),
                )
                response.raise_for_status()
                uploaded_files.add(file_path)
                logger.info(f"Successfully uploaded {file_path} to data-prep service.")
                if settings.DELETE_PROCESSED_FILES:
                    os.remove(file_path)
                    logger.info(f"Deleted processed file {file_path}")
        except requests.exceptions.HTTPError as http_err:
            all_success = False
            if response.status_code == 422:
                logger.error(
                    f"Failed to upload {file_path} to data-prep service: {response.status_code} Client Error: Unprocessable Entity for url: {response.url}"
                )
            else:
                logger.error(f"HTTP error occurred: {http_err}")
        except Exception as e:
            all_success = False
            logger.error(f"Failed to upload {file_path} to data-prep service: {str(e)}")
    return all_success
