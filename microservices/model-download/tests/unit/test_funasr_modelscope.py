# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api import main
from src.api.models import ModelHub
from src.core.model_manager import ModelManager
from src.plugins import PLUGINS


FUNASR_SNAPSHOTS = [
    ("iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch", "v2.0.4"),
    ("iic/speech_fsmn_vad_zh-cn-16k-common-pytorch", "v2.0.4"),
    ("iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch", "v2.0.4"),
]


def test_modelscope_is_a_registered_hub():
    assert "modelscope" in PLUGINS
    assert ModelHub("modelscope") is ModelHub.MODELSCOPE


def test_api_downloads_funasr_and_companions_through_modelscope(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "models_dir", str(tmp_path))
    monkeypatch.setattr(main, "model_manager", ModelManager(main.plugin_registry, str(tmp_path)))

    def snapshot(repo_id, *, local_dir, revision):
        assert (repo_id, revision) in FUNASR_SNAPSHOTS
        Path(local_dir, "config.yaml").write_text("model: example\n", encoding="utf-8")
        Path(local_dir, "model.pt").write_bytes(b"weights")
        return local_dir

    with patch("src.plugins.modelscope_plugin.snapshot_download", side_effect=snapshot) as download:
        with TestClient(main.app) as client:
            response = client.post(
                "/models/download?download_path=funasr",
                json={"models": [
                    {"name": name, "hub": "modelscope", "revision": revision}
                    for name, revision in FUNASR_SNAPSHOTS
                ]},
            )
            assert response.status_code == 200, response.text
            job_ids = response.json()["job_ids"]
            assert len(job_ids) == 3
            for job_id in job_ids:
                for _ in range(100):
                    job = client.get(f"/jobs/{job_id}").json()
                    if job["status"] not in {"queued", "downloading"}:
                        break
                    time.sleep(0.01)
                assert job["status"] == "completed", job
                assert job["result"]["source"] == "modelscope"
            assert download.call_count == 3
            for name, _ in FUNASR_SNAPSHOTS:
                assert (tmp_path / "funasr" / "modelscope" / name.replace("/", "_") / "model.pt").is_file()


def test_ephemeral_provisioning_uses_modelscope_and_reuses_valid_snapshots(monkeypatch, tmp_path):
    audio_root = Path(__file__).resolve().parents[3] / "audio-analyzer"
    monkeypatch.syspath_prepend(str(audio_root))
    from utils import provision_models
    from utils.local_models import get_local_model

    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(provision_models, "config", SimpleNamespace(
        models=SimpleNamespace(
            asr=SimpleNamespace(provider="funasr", name="paraformer-zh", diarization=False),
        ),
    ))

    def snapshot(repo_id, *, local_dir, revision):
        assert (repo_id, revision) in FUNASR_SNAPSHOTS
        Path(local_dir, "config.yaml").write_text("model: example\n", encoding="utf-8")
        Path(local_dir, "model.pt").write_bytes(b"weights")
        return local_dir

    with patch("src.plugins.modelscope_plugin.snapshot_download", side_effect=snapshot) as download:
        asyncio.run(provision_models.main())
        assert download.call_count == 3
        for model, revision in FUNASR_SNAPSHOTS:
            directory = get_local_model(
                model, revision, hub="modelscope", models_base_path=str(tmp_path),
                required_files=["config.yaml", "model.pt"],
            )
            assert Path(directory).parent == tmp_path / "funasr" / "modelscope"
        asyncio.run(provision_models.main())
        assert download.call_count == 3
