# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import List, Optional, Any, Type, Literal
from enum import Enum

from pydantic import DirectoryPath, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from audio_analyzer.schemas.types import DeviceType, WhisperModel, StorageBackend

class Settings(BaseSettings):
    """
    Configuration settings used across whole application.
    
    These settings can be configured via environment variables on host or inside container.
    """

    # API configuration
    API_V1_PREFIX: str = "/api/v1"  # API version prefix to be used with each endpoint route
    APP_NAME: str = "Audio Analyzer Service"
    API_VER: str = "1.0.0"
    API_DESCRIPTION: str = "API for intelligent audio processing including speech transcription and audio event detection" 
    FASTAPI_ENV: str = "development"  # Environment for FastAPI (development or production)

    # API Health check configuration
    API_STATUS: str = "healthy"
    API_STATUS_MSG: str = "Service is running smoothly." 
    
    # CORS configuration
    BACKEND_CORS_ORIGINS: List[str] = ["*"]
    
    # File storage configuration
    OUTPUT_DIR: Path = "/tmp/audio_analyzer"  # Temporary root directory for saving transcription outputs
    UPLOAD_DIR: Path = "/tmp/audio_analyzer/uploads"  # Temporary directory for uploaded video files
    AUDIO_DIR: Path = "/tmp/audio_analyzer/audio"  # Temporary directory for saving audio stream extracted from video files
    
    # Storage backend configuration
    STORAGE_BACKEND: StorageBackend = StorageBackend.FILESYSTEM
    
    # MinIO configuration
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_SECURE: bool = False
    
    # Whisper model download configuration
    ENABLED_WHISPER_MODELS: Optional[List[WhisperModel]] = None # List of whisper model variants to be downloaded
    GGML_MODEL_DIR: Path = "/tmp/audio_analyzer_models/ggml" 
    OPENVINO_MODEL_DIR: Path = "/tmp/audio_analyzer_models/openvino"

    # Whisper configuration
    DEFAULT_WHISPER_MODEL: Optional[WhisperModel] = None
    TRANSCRIPT_LANGUAGE: Optional[str] = None  # If None, auto-detection based on model capabilities will be used
    
    # Device configuration
    DEFAULT_DEVICE: DeviceType = DeviceType.CPU  # Default compute device to use for transcription
    USE_FP16: bool = True  # Use 16-bit precision for GPU
    
    # Audio configuration
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_BIT_DEPTH: int = 16
    AUDIO_CHANNELS: int = 1
    
    # Uploaded video file size limits (in bytes)
    MAX_FILE_SIZE: int = 300 * 1024 * 1024  # 300MB by default
    
    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="ignore",
        validate_default=True,
    )
    
    @field_validator('MINIO_ACCESS_KEY', 'MINIO_SECRET_KEY')
    def validate_minio_credentials(cls, v: str, info) -> str:
        """
        Validate that MinIO credentials are not empty when using MinIO as storage backend.
        
        Args:
            v: The value to validate
            info: The validator context information
            
        Returns:
            The validated value
        """
        storage_backend = info.data.get('STORAGE_BACKEND')
        
        # Only validate if storage backend is MinIO
        if storage_backend == StorageBackend.MINIO:
            if not v or v.strip() == "":
                field_name = info.field_name
                raise ValueError(
                    f"{field_name} cannot be empty when using MinIO as storage backend"
                )
                
        return v
    
    @computed_field
    @property
    def DEBUG(self) -> bool:
        """Determine if the application is running in debug mode based on environment"""
        return self.FASTAPI_ENV.lower() == "development"
    
    @computed_field
    @property
    def AUDIO_FORMAT_PARAMS(self) -> dict:
        """Get audio format parameters based on configured settings"""
        return {
            "fps": self.AUDIO_SAMPLE_RATE,
            "nbytes": self.AUDIO_BIT_DEPTH // 8,
            "nchannels": self.AUDIO_CHANNELS,
        }
    
    # Convert the EnabledWhisperModels to Enum type for better validation
    @computed_field
    @property
    def EnabledWhisperModelsEnum(self) -> Type[Enum]:
        """
        Creates a dynamic Enum class with enabled whisper models.
        This allows for proper type validation in request schemas.
        """
        models = self.ENABLED_WHISPER_MODELS
        return Enum('EnabledWhisperModels', {model.name: model.value for model in models})
    

    @field_validator("ENABLED_WHISPER_MODELS", mode="before")
    @classmethod
    def create_enabled_model_list(cls, v: Any) -> List[WhisperModel]:
        """Convert comma-separated string value from env vars to a list of WhisperModel"""
        try:
            if isinstance(v, str) and (v := v.strip()):
                return [WhisperModel(item.strip().lower()) for item in v.split(",") if item.strip()]
            raise ValueError
        except ValueError:
            # Handle invalid model type
            valid_models = ", ".join([m.value for m in WhisperModel])
            raise ValueError(
                f"Invalid model type: '{v}'. "
                f"Valid options are: {valid_models}"
            )
    
    @field_validator("DEFAULT_WHISPER_MODEL", mode="before")
    @classmethod
    def validate_default_whisper_model(cls, v: Any, info) -> WhisperModel | None:
        """ Validate the default whisper model against the list of enabled models.
        If no default model is provided, return the Base model if available or first enabled model.
        """
        try:
            enabled_models = info.data.get('ENABLED_WHISPER_MODELS', [])
            
            if isinstance(v, str) and (v := v.strip()):
                enabled_model_list = [model.value for model in enabled_models]
                if v not in enabled_model_list:
                    raise ValueError(
                        f"Invalid default model: '{v}'. "
                        f"Valid options are one of these: {', '.join(enabled_model_list)}"
                    )
                return WhisperModel(v)
            
            fallback_model = enabled_models[0] if len(enabled_models) > 0 else None
            # If no default model is provided, return the small model if available or first enabled model
            return WhisperModel.SMALL_EN if (WhisperModel.SMALL_EN in enabled_models) else fallback_model

        except ValueError as e:
            raise e

settings = Settings()