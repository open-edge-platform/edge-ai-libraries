# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Guard tests for the third-party version pins.

``versions.env`` is the single source of truth for every artefact the Metrics
Manager pulls from a third party (Telegraf, qmassa/qmmd, toolchain images).
The Dockerfile carries mirrored ``ARG`` defaults so that a plain
``docker build .`` works without the Makefile.

Two copies of a version number will eventually drift, and the failure mode is
nasty: the container and the bare-metal .deb would ship *different* Telegraf
builds while claiming the same version. These tests turn that drift into a CI
failure. Run ``make sync-versions`` to fix a reported mismatch.
"""

import json
import logging
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

from app.logging_config import JSONFormatter
from app.settings import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSIONS_ENV = REPO_ROOT / "versions.env"
DOCKERFILE = REPO_ROOT / "Dockerfile"


@pytest.fixture(scope="module")
def release_version():
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


class TestReleaseVersion:
    def test_python_metadata(self, release_version):
        project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert project["project"]["version"] == release_version

    def test_settings_and_log_defaults(self, release_version):
        assert Settings.model_fields["service_version"].default == release_version
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "version check", (), None)
        assert json.loads(JSONFormatter().format(record))["version"] == release_version

    def test_runtime_version_override(self, monkeypatch):
        monkeypatch.setenv("SERVICE_VERSION", "custom-build")
        settings = Settings()
        assert settings.service_version == "custom-build"
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "version check", (), None)
        formatter = JSONFormatter(service_version=settings.service_version)
        assert json.loads(formatter.format(record))["version"] == "custom-build"

    def test_environment_example(self, release_version):
        example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        assert re.findall(r"^TAG=(.+)$", example, re.MULTILINE) == [release_version]
        assert re.findall(r"^#SERVICE_VERSION=(.+)$", example, re.MULTILINE) == [release_version]

    def test_compose_defaults_preserve_tag_override(self, release_version):
        compose = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
        for name in ("metrics-manager", "metrics-manager-host-nic", "metrics-manager-test"):
            service = compose["services"][name]
            image = "metrics-manager" if name == "metrics-manager-host-nic" else name
            assert service["image"] == "${REGISTRY:-}" + image + ":${TAG:-" + release_version + "}"
            assert service["build"]["args"]["VERSION"] == "${TAG:-" + release_version + "}"

    def test_docker_build_defaults(self, release_version, dockerfile_text):
        defaults = re.findall(r"^ARG VERSION=(\S+)$", dockerfile_text, re.MULTILINE)
        assert defaults == [release_version, release_version]

    def test_docker_runtime_uses_build_version(self, dockerfile_text):
        production = dockerfile_text.split(" AS production\n", 1)[1]
        assert production.index("ARG VERSION=") < production.index("ENV SERVICE_VERSION=${VERSION}")
        assert 'org.opencontainers.image.version="${VERSION}"' in production
        assert "-X main.version=${VERSION}" in dockerfile_text

    def test_native_package_runtime_dependencies(self):
        package = yaml.safe_load(
            (REPO_ROOT / "native/packaging/nfpm.yaml").read_text(encoding="utf-8")
        )
        assert {
            "adduser",
            "systemd",
            "kmod",
            "libudev1",
            "libcap2",
            "libgcc-s1",
            "libc6 (>= 2.34)",
        } <= set(package["depends"])

    @pytest.mark.parametrize("suffix", [None, "-rc1"])
    def test_package_rejects_mismatched_image_before_staging(
        self, tmp_path, release_version, suffix
    ):
        native = tmp_path / "native"
        stage = native / "packaging/dist"
        stage.mkdir(parents=True)
        marker = stage / "existing-output"
        marker.write_text("keep")
        shutil.copy2(REPO_ROOT / "native/build.sh", native / "build.sh")
        for name in ("VERSION", "versions.env"):
            shutil.copyfile(REPO_ROOT / name, tmp_path / name)
        tools = tmp_path / "tools"
        tools.mkdir()
        docker = tools / "docker"
        version = "" if suffix is None else release_version + suffix
        docker.write_text("#!/bin/sh\nprintf '%s\\n' \"$TEST_IMAGE_VERSION\"\n")
        docker.chmod(0o755)
        result = subprocess.run(
            ["sh", str(native / "build.sh")],
            env={
                "PATH": f"{tools}:/usr/bin:/bin",
                "SKIP_IMAGE_BUILD": "1",
                "IMAGE": "version-test",
                "TEST_IMAGE_VERSION": version,
            },
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode != 0
        assert f"rebuild with TAG={release_version} before packaging" in result.stderr
        assert marker.read_text() == "keep"

    def test_package_staging_is_excluded_from_docker_context(self):
        assert "native/packaging/dist/" in (REPO_ROOT / ".dockerignore").read_text().splitlines()

    @pytest.mark.parametrize("endpoint", ["/", "/health", "/api/health"])
    @pytest.mark.parametrize("override", [None, "custom-build"])
    def test_api_reports_release(self, endpoint, override, client, release_version, monkeypatch):
        from app.settings import get_settings

        expected = override or release_version
        monkeypatch.setattr(get_settings(), "service_version", expected)
        response = client.get(endpoint)
        assert response.status_code == 200
        assert response.json()["version"] == expected

    @pytest.mark.parametrize(
        "path",
        [
            "docs/user-guide/api-reference.md",
            "docs/user-guide/get-started.md",
            "docs/user-guide/get-started/environment-variables.md",
            "docs/user-guide/get-started/native-docker-collectors.md",
            "README.md",
        ],
    )
    def test_current_documentation_versions(self, path, release_version):
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        references = re.findall(r"(?<![\d.])2026\.\d+\.\d+(?![\d.]|-helm)", text)
        assert references, f"No current version references found in {path}"
        assert set(references) == {release_version}


# Keys in versions.env that must be mirrored by an `ARG <KEY>=<value>` default.
MIRRORED_KEYS = (
    "TELEGRAF_VERSION",
    "TELEGRAF_SHA256",
    "QMASSA_VERSION",
    "QMMD_VERSION",
    "RUST_IMAGE",
    "GO_IMAGE",
    "PYTHON_IMAGE",
)

# versions.env is deliberately restricted to bare `KEY=value` lines so that
# make, sh and Python can all parse it with the same trivial rules.
_ASSIGNMENT = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>\S*)$")


def _parse_versions_env(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ASSIGNMENT.match(line)
        assert match is not None, (
            f"versions.env:{lineno}: expected a bare `KEY=value` line "
            f"(no spaces, no quotes, no shell expansion), got: {raw!r}"
        )
        parsed[match.group("key")] = match.group("value")
    return parsed


@pytest.fixture(scope="module")
def versions() -> dict[str, str]:
    assert VERSIONS_ENV.is_file(), "versions.env is missing"
    return _parse_versions_env(VERSIONS_ENV.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dockerfile_args(dockerfile_text) -> dict[str, str]:
    """Every `ARG KEY=value` default declared in the Dockerfile."""
    pattern = re.compile(r"^ARG\s+([A-Z][A-Z0-9_]*)=(\S+)\s*$", re.MULTILINE)
    return dict(pattern.findall(dockerfile_text))


class TestVersionsEnv:
    """versions.env must be complete and well-formed."""

    def test_declares_every_mirrored_key(self, versions):
        missing = [key for key in MIRRORED_KEYS if key not in versions]
        assert not missing, f"versions.env is missing: {missing}"

    def test_no_value_is_empty(self, versions):
        empty = [key for key, value in versions.items() if not value]
        assert not empty, f"versions.env has empty values for: {empty}"

    def test_telegraf_version_is_a_release_number(self, versions):
        assert re.fullmatch(r"\d+\.\d+\.\d+", versions["TELEGRAF_VERSION"]), (
            "TELEGRAF_VERSION must be a bare release number such as 1.39.3 "
            "(no leading 'v'), because it is interpolated into both the "
            "download URL and the archive's top-level directory name"
        )

    def test_telegraf_digest_is_a_sha256(self, versions):
        assert re.fullmatch(r"[0-9a-f]{64}", versions["TELEGRAF_SHA256"]), (
            "TELEGRAF_SHA256 must be 64 lowercase hex characters. The build "
            "verifies the downloaded archive against it, so a malformed digest "
            "silently weakens supply-chain integrity"
        )


class TestDockerfileMirrorsVersionsEnv:
    """A forgotten `make sync-versions` must fail here, not in production."""

    @pytest.mark.parametrize("key", MIRRORED_KEYS)
    def test_arg_default_matches(self, key, versions, dockerfile_args):
        assert key in dockerfile_args, f"Dockerfile declares no `ARG {key}=<default>`"
        assert dockerfile_args[key] == versions[key], (
            f"{key} drifted: versions.env={versions[key]!r} but "
            f"Dockerfile ARG default={dockerfile_args[key]!r}. "
            f"Run `make sync-versions`."
        )

    def test_python_stages_share_pinned_debian_base(self, versions, dockerfile_text):
        assert re.fullmatch(
            r"docker\.io/library/python:3\.12-slim-trixie@sha256:[0-9a-f]{64}",
            versions["PYTHON_IMAGE"],
        )
        assert "FROM ${PYTHON_IMAGE} AS python-builder" in dockerfile_text
        assert "FROM ${PYTHON_IMAGE} AS production" in dockerfile_text

    def test_build_proxies_are_not_persisted(self, dockerfile_text):
        assert not re.search(
            r"^ARG\s+(?:https?|no)_proxy\b",
            dockerfile_text,
            re.MULTILINE | re.IGNORECASE,
        )
        proxy_values = re.findall(r"\b(?:https?|no)_proxy=([^\s]*)", dockerfile_text, re.IGNORECASE)
        assert proxy_values == [""] * 6

    def test_runtime_refreshes_distribution_packages(self, dockerfile_text):
        production = dockerfile_text.split(" AS production\n", 1)[1]
        assert re.search(r"RUN(?: --mount=\S+)*\s+\\\n\s+set -eu;", production)
        assert "apt-get upgrade --yes --no-install-recommends;" in production


class TestTelegrafFetchIsVerified:
    """The Telegraf download must never be trusted without a digest check."""

    def test_download_uses_https_only(self, dockerfile_text):
        assert "https://dl.influxdata.com/telegraf/releases" in dockerfile_text
        assert "--proto '=https'" in dockerfile_text, (
            "curl must be restricted to https so a redirect cannot downgrade "
            "the transport to plain http"
        )

    def test_archive_digest_is_checked_before_extraction(self, dockerfile_text):
        assert "sha256sum --check --strict" in dockerfile_text, (
            "the downloaded Telegraf archive must be verified against "
            "TELEGRAF_SHA256 before it is extracted"
        )

    def test_curl_fails_on_http_errors(self, dockerfile_text):
        assert "--fail" in dockerfile_text, (
            "without curl --fail an HTTP error page is written to disk and the "
            "digest check becomes the only thing standing between an outage "
            "and a corrupt build"
        )
