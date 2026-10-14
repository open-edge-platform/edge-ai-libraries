# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from os.path import dirname, abspath
from pydantic import PrivateAttr
from pydantic_settings import BaseSettings
import tempfile
import os

class Settings(BaseSettings):
    """
    Settings class for configuring the Chatqna-Core application.
    This class manages application settings, including model backend runtime selection,
    model IDs, device configurations, prompt templates, and various internal paths.
    It loads configuration from a YAML file, validates backend-specific requirements,
    and ensures prompt templates contain required placeholders.
    """

    APP_DISPLAY_NAME: str = "Video-Accuracy Evaluation"
    BASE_DIR: str = dirname(dirname(abspath(__file__)))
    DEBUG: bool = False

    BERT_SCORER_MODEL_ID: str = "bert-base-uncased"
    SBERT_MODEL_ID: str = ""
    NLI_MODEL_ID:  str = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
    # Pinned to a specific commit so a republished tag upstream cannot silently change the model weights.
    NLI_MODEL_REVISION: str = "b3546ea6b0346eb6f8d5d68b13c7dc6d0376b3d7"


    # These fields are private within class and will not be affected by environment variables
    _SUPPORTED_FORMATS: set[str] = PrivateAttr(default={".tsv", ".md"})
    _CACHE_DIR: str = PrivateAttr(os.path.join(tempfile.gettempdir(), "model_cache"))
    _DATASETS_CACHE: str = PrivateAttr(os.path.join(tempfile.gettempdir(), "datasets"))
    _TMP_FILE_PATH: str = PrivateAttr(os.path.join(tempfile.gettempdir(), "documents"))

config = Settings()
