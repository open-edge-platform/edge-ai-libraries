"""Integration test ensuring the models endpoint responds with data.

Run with Python 3.12+ and pytest while the VIPPET API is available locally:

    python3.12 -m pytest integration/test_models_list.py
"""

import logging

import pytest
import requests

from api_helpers import fetch_models
from vippet.api.api_schemas import Model

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


def test_models_endpoint_returns_models(http_client: requests.Session) -> None:
    models = fetch_models(http_client)

    assert models, "Models endpoint returned an empty list"
    for raw in models:
        Model.model_validate(raw)
