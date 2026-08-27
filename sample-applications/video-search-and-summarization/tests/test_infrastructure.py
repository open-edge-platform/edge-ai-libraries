# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
TIER 1 — Infrastructure Gate Tests

These tests verify the VSS stack is healthy at the platform level
before any functional tests are run.

Run with:
    cd test-functional/
    pytest test_infrastructure.py -v

Tests in this file:
    T1.1 - test_all_containers_running
    T1.2 - test_nginx_gateway_reachable
    T1.3 - covered by test_health.py (TestHealth class)
    T1.4 - covered by test_health.py (TestHealth class)
    T1.5 - test_postgres_connection_healthy
    T1.6 - test_minio_service_running
    T1.7 - test_rabbitmq_service_running        (skipped in search-only mode)
    T1.8 - test_model_server_running            (handles both ovms-service and vllm-cpu-service)
"""

import json
import subprocess

import pytest
import requests


class TestInfrastructure:

    # ──────────────────────────────────────────────────────────────────────────
    # T1.1 — All containers are running (no Exited / unhealthy containers)
    # ──────────────────────────────────────────────────────────────────────────

    def test_all_containers_running(self):
        result = subprocess.run(
            ["docker", "compose", "-p", "docker", "ps", "--format", "json"],
            capture_output=True,   # capture what the command prints
            text=True,             # give us text (str), not raw bytes
        )

        assert result.returncode == 0, (
            f"'docker compose ps' command failed.\n"
            f"Error output: {result.stderr}"
        )

        raw_output = result.stdout.strip()
        assert raw_output, (
            "No output from 'docker compose ps'. "
            "Is the VSS stack deployed? Try: source setup.sh --summary (or --search)"
        )

        containers = []
        for line in raw_output.splitlines():
            line = line.strip()
            if line:
                containers.append(json.loads(line))

        assert len(containers) > 0, (
            "No containers found in the 'docker' compose project. "
            "Deploy the stack first."
        )

        bad_containers = []
        for container in containers:
            # Docker reports state as "running", "exited", "paused", etc.
            state = container.get("State", "").lower()
            name  = container.get("Name", "unknown")
            if state in ("exited", "dead"):
                bad_containers.append(f"  - {name}  →  State: {state}")

        assert not bad_containers, (
            "The following containers are NOT running:\n"
            + "\n".join(bad_containers)
            + "\n\nFix: docker compose -p docker logs <service-name>"
        )


    def test_nginx_gateway_reachable(self, base_url):
        try:
            response = requests.get(base_url, timeout=10)
            assert response.status_code < 500, (
                f"nginx gateway returned server error: {response.status_code}"
            )
        except requests.exceptions.ConnectionError:
            pytest.fail(
                f"Cannot reach nginx gateway at {base_url}. "
                "Is the stack running? Check: docker compose -p docker ps"
            )


    # ──────────────────────────────────────────────────────────────────────────
    # T1.5 — PostgreSQL connection healthy (no DB errors in PM logs)
    # ──────────────────────────────────────────────────────────────────────────

    def test_postgres_connection_healthy(self):
        result = subprocess.run(
            ["docker", "compose", "-p", "docker", "logs", "--tail=100", "pipeline-manager"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Could not fetch pipeline-manager logs.\nError: {result.stderr}"
        )

        # docker logs writes to both stdout and stderr — merge both
        logs = result.stdout + result.stderr

        error_keywords = [
            "ECONNREFUSED",
            "password authentication failed",
            "role does not exist",
            "relation does not exist",
            "connection refused",
            "connection terminated",
        ]

        found_errors = []
        for line in logs.splitlines():
            for keyword in error_keywords:
                if keyword.lower() in line.lower():
                    found_errors.append(line.strip())
                    break  # don't double-count the same line

        assert not found_errors, (
            "Database connection errors found in pipeline-manager logs:\n"
            + "\n".join(found_errors)
            + "\n\nFix: source setup.sh --clean-data  then redeploy"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # T1.6 — MinIO object store container is running
    # ──────────────────────────────────────────────────────────────────────────

    def test_minio_service_running(self):
        result = subprocess.run(
            ["docker", "compose", "-p", "docker", "ps", "--format", "json", "minio-service"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Could not query minio-service container.\nError: {result.stderr}"
        )

        raw_output = result.stdout.strip()
        assert raw_output, (
            "minio-service container not found. Is the VSS stack deployed?"
        )

        container = json.loads(raw_output.splitlines()[0])
        state = container.get("State", "").lower()
        name  = container.get("Name", "minio-service")

        assert state == "running", (
            f"minio-service is not running. Current state: '{state}'\n"
            f"Fix: docker compose -p docker logs {name}"
        )

    def test_rabbitmq_service_running(self):
        result = subprocess.run(
            ["docker", "compose", "-p", "docker", "ps", "--format", "json", "rabbitmq-service"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Could not query rabbitmq-service container.\nError: {result.stderr}"
        )

        raw_output = result.stdout.strip()

        # No output means the container was never created — this is expected in
        # search-only mode where compose.summary.yaml is not included.
        if not raw_output:
            pytest.skip(
                "rabbitmq-service container not found — "
                "this is expected in search-only mode (--search). "
                "Deploy with --summary or --summary --search to test RabbitMQ."
            )

        container = json.loads(raw_output.splitlines()[0])
        state = container.get("State", "").lower()
        name  = container.get("Name", "rabbitmq-service")

        assert state == "running", (
            f"rabbitmq-service is not running. Current state: '{state}'\n"
            f"Fix: docker compose -p docker logs {name}"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Helper — reusable container state lookup
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_container_state(service_name):
        result = subprocess.run(
            ["docker", "compose", "-p", "docker", "ps", "--format", "json", service_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None  # container not part of this deployment
        container = json.loads(result.stdout.strip().splitlines()[0])
        return container.get("State", "").lower()

    # ──────────────────────────────────────────────────────────────────────────
    # T1.8 — Model server (OVMS or vLLM) is running
    # ──────────────────────────────────────────────────────────────────────────

    def test_model_server_running(self):
        ovms_state = self._get_container_state("ovms-service")
        vllm_state = self._get_container_state("vllm-cpu-service")

        if ovms_state is None and vllm_state is None:
            rabbitmq_state = self._get_container_state("rabbitmq-service")
            if rabbitmq_state is None:
                pytest.skip(
                    "No model server found (ovms-service or vllm-cpu-service) — "
                    "this is expected in search-only mode (--search). "
                    "Deploy with --summary or --summary --search to test the model server."
                )
            # RabbitMQ is present but model server is missing → real failure
            pytest.fail(
                "No model server found (neither ovms-service nor vllm-cpu-service) "
                "but rabbitmq-service is running — summary mode is deployed but the "
                "model server is missing.\n"
                "Fix: redeploy with --summary or check your compose files."
            )

        if ovms_state is not None:
            assert ovms_state == "running", (
                f"ovms-service is deployed but not running. State: '{ovms_state}'\n"
                "Fix: docker compose -p docker logs ovms-service"
            )

        if vllm_state is not None:
            assert vllm_state == "running", (
                f"vllm-cpu-service is deployed but not running. State: '{vllm_state}'\n"
                "Fix: docker compose -p docker logs vllm-cpu-service"
            )