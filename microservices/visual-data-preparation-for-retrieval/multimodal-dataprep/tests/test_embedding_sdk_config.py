# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from src.core.embedding import client


def test_configure_mme_sdk_environment_translates_dataprep_settings(monkeypatch):
    monkeypatch.setattr(client.settings, "EMBEDDING_BATCH_SIZE", 24)
    monkeypatch.setattr(client.settings, "OV_PERFORMANCE_MODE", "THROUGHPUT")
    monkeypatch.setattr(client.settings, "MAX_PARALLEL_WORKERS", 6)
    monkeypatch.delenv("INFER_BATCH_SIZE", raising=False)
    monkeypatch.delenv("OV_PERFORMANCE_MODE", raising=False)
    monkeypatch.delenv("MAX_PARALLEL_WORKERS", raising=False)

    client._configure_mme_sdk_environment()

    assert client.os.environ["INFER_BATCH_SIZE"] == "24"
    assert client.os.environ["OV_PERFORMANCE_MODE"] == "THROUGHPUT"
    assert client.os.environ["MAX_PARALLEL_WORKERS"] == "6"


def test_configure_mme_sdk_environment_clears_unset_worker_override(monkeypatch):
    monkeypatch.setattr(client.settings, "EMBEDDING_BATCH_SIZE", 32)
    monkeypatch.setattr(client.settings, "OV_PERFORMANCE_MODE", "LATENCY")
    monkeypatch.setattr(client.settings, "MAX_PARALLEL_WORKERS", None)
    monkeypatch.setenv("MAX_PARALLEL_WORKERS", "99")

    client._configure_mme_sdk_environment()

    assert client.os.environ["INFER_BATCH_SIZE"] == "32"
    assert client.os.environ["OV_PERFORMANCE_MODE"] == "LATENCY"
    assert "MAX_PARALLEL_WORKERS" not in client.os.environ
