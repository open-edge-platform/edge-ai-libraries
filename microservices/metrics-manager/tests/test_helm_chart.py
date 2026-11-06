# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Drift guard for the Helm chart at helm/metrics-manager/.

Ensures the independently versioned chart metadata stays consistent:
  * Chart.version == "<Chart.appVersion>-helm"
  * Chart.appVersion is a release no newer than VERSION
  * Chart.name == "metrics-manager"

If `helm` is on PATH the test additionally runs `helm lint` and
`helm template` to catch syntax / rendering regressions.
"""

from __future__ import annotations

import re
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


def test_chart_app_version_is_supported_release(chart: dict, project_version: str) -> None:
    app_version = str(chart["appVersion"])
    assert re.fullmatch(
        r"\d+\.\d+\.\d+", app_version
    ), f"Chart.yaml appVersion must identify a release, got {app_version!r}"
    assert tuple(map(int, app_version.split("."))) <= tuple(map(int, project_version.split("."))), (
        f"Chart.yaml appVersion ({app_version!r}) is newer than "
        f"the current application release ({project_version!r})"
    )


def test_chart_version_carries_helm_suffix(chart: dict) -> None:
    expected = f"{chart['appVersion']}-helm"
    assert chart["version"] == expected, (
        f"Chart.yaml version ({chart['version']!r}) must equal "
        f"'<appVersion>-helm' = {expected!r}. Update chart metadata together."
    )


@pytest.mark.skipif(shutil.which("make") is None, reason="make CLI not installed")
@pytest.mark.parametrize("app_version", ["2026.2.0", "2026.4.0"])
def test_make_preserves_independent_chart_version(
    tmp_path: Path, chart: dict, app_version: str
) -> None:
    for name in ("Makefile", "VERSION", "versions.env"):
        shutil.copyfile(REPO_ROOT / name, tmp_path / name)
    chart_dir = tmp_path / "helm" / "metrics-manager"
    chart_dir.mkdir(parents=True)
    metadata = dict(chart, appVersion=app_version, version=f"{app_version}-helm")
    (chart_dir / "Chart.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
    package = subprocess.run(
        ["make", "--dry-run", "helm-push"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert package.returncode == 0, package.stderr
    assert f"helm push dist/helm/metrics-manager-{app_version}-helm.tgz " in package.stdout
    bump = subprocess.run(
        ["make", "--dry-run", "bump", "NEW=2026.9.0"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bump.returncode == 0, bump.stderr
    assert "Chart.yaml" not in bump.stdout
    assert "docs/HELM.md" not in bump.stdout


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
    assert (
        result.returncode == 0
    ), f"helm lint failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not installed")
def test_helm_template_renders() -> None:
    result = subprocess.run(
        ["helm", "template", "test", str(CHART_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"helm template failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    rendered = result.stdout
    assert "kind: Deployment" in rendered
    assert "kind: Service" in rendered
    assert "hostPID: false" in rendered
    assert "privileged: false" in rendered
    assert "runAsNonRoot: true" in rendered
    assert "readOnlyRootFilesystem: true" in rendered
    assert "allowPrivilegeEscalation: false" in rendered
    assert "type: RuntimeDefault" in rendered
    assert "hostPath:" not in rendered


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not installed")
def test_helm_template_hardware_telemetry_profile() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(CHART_DIR),
            "--set",
            "hardware.telemetry.enabled=true",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rendered = result.stdout
    assert "hostPID: true" in rendered
    assert "privileged: true" in rendered
    assert "runAsNonRoot: false" in rendered
    assert "readOnlyRootFilesystem: false" in rendered
    assert "mountPath: /sys" in rendered
    assert "mountPath: /dev/dri" in rendered


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not installed")
def test_helm_template_daemonset_mode() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "test",
            str(CHART_DIR),
            "--set",
            "controller.kind=DaemonSet",
            "--set",
            "hardware.gpu.enabled=false",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "kind: DaemonSet" in result.stdout
    # GPU disabled => /dev/dri host path must not be mounted.
    assert "/dev/dri" not in result.stdout
