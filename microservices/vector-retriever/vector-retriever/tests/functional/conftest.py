# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for backend functional filtering tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

import pytest
import requests

from tests.functional.data import DOCUMENTS


REPO_ROOT = Path(__file__).resolve().parents[2]

# Docker Compose project name (derived from first compose file's directory name "docker")
_COMPOSE_PROJECT = "docker"
# Pre-converted OV models volume (created by prior stack runs); used to seed the
# compose-managed ov-models volume so the embedding service skips model conversion.
_OV_MODELS_SOURCE_VOLUME = "docker_ov_models"
_OV_MODELS_DEST_VOLUME = f"{_COMPOSE_PROJECT}_ov-models"
_DEFAULT_TEST_EMBEDDING_MODEL_NAME = "CLIP/clip-vit-b-32"

PORT_MAP = {
    "vdms": {
        "VECTOR_RETRIEVER_HOST_PORT": "6101",
        "EMBEDDING_SERVER_PORT": "9711",
        "VDMS_VDB_HOST_PORT": "5511",
    },
    "milvus": {
        "VECTOR_RETRIEVER_HOST_PORT": "6102",
        "EMBEDDING_SERVER_PORT": "9712",
        "MILVUS_HOST_PORT": "19531",
        "MILVUS_METRICS_HOST_PORT": "9092",
    },
    "pgvector": {
        "VECTOR_RETRIEVER_HOST_PORT": "6103",
        "EMBEDDING_SERVER_PORT": "9713",
        "PGVECTOR_HOST_PORT": "5433",
    },
    "faiss": {
        "VECTOR_RETRIEVER_HOST_PORT": "6104",
        "EMBEDDING_SERVER_PORT": "9714",
    },
}


def _run_compose(backend: str, env: dict[str, str], args: list[str]) -> subprocess.CompletedProcess:
    """Run docker compose command for one backend overlay."""
    command = [
        "docker",
        "compose",
        "-f",
        "docker/compose.yaml",
        "-f",
        f"docker/compose.{backend}.yaml",
        *args,
    ]
    try:
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"docker compose command failed (exit {exc.returncode}):\n"
            f"cmd: {exc.cmd}\n"
            f"stdout: {exc.stdout}\n"
            f"stderr: {exc.stderr}"
        ) from exc



def _wait_for_ready(base_url: str, timeout_seconds: int = 600) -> None:
    """Wait until vector-retriever reports ready status."""
    start = time.time()
    last_error = ""
    while time.time() - start < timeout_seconds:
        try:
            response = requests.get(f"{base_url}/ready", timeout=10)
            if response.status_code == 200:
                payload = response.json()
                if payload.get("status") == "ready":
                    return
                last_error = f"unexpected /ready payload: {payload}"
            else:
                last_error = f"/ready status={response.status_code} body={response.text}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(3)
    raise AssertionError(f"vector-retriever did not become ready: {last_error}")


def _seed_backend_data(backend: str, env: dict[str, str]) -> None:
    """Insert deterministic fixture documents into active backend store.

    For FAISS the exec'd process runs a separate in-memory index (due to
    @lru_cache isolation). After seeding the index is saved to FAISS_INDEX_PATH
    so the service can reload it on restart.
    """
    # For FAISS: save the seeded index to disk so the running service can load it.
    faiss_save_snippet = (
        "from pathlib import Path as _Path\n"
        "_index_path = (settings.FAISS_INDEX_PATH or '').strip()\n"
        "if _index_path and hasattr(store, 'save_local'):\n"
        "    _Path(_index_path).mkdir(parents=True, exist_ok=True)\n"
        "    store.save_local(_index_path)\n"
        "    print('saved faiss index to', _index_path)\n"
    ) if backend == "faiss" else ""

    script = (
        "import json\n"
        "from src.common.settings import settings\n"
        "from src.retriever.backend_factory import get_vectordb\n"
        f"expected_backend = {backend!r}\n"
        "assert settings.RETRIEVER_BACKEND == expected_backend, (\n"
        "    f'backend mismatch: expected {expected_backend!r}, got {settings.RETRIEVER_BACKEND!r}'\n"
        ")\n"
        f"docs = json.loads({json.dumps(DOCUMENTS)!r})\n"
        "store = get_vectordb()\n"
        "texts = [item['page_content'] for item in docs]\n"
        "metadatas = [item['metadata'] for item in docs]\n"
        "ids = [item['metadata']['video_id'] for item in docs]\n"
        "try:\n"
        "    store.add_texts(texts=texts, metadatas=metadatas, ids=ids)\n"
        "except TypeError:\n"
        "    store.add_texts(texts=texts, metadatas=metadatas)\n"
        + faiss_save_snippet
        + "print('seeded', len(docs))\n"
    )

    _run_compose(
        backend,
        env,
        ["exec", "-T", "vector-retriever", "python", "-c", script],
    )


