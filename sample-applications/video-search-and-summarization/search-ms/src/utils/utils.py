# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import re
import time
from urllib.parse import urlparse

import requests
from src.utils.common import logger, settings

uploaded_files = set()
TERMINAL_BATCH_STATES = {
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
}


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


def request_proxies(url: str):
    """Return the configured proxies unless the URL matches ``no_proxy``."""
    if should_use_no_proxy(url):
        return None
    return {
        "http": settings.http_proxy,
        "https": settings.https_proxy,
    }


def upload_single_video_with_retry(file_path, max_retries=3):
    """Upload one video through Pipeline Manager and return its video ID."""
    sanitized_name = sanitize_file_path(file_path)

    for attempt in range(1, max_retries + 1):
        try:
            with open(file_path, "rb") as file:
                upload_response = requests.post(
                    f"{settings.VIDEO_UPLOAD_ENDPOINT}/videos",
                    files={"video": (sanitized_name, file, "video/mp4")},
                    proxies=request_proxies(settings.VIDEO_UPLOAD_ENDPOINT),
                )
                upload_response.raise_for_status()

                video_data = upload_response.json()
                video_id = video_data.get("videoId")
                if not video_id:
                    raise ValueError("No video ID returned from upload")

                logger.info(
                    f"Successfully uploaded {file_path}, received ID: {video_id}"
                )
                return video_id
        except Exception as e:
            if attempt == max_retries:
                if isinstance(e, requests.exceptions.HTTPError):
                    status_code = (
                        e.response.status_code
                        if getattr(e, "response", None) is not None
                        else "unknown"
                    )
                    logger.error(
                        f"HTTP error {status_code} occurred while processing {file_path} after {max_retries} retries: {str(e)}"
                    )
                else:
                    logger.error(
                        f"Error occurred while processing {file_path} after {max_retries} retries: {str(e)}"
                    )
                return None

            backoff_time = 2**attempt
            error_type = (
                "HTTP error"
                if isinstance(e, requests.exceptions.HTTPError)
                else "Error"
            )
            logger.warning(
                f"{error_type} on attempt {attempt}/{max_retries} for {file_path}: {str(e)}. Retrying in {backoff_time} seconds..."
            )
            time.sleep(backoff_time)

    return None


def submit_embedding_batch(video_ids, max_retries=3):
    """Submit one Pipeline Manager batch that delegates to DataPrep."""
    endpoint = f"{settings.VIDEO_UPLOAD_ENDPOINT}/videos/search-embeddings-batch"
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                endpoint,
                json={"videoIds": video_ids},
                proxies=request_proxies(endpoint),
            )
            response.raise_for_status()
            body = response.json()
            job_id = body.get("job_id")
            if not job_id:
                raise ValueError("No job_id returned from batch submission")
            logger.info(
                "Submitted %d videos for batch embedding, job ID: %s",
                len(video_ids),
                job_id,
            )
            return job_id
        except Exception as e:
            if attempt == max_retries:
                logger.error(
                    "Failed to submit embedding batch after %d attempts: %s",
                    max_retries,
                    str(e),
                )
                return None
            backoff_time = 2**attempt
            logger.warning(
                "Embedding batch submission failed on attempt %d/%d: %s. Retrying in %d seconds...",
                attempt,
                max_retries,
                str(e),
                backoff_time,
            )
            time.sleep(backoff_time)
    return None


def wait_for_embedding_batch(job_id):
    """Poll Pipeline Manager until a DataPrep batch job reaches a terminal state."""
    endpoint = (
        f"{settings.VIDEO_UPLOAD_ENDPOINT}/videos/search-embeddings-jobs/{job_id}"
    )
    deadline = time.monotonic() + settings.BATCH_JOB_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        try:
            response = requests.get(
                endpoint,
                proxies=request_proxies(endpoint),
            )
            response.raise_for_status()
            status = response.json()
            state = status.get("state")
            if state in TERMINAL_BATCH_STATES:
                logger.info("Embedding batch %s finished with state %s", job_id, state)
                return status
        except Exception as e:
            logger.warning("Failed to poll embedding batch %s: %s", job_id, str(e))

        time.sleep(settings.BATCH_JOB_POLL_INTERVAL_SECONDS)

    logger.error(
        "Timed out after %.1f seconds waiting for embedding batch %s",
        settings.BATCH_JOB_TIMEOUT_SECONDS,
        job_id,
    )
    return None


def upload_videos_to_dataprep(file_paths):
    """Upload files through Pipeline Manager and embed them as one DataPrep batch.

    Returns the paths that completed successfully. Pipeline Manager remains the
    upload system of record; its batch endpoint delegates the stored videos to
    DataPrep's asynchronous ``/media/process/batch`` API.
    """
    requested_paths = list(file_paths)
    previously_uploaded_paths = {
        path for path in requested_paths if path in uploaded_files
    }
    successful_paths = set(previously_uploaded_paths)
    video_paths_by_id = {}

    for file_path in requested_paths:
        if file_path in uploaded_files:
            continue
        video_id = upload_single_video_with_retry(file_path)
        if video_id:
            video_paths_by_id[video_id] = file_path

    video_ids = list(video_paths_by_id)
    for start in range(0, len(video_ids), settings.WATCH_BATCH_SIZE):
        batch_ids = video_ids[start : start + settings.WATCH_BATCH_SIZE]
        job_id = submit_embedding_batch(batch_ids)
        status = wait_for_embedding_batch(job_id) if job_id else None
        if not status:
            continue
        for item in status.get("items", []):
            if item.get("status") != "success":
                logger.error(
                    "Batch embedding failed for %s: %s",
                    item.get("identifier", "unknown item"),
                    item.get("message", "unknown error"),
                )
                continue
            video_id = item.get("video_id") or item.get("identifier")
            file_path = video_paths_by_id.get(video_id)
            if file_path:
                successful_paths.add(file_path)

    for file_path in successful_paths:
        uploaded_files.add(file_path)
        if (
            file_path not in previously_uploaded_paths
            and settings.DELETE_PROCESSED_FILES
            and os.path.exists(file_path)
        ):
            os.remove(file_path)
            logger.info(f"Deleted processed file {file_path}")

    failed_count = len(requested_paths) - len(successful_paths)
    if failed_count:
        logger.error(
            "%d of %d watched videos failed ingestion",
            failed_count,
            len(requested_paths),
        )
    return successful_paths
