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
import tempfile
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

    @pytest.mark.tier3
    def test_docker_compose_config_resolves_accel_mount_path(self):
        """Ensure ACCEL_MOUNT_PATH host value maps to fixed container NPU path."""
        if shutil.which("docker") is None:
            pytest.skip("docker binary not found on PATH")

        host_accel = "/dev/accel/accel0"
        env = {**os.environ, "ACCEL_MOUNT_PATH": host_accel}
        result = subprocess.run(
            ["docker", "compose", "config"],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, (
            f"`docker compose config` failed (exit {result.returncode}).\n"
            f"Last stderr:\n{result.stderr.strip()[-1000:]}"
        )

        cfg = yaml.safe_load(result.stdout)
        service = cfg.get("services", {}).get("audio-analyzer", {})
        devices = service.get("devices", [])

        accel_map = next(
            (
                d for d in devices
                if isinstance(d, dict)
                and d.get("target") == "/dev/accel/accel0"
            ),
            None,
        )
        assert accel_map is not None, "Missing /dev/accel/accel0 device mapping in compose config"
        assert accel_map.get("source") == host_accel

    @pytest.mark.tier3
    def test_docker_compose_config_accel_mount_path_fallbacks_to_dev_null(self):
        """Ensure ACCEL_MOUNT_PATH fallback maps /dev/null when variable is unset."""
        if shutil.which("docker") is None:
            pytest.skip("docker binary not found on PATH")

        env = {k: v for k, v in os.environ.items() if k != "ACCEL_MOUNT_PATH"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=True) as empty_env_file:
            result = subprocess.run(
                ["docker", "compose", "--env-file", empty_env_file.name, "config"],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )

        assert result.returncode == 0, (
            f"`docker compose --env-file <empty> config` failed (exit {result.returncode}).\n"
            f"Last stderr:\n{result.stderr.strip()[-1000:]}"
        )

        cfg = yaml.safe_load(result.stdout)
        service = cfg.get("services", {}).get("audio-analyzer", {})
        devices = service.get("devices", [])

        accel_map = next(
            (
                d for d in devices
                if isinstance(d, dict)
                and d.get("target") == "/dev/accel/accel0"
            ),
            None,
        )
        assert accel_map is not None, "Missing /dev/accel/accel0 device mapping in compose config"
        assert accel_map.get("source") == "/dev/null"
