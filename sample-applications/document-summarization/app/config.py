# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
 
from pydantic_settings import BaseSettings,SettingsConfigDict
from os.path import dirname, abspath, join

enviornment_file = join(dirname(abspath(__file__)), ".env")

class Settings(BaseSettings):
    
    SUPPORTED_FILE_EXTENSIONS: set = {".pdf", ".txt", ".docx"}
    SUPPORTED_FILE_TYPES: set = { file_type[1:] for file_type in SUPPORTED_FILE_EXTENSIONS }

    MIME_TYPES: dict[str, str] = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
        }
    
    LLM_ENDPOINT_URL: str
    LLM_MODEL: str
    CORS_ALLOW_ORIGINS: str
    CORS_ALLOW_METHODS: str
    CORS_ALLOW_HEADERS: str
    API_PORT: str
    GRADIO_PORT: str
    API_URL: str
    CHUNK_SIZE: int

    model_config = SettingsConfigDict(env_file=enviornment_file ,extra="ignore")
