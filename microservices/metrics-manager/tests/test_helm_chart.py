# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Drift guard for the Helm chart at helm/metrics-manager/.

Ensures the chart metadata stays in lock-step with VERSION:
  * Chart.version == "<VERSION>-helm"
  * Chart.appVersion == VERSION
  * Chart.name == "metrics-manager"

If `helm` is on PATH the test additionally runs `helm lint` and
`helm template` to catch syntax / rendering regressions.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"
CHART_DIR = REPO_ROOT / "helm" / "metrics-manager"
CHART_FILE = CHART_DIR / "Chart.yaml"


@pytest.fixture(scope="module")
def chart() -> dict:
    assert CHART_FILE.is_file(), f"Missing {CHART_FILE}"
    with CHART_FILE.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def project_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def test_chart_name(chart: dict) -> None:
    assert chart["name"] == "metrics-manager"


def test_chart_app_version_matches_version_file(chart: dict, project_version: str) -> None:
    assert str(chart["appVersion"]) == project_version, (
        f"Chart.yaml appVersion ({chart['appVersion']!r}) drifted from "
        f"VERSION ({project_version!r}). Run: make bump NEW={project_version}"
    )


def test_chart_version_carries_helm_suffix(chart: dict, project_version: str) -> None:
    expected = f"{project_version}-helm"
    assert chart["version"] == expected, (
        f"Chart.yaml version ({chart['version']!r}) must equal "
        f"'<VERSION>-helm' = {expected!r}. Run: make bump NEW={project_version}"
    )


def test_chart_api_version_v2(chart: dict) -> None:
    assert chart.get("apiVersion") == "v2"


def test_helmignore_present() -> None:
    assert (CHART_DIR / ".helmignore").is_file()


def test_values_file_present() -> None:
    assert (CHART_DIR / "values.yaml").is_file()


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not installed")
def test_helm_lint_passes() -> None:
    result = subprocess.run(
        ["helm", "lint", str(CHART_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"helm lint failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not installed")
def test_helm_template_renders() -> None:
    result = subprocess.run(
        ["helm", "template", "test", str(CHART_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"helm template failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    rendered = result.stdout
    assert "kind: Deployment" in rendered
    assert "kind: Service" in rendered
    # Privileged hostPID profile must always be rendered.
    assert "hostPID: true" in rendered
    assert "privileged: true" in rendered


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not installed")
def test_helm_template_daemonset_mode() -> None:
    result = subprocess.run(
        [
            "helm", "template", "test", str(CHART_DIR),
            "--set", "controller.kind=DaemonSet",
            "--set", "hardware.gpu.enabled=false",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "kind: DaemonSet" in result.stdout
    # GPU disabled => /dev/dri host path must not be mounted.
    assert "/dev/dri" not in result.stdout
