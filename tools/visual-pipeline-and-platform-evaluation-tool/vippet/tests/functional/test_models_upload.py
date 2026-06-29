# SPDX-License-Identifier: Apache-2.0
"""Functional tests for ``POST /models/upload``.

These tests upload the two reference OMZ models
(``face-detection-retail-0004`` and
``age-gender-recognition-retail-0013``) under per-session unique
names so they show up as custom (uploaded) models in
``GET /models``. The pipeline test in
``test_models_uploaded_pipeline.py`` then exercises the very same
uploaded models end-to-end through ``/tests/performance`` to lock in
the ``ModelManager`` fallback added in ``graph.py``.
"""

from __future__ import annotations

import logging

import pytest
import requests

from helpers.api_helpers import (
    fetch_models,
    find_model_in_list,
    upload_model_file,
)

logger = logging.getLogger(__name__)


@pytest.mark.full
def test_uploaded_models_appear_in_models_list(
    http_client: requests.Session,
    uploaded_model_names: dict[str, str],
) -> None:
    """Both uploaded copies must appear in ``GET /models`` as INSTALLED
    custom models with the right category.
    """
    expected_categories = {
        "face-detection-retail-0004": "detection",
        "age-gender-recognition-retail-0013": "classification",
    }

    models = fetch_models(http_client)
    for source_name, uploaded_name in uploaded_model_names.items():
        entry = find_model_in_list(models, uploaded_name)
        assert entry is not None, (
            f"Uploaded model {uploaded_name!r} missing from GET /models"
        )
        install_status = str(entry.get("install_status") or "").upper()
        assert install_status == "INSTALLED", (
            f"Uploaded model {uploaded_name!r} not INSTALLED: "
            f"install_status={entry.get('install_status')!r}"
        )
        # Custom uploads use ``source=custom`` in the registry; the
        # exact label may vary across API versions, so we only assert
        # the model is NOT marked as one of the catalogue sources.
        assert entry.get("source") not in {"omz", "public"}, (
            f"Uploaded model {uploaded_name!r} mis-tagged with "
            f"source={entry.get('source')!r}"
        )
        assert entry.get("category") == expected_categories[source_name], (
            f"Uploaded model {uploaded_name!r} got category "
            f"{entry.get('category')!r}, expected "
            f"{expected_categories[source_name]!r}"
        )


@pytest.mark.full
def test_uploading_same_model_name_twice_is_rejected(
    http_client: requests.Session,
    uploaded_model_names: dict[str, str],
) -> None:
    """A second upload using a model_name that already exists must be
    rejected (409 from the model-download microservice, surfaced as-is
    by the vippet upload route).
    """
    # We only need a tiny placeholder payload here; the server checks
    # the name before unpacking the archive.
    existing_name = next(iter(uploaded_model_names.values()))
    response = upload_model_file(
        http_client,
        model_name=existing_name,
        category="detection",
        payload=b"PK\x05\x06" + b"\x00" * 18,  # empty zip
    )
    assert response.status_code in {400, 409, 422}, (
        f"Re-uploading {existing_name!r} should be rejected, got "
        f"{response.status_code}: {response.text}"
    )


@pytest.mark.full
def test_uploading_with_invalid_category_rejected(
    http_client: requests.Session,
    upload_run_id: str,
) -> None:
    """The ``category`` form field is validated against the
    ``ModelCategory`` enum; an unknown value must be rejected with 422.
    """
    response = upload_model_file(
        http_client,
        model_name=f"invalid-category-{upload_run_id}",
        category="not-a-valid-category",
        payload=b"PK\x05\x06" + b"\x00" * 18,
    )
    assert response.status_code == 422, response.text
