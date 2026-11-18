# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Python service builds reuse installed dependencies and cached downloads."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
PYTHON_SERVICES = [
    pytest.param(
        "Dockerfile", "deployment/docker/docker-compose.yml", "engine",
        "COPY pyproject.toml /app/engine/pyproject.toml", "COPY . /app/engine/",
        id="engine",
    ),
    pytest.param(
        "tools/okf_extractor/Dockerfile",
        "deployment/docker/docker-compose-okf-extractor.yml", "okf-extractor",
        "COPY requirements.txt /app/requirements.txt", "COPY . /app/okf_extractor/",
        id="okf-extractor",
    ),
]


@pytest.mark.parametrize(
    "dockerfile,compose,service,manifest_copy,source_copy", PYTHON_SERVICES
)
def test_dependency_install_is_cached_independently_of_source(
    dockerfile, compose, service, manifest_copy, source_copy
):
    text = (ROOT / dockerfile).read_text(encoding="utf-8")

    assert text.startswith("# syntax=docker/dockerfile:1\n")
    assert text.index(manifest_copy) < text.index(source_copy)
    dependencies = text[text.index(manifest_copy):text.index(source_copy)]
    assert "RUN --mount=type=cache" in dependencies
    assert "target=/root/.cache/pip" in dependencies
    assert "sharing=locked" in dependencies
    assert "pip3 install" in dependencies or "pip install" in dependencies
    assert "--no-cache-dir" not in text


@pytest.mark.parametrize(
    "dockerfile,compose,service,manifest_copy,source_copy", PYTHON_SERVICES
)
def test_compose_keeps_inline_cache_in_the_service_image(
    dockerfile, compose, service, manifest_copy, source_copy
):
    definition = yaml.safe_load((ROOT / compose).read_text(encoding="utf-8"))
    definition = definition["services"][service]
    build = definition["build"]

    assert build["args"]["BUILDKIT_INLINE_CACHE"] == "1"
    assert build["cache_from"] == [definition["image"]]
    assert not build.get("no_cache", False)


def test_engine_dependency_requirements_are_derived_from_the_manifest(tmp_path):
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    script = text.split("python3 - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    manifest = ROOT / "pyproject.toml"
    requirements = tmp_path / "engine-requirements.txt"
    script = script.replace("/app/engine/pyproject.toml", str(manifest))
    script = script.replace("/tmp/engine-requirements.txt", str(requirements))

    # Execute only the metadata extraction, never the Dockerfile's pip install.
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)

    project = tomllib.loads(manifest.read_text(encoding="utf-8"))
    assert requirements.read_text(encoding="utf-8").splitlines() == (
        project["build-system"]["requires"] + project["project"]["dependencies"]
    )


def test_engine_source_install_does_not_resolve_or_download_dependencies():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    source_install = text.split("COPY . /app/engine/", 1)[1]

    assert 'project["build-system"]["requires"]' in text
    assert 'project["project"]["dependencies"]' in text
    assert "pip3 install --no-deps --no-build-isolation --no-index /app/engine" in source_install