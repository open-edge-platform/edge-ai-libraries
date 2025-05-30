# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

APP_TITLE: str = "Intel GenAI DataPrep Microservice"
APP_DESC: str = "A Data preparation microservice based on \
Intel GenAI DataStore service. Helps create embeddings for a given document \
and store it in an Object storage service."

# Embedding endpoint
TEI_ENDPOINT: str = os.getenv("TEI_ENDPOINT_URL")
EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME")

# Postgres Configuration
PG_CONNECTION_STRING: str = os.getenv("PG_CONNECTION_STRING")
# Data Store Endpoint
DATASTORE_BASE_URL: str = os.getenv("DATASTORE_ENDPOINT_URL")
DATASTORE_DATA_ENDPOINT: str = f"{DATASTORE_BASE_URL}/data"

# Vector Index Configuration
INDEX_NAME: str = os.getenv("INDEX_NAME", "intel-rag-xeon")
#supported file formats
SUPPORTED_FORMATS: set = {".pdf", ".txt", ".docx"}
#allowed hosts for url ingestion
ALLOWED_HOSTS = set(host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip())


# chunk parameters
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE")) if os.getenv("CHUNK_SIZE") and os.getenv("CHUNK_SIZE").isdigit() else 1500
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP")) if os.getenv("CHUNK_OVERLAP") and os.getenv("CHUNK_OVERLAP").isdigit() else 50

LOCAL_STORE_PREFIX: str = "/tmp/intelgai"

BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", 16))

current_file_path: str = os.path.abspath(__file__)
parent_dir: str = os.path.dirname(current_file_path)
