# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pydantic_settings import BaseSettings
from pydantic import Field, computed_field
from os.path import dirname, abspath, join
from typing import List

class Settings(BaseSettings):

    APP_DISPLAY_NAME: str = "Document Ingestion Microservice"
    APP_DESC: str = "A microservice for document ingestion utilizing PGVector and MinIO.\
It generates embeddings for documents, stores them in PGVector, and saves the documents in MinIO."
    BASE_DIR: str = dirname(dirname(abspath(__file__)))

    ALLOW_ORIGINS: str = "*"  # Comma separated values for allowed origins
    ALLOW_METHODS: str = "*"  # Comma separated values for allowed HTTP Methods
    ALLOW_HEADERS: str = "*"  # Comma separated values for allowed HTTP Headers

    # Supported file formats
    SUPPORTED_FORMATS: set = {".pdf", ".txt", ".docx"}

    # Embedding endpoint
    TEI_ENDPOINT_URL: str = ...
    EMBEDDING_MODEL_NAME: str = ...

    # Postgres Configuration
    PG_CONNECTION_STRING: str = ...

    # Vector Index Configuration
    INDEX_NAME: str = ...

    # chunk parameters
    CHUNK_SIZE: int = ...
    CHUNK_OVERLAP: int = ...
    LOCAL_STORE_PREFIX: str = ...

    BATCH_SIZE: int = ...

    # MINIO Configuration
    DEFAULT_BUCKET: str = ...
    OBJECT_PREFIX: str = ...

    MINIO_HOST: str = ...
    MINIO_API_PORT: str = ...
    MINIO_ACCESS_KEY: str = ...
    MINIO_SECRET_KEY: str = ...

    #Allowed host domains for url ingestion
    DOMAINS: str = Field("", alias="ALLOWED_HOSTS", description="Comma separated list of allowed host domains for URL ingestion")


    @computed_field
    @property
    def ALLOWED_DOMAINS(self) -> List[str]:
        """
        Returns a list of allowed domains in canonical form (lowercase, stripped of trailing dots).
        """
        return [d.lower().rstrip('.') for d in self.DOMAINS.split(",") if d.strip()]


    class Config:
        env_file = join(dirname(abspath(__file__)), ".env")