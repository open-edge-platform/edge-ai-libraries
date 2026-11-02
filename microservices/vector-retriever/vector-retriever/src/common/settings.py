# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings


env_path = os.path.join(os.path.dirname(__file__), "../../", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    APP_NAME: str = "vector-retriever"
    APP_DISPLAY_NAME: str = "Vector Retriever Microservice"
    APP_DESC: str = "Semantic retrieval service over pluggable vector backends with batch query support"

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    RETRIEVER_BACKEND: str = "vdms"

    VDMS_VDB_HOST: str = "vdms-vector-db"
    VDMS_VDB_PORT: int = 55555
    INDEX_NAME: str = "video_frame_embeddings"
    SEARCH_ENGINE: str = "FaissFlat"
    DISTANCE_STRATEGY: str = "IP"

    EMBEDDINGS_ENDPOINT: str = ""
    EMBEDDING_MODEL_NAME: str = ""
    DEFAULT_TOP_K: int = 20
    MAX_TOP_K: int = 1000

    # Milvus backend settings
    MILVUS_URI: str = "http://milvus-server:19530"
    MILVUS_TOKEN: str = ""
    MILVUS_DB_NAME: str = ""
    MILVUS_INDEX_TYPE: str = "FLAT"
    MILVUS_METRIC_TYPE: str = "L2"
    MILVUS_TEXT_FIELD: str = "text"
    MILVUS_METADATA_FIELD: str = ""

    # PGVector backend settings
    PGVECTOR_CONNECTION_STRING: str = ""

    # FAISS backend settings
    FAISS_INDEX_PATH: str = ""

    REQUEST_TIMEOUT_SECONDS: int = 30
    BATCH_MAX_CONCURRENCY: int = 10

    no_proxy: str = ""
    http_proxy: str = ""
    https_proxy: str = ""


settings = Settings()
