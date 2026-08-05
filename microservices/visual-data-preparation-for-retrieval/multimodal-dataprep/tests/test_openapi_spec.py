# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Guard rails for the committed OpenAPI specification.

These tests fail when the spec drifts from the application, and when documented
metadata regresses to storage- or vector-backend-specific wording.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "docs" / "user-guide" / "api-docs" / "openapi.yaml"
GENERATOR = REPO_ROOT / "scripts" / "generate_openapi.py"

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def _operations(spec):
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


def test_committed_spec_is_not_stale():
    """The committed spec must match what the application generates."""
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "docs/user-guide/api-docs/openapi.yaml is out of date. "
        "Run: python scripts/generate_openapi.py\n" + result.stderr
    )


def test_version_matches_pyproject(spec):
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE).group(1)
    assert spec["info"]["version"] == declared


def test_servers_reflect_root_path(spec):
    assert [server["url"] for server in spec.get("servers", [])] == ["/v1/dataprep"]


def test_every_operation_tag_is_documented(spec):
    documented = {tag["name"] for tag in spec.get("tags", [])}
    assert documented, "Top-level tag metadata is missing."
    for tag in documented:
        assert spec_tag_description(spec, tag), f"Tag {tag!r} has no description."

    used = {tag for _, _, op in _operations(spec) for tag in op.get("tags", [])}
    assert used <= documented, f"Undocumented tags: {sorted(used - documented)}"


def spec_tag_description(spec, name):
    for tag in spec.get("tags", []):
        if tag["name"] == name:
            return tag.get("description")
    return None


def test_every_operation_declares_error_responses(spec):
    """Every operation must document at least one 4xx and the 500 response.

    ``/health`` is exempt: it swallows all backend errors by design and always
    returns 200, reporting degradation inside the response body instead.
    """
    exempt = {"/health"}
    for path, method, operation in _operations(spec):
        if path in exempt:
            continue
        codes = set(operation["responses"])
        assert "500" in codes, f"{method.upper()} {path} does not document 500."
        assert any(
            code.startswith("4") for code in codes
        ), f"{method.upper()} {path} documents no 4xx response."


def test_dedup_endpoints_document_conflict(spec):
    """Endpoints gated by the duplicate-upload check must document 409."""
    dedup_paths = {
        "/media/upload",
        "/media/process",
        "/media/ingest",
        "/media/upload/batch",
        "/media/ingest/batch",
    }
    for path in dedup_paths:
        item = spec["paths"][path]
        for method, operation in item.items():
            if method in HTTP_METHODS:
                assert "409" in operation["responses"], f"{method.upper()} {path} is missing 409."

    for path, method, operation in _operations(spec):
        if path not in dedup_paths:
            assert (
                "409" not in operation["responses"]
            ), f"{method.upper()} {path} documents 409 but is not a dedup endpoint."


def test_documentation_is_storage_and_backend_agnostic(spec):
    """Parameter and operation docs must not name a specific storage or vector backend."""
    banned = re.compile(r"\b(minio|vdms|milvus)\b", re.IGNORECASE)
    offenders = []

    for path, method, operation in _operations(spec):
        for field in ("summary", "description"):
            text = operation.get(field) or ""
            if banned.search(text):
                offenders.append(f"{method.upper()} {path} [{field}]")
        for parameter in operation.get("parameters", []):
            if banned.search(parameter.get("description") or ""):
                offenders.append(f"{method.upper()} {path} param {parameter['name']}")

    for name, schema in spec.get("components", {}).get("schemas", {}).items():
        if banned.search(schema.get("description") or ""):
            offenders.append(f"schema {name}")
        for prop, prop_schema in (schema.get("properties") or {}).items():
            if isinstance(prop_schema, dict) and banned.search(
                prop_schema.get("description") or ""
            ):
                offenders.append(f"schema {name}.{prop}")

    assert not offenders, "Backend-specific wording found in: " + ", ".join(sorted(offenders))


def test_optional_processing_params_have_no_misleading_defaults(spec):
    """These params resolve from service config, so the spec must not assert a default."""
    config_driven = {"frame_interval", "enable_object_detection", "detection_confidence"}
    for path, method, operation in _operations(spec):
        for parameter in operation.get("parameters", []):
            if parameter["name"] in config_driven:
                assert (
                    parameter["schema"].get("default") is None
                ), f"{method.upper()} {path} param {parameter['name']} asserts a schema default."
