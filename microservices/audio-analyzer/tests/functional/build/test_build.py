"""
Tier 3 — Real Docker Compose Build Tests
==========================================
These tests run actual Docker commands against a live Docker daemon.
No mocking.  No text parsing.  No shortcuts.

Prerequisites:
  - Docker installed and daemon running
  - Run from the audio-analyzer repo root

Run:
    pytest tests/functional/build/test_build.py -m tier3 -v -s
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_TIMEOUT_SEC = 900   # 15 min — covers base image pull + pip install


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _docker_available() -> tuple[bool, str]:
    """Return (available, reason).  Checks Docker binary and daemon."""
    if shutil.which("docker") is None:
        return False, "docker binary not found on PATH"
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        return False, "Docker daemon timed out — daemon may not be running"
    except FileNotFoundError:
        return False, "docker binary not found"
    if result.returncode != 0:
        return False, f"Docker daemon not reachable: {result.stderr.strip()[:200]}"
    return True, ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestDockerComposeBuild:

    @pytest.mark.tier3
    def test_docker_daemon_is_running(self):
        """Prerequisite: Docker daemon must be reachable before any build test."""
        ok, reason = _docker_available()
        if not ok:
            pytest.skip(f"Docker not available — {reason}")

    @pytest.mark.tier3
    def test_docker_compose_build_completes(self):
        """
        Run `docker compose build --no-cache` and assert exit code 0.

        Validates:
          - Dockerfile syntax is valid (not just text-checked)
          - All COPY / ADD sources exist on disk
          - pip install -r requirements.txt succeeds inside the image
          - Final image is produced without error
        """
        ok, reason = _docker_available()
        if not ok:
            pytest.skip(f"Docker not available — {reason}")

        result = subprocess.run(
            ["docker", "compose", "build", "--no-cache"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT_SEC,
        )

        if result.returncode != 0:
            print("\n── docker compose build STDOUT ──")
            print(result.stdout[-4000:] if result.stdout else "(empty)")
            print("── docker compose build STDERR ──")
            print(result.stderr[-4000:] if result.stderr else "(empty)")

        assert result.returncode == 0, (
            f"`docker compose build` failed (exit {result.returncode}).\n"
            f"Last stderr:\n{result.stderr.strip()[-1000:]}"
        )

    @pytest.mark.tier3
    def test_docker_image_exists_after_build(self):
        """
        After build, verify the image is present in the local Docker image store.
        Image name is read from docker-compose.yml — stays in sync with config.
        """
        ok, reason = _docker_available()
        if not ok:
            pytest.skip(f"Docker not available — {reason}")

        with open(REPO_ROOT / "docker-compose.yml") as fh:
            dc = yaml.safe_load(fh)

        service = dc.get("services", {}).get("audio-analyzer", {})
        image_name = service.get("image", "")

        if not image_name:
            pytest.skip("Could not determine image name from docker-compose.yml")

        # Resolve ${VAR:-fallback} → fallback for local inspection
        image_name = re.sub(r"\$\{[^}]+:-([^}]*)\}", r"\1", image_name)
        image_name = re.sub(r"\$\{[^}]+\}", "", image_name).strip("/: ")

        result = subprocess.run(
            ["docker", "image", "inspect", image_name],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"Image '{image_name}' not found in local Docker store after build.\n"
            f"{result.stderr.strip()}"
        )

    @pytest.mark.tier3
    def test_docker_compose_build_with_registry_false(self):
        """
        Validate the documented local-only build path (no registry push).
        Mirrors: `make build registry=false` / REGISTRY="" behaviour.
        Uses cached layers so it completes quickly after the first build.
        """
        ok, reason = _docker_available()
        if not ok:
            pytest.skip(f"Docker not available — {reason}")

        result = subprocess.run(
            ["docker", "compose", "build"],
            cwd=str(REPO_ROOT),
            env={**os.environ, "REGISTRY": ""},
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT_SEC,
        )

        assert result.returncode == 0, (
            f"`docker compose build` (REGISTRY='') failed (exit {result.returncode}).\n"
            f"Last stderr:\n{result.stderr.strip()[-1000:]}"
        )
