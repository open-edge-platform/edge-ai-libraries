# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
TIER 2 — Feature & Config Discovery Tests

These tests verify that the deployed VSS stack is running in the correct mode
and that all configuration endpoints are healthy before running any E2E tests.

Run with:
    cd test-functional/
    pytest test_features.py -v

Tests in this file:
    T2.1 - test_feature_flags_present
    T2.2 - test_resolved_config_non_empty
    T2.3 - test_whisper_models_loaded         (auto-skipped in search-only mode)
    T2.4 - test_evam_pipeline_status
    T2.5 - test_swagger_docs_accessible
"""

import pytest
import requests


class TestFeatures:
    """TIER 2: Feature flag and configuration discovery tests."""

    # ──────────────────────────────────────────────────────────────────────────
    # T2.1 — Feature flags match the deployed mode
    # ──────────────────────────────────────────────────────────────────────────

    def test_feature_flags_present(self, base_url, vss_health):
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        response = requests.get(f"{base_url}/manager/app/features", timeout=10)

        assert response.status_code == 200, (
            f"Expected 200 from /manager/app/features, got {response.status_code}. "
            f"Response: {response.text}"
        )

        body = response.json()

        # Both keys must be present in the response
        assert "summary" in body, f"'summary' key missing from features response: {body}"
        assert "search" in body,  f"'search' key missing from features response: {body}"

        # Each flag must be a recognized string value (not None, not boolean)
        valid_values = {"FEATURE_ON", "FEATURE_OFF"}
        assert body["summary"] in valid_values, (
            f"Unexpected value for 'summary' flag: {body['summary']!r}. "
            f"Expected one of: {valid_values}"
        )
        assert body["search"] in valid_values, (
            f"Unexpected value for 'search' flag: {body['search']!r}. "
            f"Expected one of: {valid_values}"
        )

        # At least one feature must be ON — otherwise nothing is deployed
        # We use 'or' here because a valid deployment can be summary-only OR search-only
        summary_on = body["summary"] == "FEATURE_ON"
        search_on  = body["search"]  == "FEATURE_ON"
        assert summary_on or search_on, (
            f"Both features are OFF — is the stack fully deployed? Features: {body}\n"
            "Fix: source setup.sh --summary  OR  source setup.sh --search"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # T2.2 — Resolved configuration object is non-empty
    # ──────────────────────────────────────────────────────────────────────────

    def test_resolved_config_non_empty(self, base_url, vss_health):
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        response = requests.get(f"{base_url}/manager/app/config", timeout=10)

        assert response.status_code == 200, (
            f"Expected 200 from /manager/app/config, got {response.status_code}. "
            f"Response: {response.text}"
        )

        body = response.json()

        # Shape check: config must be an object (dict), not a list or primitive
        assert isinstance(body, dict), (
            f"Expected a JSON object from /manager/app/config, "
            f"got {type(body).__name__}: {body}"
        )

        # Content check: object must not be empty
        assert body, (
            "Config response is an empty object {}. "
            "Pipeline Manager may have failed to load its runtime configuration."
        )

    # ──────────────────────────────────────────────────────────────────────────
    # T2.3 — Whisper audio models loaded (summary/dual/unified modes only)
    # ──────────────────────────────────────────────────────────────────────────

    def test_whisper_models_loaded(self, base_url, vss_health):
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        # Step 1: Check if summary is even deployed before testing Whisper
        # We call /features here to get the current mode
        features_response = requests.get(
            f"{base_url}/manager/app/features", timeout=10
        )
        assert features_response.status_code == 200
        features = features_response.json()

        # Auto-skip: Whisper is only deployed in summary mode
        if features.get("summary") != "FEATURE_ON":
            pytest.skip(
                "Skipping Whisper model check — summary feature is OFF in this deployment. "
                "Deploy with --summary or --summary --search to test audio models."
            )

        # Step 2: Now check that Whisper models are actually loaded
        response = requests.get(f"{base_url}/manager/audio/models", timeout=10)

        assert response.status_code == 200, (
            f"Expected 200 from /manager/audio/models, got {response.status_code}. "
            f"Response: {response.text}"
        )

        body = response.json()

        # The response can be either a bare array  →  ["tiny.en", "small.en", ...]
        # or a wrapped object                      →  {"models": [...], "default_model": "..."}
        # Handle both shapes so this test doesn't break on an API schema change.
        if isinstance(body, list):
            models = body
        elif isinstance(body, dict):
            models = body.get("models", [])
        else:
            models = []

        assert isinstance(models, list), (
            f"Expected a list of models from /manager/audio/models, "
            f"got {type(body).__name__}: {body}"
        )

        # len() counts items in a list — must have at least one model loaded
        assert len(models) > 0, (
            "No Whisper models returned by /manager/audio/models. "
            "audio-analyzer container may not have finished loading models."
        )

    # ──────────────────────────────────────────────────────────────────────────
    # T2.4 — EVAM pipeline status is reachable and returns valid JSON
    # ──────────────────────────────────────────────────────────────────────────

    def test_evam_pipeline_status(self, base_url, vss_health):
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        response = requests.get(f"{base_url}/manager/pipeline/evam", timeout=10)

        assert response.status_code == 200, (
            f"Expected 200 from /manager/pipeline/evam, got {response.status_code}. "
            f"Response: {response.text}"
        )

        # Just verify the response is parseable JSON (not None, not an error string)
        body = response.json()
        assert body is not None, "Expected JSON response from /manager/pipeline/evam, got None"

    # ──────────────────────────────────────────────────────────────────────────
    # T2.5 — Swagger UI and raw OpenAPI JSON are accessible
    # ──────────────────────────────────────────────────────────────────────────

    def test_swagger_docs_accessible(self, base_url, vss_health):
        if not vss_health:
            pytest.fail("VSS stack did not become healthy within the timeout period.")

        # Test both Swagger endpoints in one loop
        swagger_paths = ["/manager/docs", "/manager/swagger/json"]

        for url_path in swagger_paths:
            response = requests.get(f"{base_url}{url_path}", timeout=10)
            assert response.status_code == 200, (
                f"Expected 200 from {url_path}, got {response.status_code}. "
                f"Response: {response.text[:200]}"  # only first 200 chars to keep output clean
            )