def _verify_seed_visible(base_url: str, expected_count: int) -> None:
    """Ensure seeded records are retrievable before filter-matrix checks."""
    payload = [
        {
            "query_id": "seed-verification",
            "query": "fixture retrieval anchor",
            "top_k": 100,
        }
    ]
    response = requests.post(f"{base_url}/query", json=payload, timeout=60)
    assert response.status_code == 200, response.text
    body = response.json()
    assert not body["errors"], body["errors"]
    assert body["results"], body
    count = body["results"][0]["count"]
    assert count >= expected_count, f"expected at least {expected_count} seeded docs, got {count}"


def _build_env(backend: str) -> dict[str, str]:
    """Build per-backend environment including isolated ports and index name."""
    env = os.environ.copy()
    env.update(PORT_MAP[backend])
    env["RETRIEVER_BACKEND"] = backend

    # Use underscores — some backends (e.g. Milvus) reject hyphens in collection names.
    index_name = f"vr_functional_{backend}_{uuid4().hex[:8]}"
    env["INDEX_NAME"] = index_name
    env["VS_INDEX_NAME"] = index_name
    env["EMBEDDING_MODEL_NAME"] = (
        env.get("EMBEDDING_MODEL_NAME", "").strip() or _DEFAULT_TEST_EMBEDDING_MODEL_NAME
    )
    env["EMBEDDING_DEVICE"] = "CPU"
    env["EMBEDDING_USE_OV"] = "true"
    if backend == "faiss":
        env["FAISS_INDEX_PATH"] = f"/tmp/faiss-functional-{uuid4().hex}"
    return env


@pytest.fixture(scope="session", autouse=True)
def _functional_gate() -> None:
    """Skip expensive backend functional suite unless explicitly enabled."""
    if os.getenv("RUN_FUNCTIONAL_BACKEND_TESTS") != "1":
        pytest.skip(
            "Set RUN_FUNCTIONAL_BACKEND_TESTS=1 to run dockerized backend functional tests.",
            allow_module_level=True,
        )
    if shutil.which("docker") is None:
        pytest.skip("docker CLI is required for functional backend tests", allow_module_level=True)


def _ensure_ov_models_volume() -> None:
    """Seed the compose-managed OV models volume from the cached source volume.

    Called before each backend stack starts.  The copy is skipped when the
    destination volume already exists (carried over from a previous backend
    run in the same session) or when the source volume is absent (the
    embedding service will download models at runtime instead).
    """
    if subprocess.run(
        ["docker", "volume", "inspect", _OV_MODELS_DEST_VOLUME],
        capture_output=True,
    ).returncode == 0:
        return  # volume already exists

    if subprocess.run(
        ["docker", "volume", "inspect", _OV_MODELS_SOURCE_VOLUME],
        capture_output=True,
    ).returncode != 0:
        return  # source not available; embedding service will load models at runtime

    subprocess.run(["docker", "volume", "create", _OV_MODELS_DEST_VOLUME], check=True, capture_output=True)
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{_OV_MODELS_SOURCE_VOLUME}:/src",
            "-v", f"{_OV_MODELS_DEST_VOLUME}:/dst",
            "alpine", "sh", "-c", "cp -r /src/. /dst/",
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="module")
def backend_stack(backend_name: str):
    """Bring up one backend stack, seed fixture records, and tear it down."""
    backend = backend_name
    env = _build_env(backend)
    base_url = f"http://localhost:{env['VECTOR_RETRIEVER_HOST_PORT']}"
    _ensure_ov_models_volume()

    try:
        _run_compose(backend, env, ["up", "-d", "--build"])
        _wait_for_ready(base_url)
        _seed_backend_data(backend, env)
        if backend in ("faiss", "milvus", "vdms"):
            # FAISS: in-memory; restart to reload the saved index from disk.
            # Milvus: search_params may not be populated if the index wasn't
            #         ready when the service first called get_vectordb().
            #         Restart forces a clean re-initialization against the now-
            #         populated collection.
            # VDMS: collection_properties (the list of stored metadata fields
            #       fetched at init time) is stale after seeding in a separate
            #       process.  Restarting forces re-initialization so that all
            #       custom fields are included in similarity-search results.
            _run_compose(backend, env, ["restart", "vector-retriever"])
            _wait_for_ready(base_url)
        _verify_seed_visible(base_url, expected_count=len(DOCUMENTS))
        yield {
            "backend": backend,
            "base_url": base_url,
        }
    finally:
        try:
            _run_compose(backend, env, ["down", "-v", "--remove-orphans"])
        except Exception:  # noqa: BLE001
            pass
