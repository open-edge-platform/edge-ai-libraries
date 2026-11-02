# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Centralized user-facing strings (messages, errors) used across the service."""


class Strings:
    """Namespace of constant message strings referenced throughout the service."""

    server_error: str = "Some error ocurred at API server. Please try later!"
    format_error: str = "Only .mp4 file is supported."
    video_open_error: str = "Error: Could not open video file."
    datastore_error: str = "Some error ocurred at DataStore Service. Please try later!"
    minio_error: str = "Some error ocurred while accessing the Minio storage. Please try later!"
    minio_conn_error: str = "Error connecting to Minio object storage."
    minio_file_not_found: str = "Video file not found in Minio storage."
    video_id_not_found: str = "No video found for the specified video ID."
    embedding_success: str = "Embeddings for the video file(s) were created successfully."
    text_embedding_success: str = "Text embedding was created successfully."
    config_error: str = "Some error ocurred while reading the config file."
    metadata_read_error: str = "Error ocurred while reading metadata file."
    db_conn_error: str = "Error ocurred while initializing connection with VDMS vector DB."
    embedding_error: str = "Error occurred while trying to create embeddings."
    text_validation_error: str = "Invalid text or video timestamp parameters."
    invalid_time_range: str = "End time must be greater than start time."
    range_not_satisfiable: str = "Requested range is not satisfiable."
    vdms_client_error: str = "Error occurred while initializing VDMS client."
    batch_accepted: str = "Batch ingestion job accepted and is being processed."
    batch_job_not_found: str = "No batch job found for the specified job ID."
    batch_empty: str = "No videos were provided or found to process."
    batch_too_large: str = "Batch size exceeds the maximum allowed items."
    ingest_dir_not_found: str = "The requested ingest directory was not found."
    ingest_file_not_found: str = "The referenced media file was not found under the ingest data root."
    ingest_path_invalid: str = "The requested path is outside the configured ingest data root."
    reserved_metadata_key: str = (
        "Metadata key is reserved by the canonical metadata contract; choose another name."
    )
    vectordb_delete_error: str = "Error occurred while deleting embeddings from the vector DB."
    duplicate_upload: str = "A video with identical content already exists"
