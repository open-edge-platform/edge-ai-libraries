# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


class Strings:
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
    vdms_client_error: str = "Error occurred while initializing VDMS client."
