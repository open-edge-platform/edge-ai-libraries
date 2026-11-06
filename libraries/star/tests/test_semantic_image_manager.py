# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for SemanticImageManager with image pipeline."""

import importlib.util
from copy import deepcopy
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys
import types

import pytest
from PIL import Image


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
IMAGE_SRC = WORKSPACE_ROOT / "image" / "src"
SEMANTIC_IMAGE_SRC = WORKSPACE_ROOT / "semantic-img-comp" / "src"
CORE_SRC = WORKSPACE_ROOT / "core" / "python"

for path in (IMAGE_SRC, SEMANTIC_IMAGE_SRC, CORE_SRC):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _bootstrap_image_image_manager() -> None:
    """Load image.image_manager without executing image.__init__."""

    if "image.image_manager" in sys.modules:
        return

    try:
        import image as image_pkg  # type: ignore

        # If the real package imports cleanly, keep it and avoid introducing a stub.
        if hasattr(image_pkg, "ImageControlMsg") and hasattr(image_pkg, "SemanticImageManager"):
            return
    except Exception:
        image_pkg = None

    image_manager_path = IMAGE_SRC / "image" / "image_manager.py"
    if not image_manager_path.exists():
        # Sibling "image" repo isn't checked out alongside this one; skip module collection.
        pytest.skip("sibling 'image' repo not available for cross-package bootstrap", allow_module_level=True)

    image_pkg = sys.modules.get("image") or image_pkg
    if image_pkg is None:
        image_pkg = types.ModuleType("image")
        image_pkg.__path__ = [str(IMAGE_SRC / "image")]
        sys.modules["image"] = image_pkg

    spec = importlib.util.spec_from_file_location(
        "image.image_manager",
        image_manager_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to bootstrap image.image_manager")
    module = importlib.util.module_from_spec(spec)
    sys.modules["image.image_manager"] = module
    spec.loader.exec_module(module)
    setattr(sys.modules["image"], "image_manager", module)

    # Mirror the public package exports expected by other smoke tests.
    setattr(sys.modules["image"], "ImageManager", module.ImageManager)
    setattr(sys.modules["image"], "SimpleImageManager", module.SimpleImageManager)
    from image.image_control_msg import ImageControlMsg
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    setattr(sys.modules["image"], "ImageControlMsg", ImageControlMsg)
    setattr(sys.modules["image"], "SemanticImageManager", SemanticImageManager)


_bootstrap_image_image_manager()


def _create_test_jpeg(width: int = 8, height: int = 6, color: str = "red") -> bytes:
    """Create a test JPEG image."""
    img = Image.new("RGB", (width, height), color=color)
    buff = BytesIO()
    img.save(buff, format="JPEG")
    return buff.getvalue()


def _cfg():
    """Load the canonical semantic pipeline config and clone it for tests."""
    from semantic_img_comp.utils.config import load_config

    config_path = Path(__file__).resolve().parents[2] / "semantic-img-comp" / "configs" / "default.yaml"
    cfg = load_config(str(config_path))
    return deepcopy(cfg)


def test_semantic_image_manager_init(tmp_path):
    """Test SemanticImageManager initialization."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    manager = SemanticImageManager(
        cfg=_cfg(),
        service_name="test_encoder",
        output_dir=tmp_path,
    )

    assert manager.service_name == "test_encoder"
    assert manager.output_dir == tmp_path
    assert manager._frame_counter == 0


def test_semantic_image_manager_process_image_rejects_empty_bytes():
    """Test that process_image rejects empty input."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    manager = SemanticImageManager(cfg=_cfg(), service_name="test")

    with pytest.raises(ValueError, match="must not be empty"):
        manager.process_image(b"")


def test_semantic_image_manager_warmup_initializes_codec_dependencies(monkeypatch):
    """Test that warmup eagerly creates the bridge, encoder, and decoder."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager
    import semantic_img_comp.integration.semantic_codec_bridge as bridge_module

    events = []

    class FakeBridge:
        def __init__(self, cfg):
            self.cfg = cfg
            events.append("bridge")

        @property
        def encoder(self):
            events.append("encoder")
            return object()

        @property
        def decoder(self):
            events.append("decoder")
            return object()

    monkeypatch.setattr(bridge_module, "SemanticCodecBridge", FakeBridge)

    cfg = _cfg()
    manager = SemanticImageManager(cfg=cfg, service_name="test")

    manager.warmup()

    assert isinstance(manager._bridge, FakeBridge)
    assert manager._bridge.cfg is cfg
    assert events == ["bridge", "encoder", "decoder"]


def test_semantic_image_manager_process_payload_rejects_empty_bytes():
    """Test that process_payload rejects empty input."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    manager = SemanticImageManager(cfg=_cfg(), service_name="test")

    with pytest.raises(ValueError, match="must not be empty"):
        manager.process_payload(b"")


def test_semantic_image_manager_process_image_increments_frame_counter():
    """Test that frame counter increments with each process_image call."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager
    import semantic_img_comp.integration.semantic_codec_bridge as bridge_module

    manager = SemanticImageManager(cfg=_cfg(), service_name="test")
    manager.set_compression_level(1)

    # Mock the bridge to avoid heavy dependencies
    mock_bridge = MagicMock()
    mock_result = SimpleNamespace(
        payload=b"payload_1",
        size_log={"header": 1, "background": 2},
        img_data=SimpleNamespace(img_idx=1, org_img_size=(8, 6), crops=[]),
        detections=[],
    )
    mock_bridge.encode_from_jpeg.return_value = mock_result
    manager._bridge = mock_bridge

    jpeg_bytes = _create_test_jpeg()

    payload_1 = manager.process_image(jpeg_bytes)
    assert manager._frame_counter == 1
    assert payload_1 == b"payload_1"

    payload_2 = manager.process_image(jpeg_bytes)
    assert manager._frame_counter == 2

    # Verify frame IDs were passed correctly
    assert mock_bridge.encode_from_jpeg.call_count == 2
    assert mock_bridge.encode_from_jpeg.call_args_list[0][1]["img_id"] == 1
    assert mock_bridge.encode_from_jpeg.call_args_list[1][1]["img_id"] == 2
    assert mock_bridge.encode_from_jpeg.call_args_list[0][1]["queue_length"] == 0
    assert mock_bridge.encode_from_jpeg.call_args_list[0][1]["compression_level"] == 1
    assert mock_bridge.encode_from_jpeg.call_args_list[1][1]["queue_length"] == 0
    assert mock_bridge.encode_from_jpeg.call_args_list[1][1]["compression_level"] == 1

    status = manager.performance_status()
    assert status["frames_encoded"] == 2
    assert status["frames_decoded"] == 0
    assert status["last_encode"]["frame_id"] == 2
    assert status["last_encode"]["payload_bytes"] == len(b"payload_1")
    assert status["encode_avg_ms"]["wall_encode"] >= 0
    assert status["queue"]["pending_images"] == 0


def test_semantic_image_manager_process_image_level_zero_bypasses_encode(tmp_path):
    """Test compression level 0 keeps the original JPEG bytes and skips bridge.encode_from_jpeg."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    manager = SemanticImageManager(cfg=_cfg(), service_name="test", output_dir=tmp_path)
    jpeg_bytes = _create_test_jpeg(color="yellow")
    mock_bridge = MagicMock()
    manager._bridge = mock_bridge

    payload = manager.process_image(jpeg_bytes)

    assert payload == jpeg_bytes
    mock_bridge.encode_from_jpeg.assert_not_called()

    status = manager.performance_status()
    assert status["frames_encoded"] == 1
    assert status["last_encode"]["payload_bytes"] == len(jpeg_bytes)
    assert status["last_encode"]["comp_rate"] == 1.0
    assert status["last_encode"]["size_log"] == {"jpeg_passthrough": len(jpeg_bytes)}

    frame_log_path = tmp_path / "log" / "frame_000001_enc.json"
    assert not frame_log_path.exists()

    jsonl_path = tmp_path / "log" / "enc_log.json"
    assert jsonl_path.exists()
    with open(jsonl_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    metadata = records[-1]

    assert metadata["img_id"] == 1
    assert metadata["img_idx"] == 1
    assert metadata["org_jpeg_bytes"] == len(jpeg_bytes)
    assert metadata["payload"]["total_bytes"] == len(jpeg_bytes)
    assert metadata["payload"]["bytes_by_bucket"] == {"jpeg_passthrough": len(jpeg_bytes)}
    assert "file_name" in metadata and metadata["file_name"] is None
    assert metadata["fast_path_selected"] is False
    assert metadata["fast_path_bg_selected"] is False
    assert metadata["fast_path_obj_selected"] is False
    assert metadata["obj_detection_skipped"] is True
    assert metadata["metrics"]["comp_rate"] == 1.0
    assert metadata["metrics"]["comp_level"] == 0
    assert metadata["detections"] == []


def test_semantic_image_manager_process_payload_calls_bridge_decode(tmp_path):
    """Test that process_payload delegates to bridge.decode_payload."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    manager = SemanticImageManager(cfg=_cfg(), service_name="test", output_dir=tmp_path)

    # Mock the bridge
    recon_img = Image.new("RGB", (8, 6), color="blue")
    mock_result = SimpleNamespace(image=recon_img, img_idx=1)
    mock_bridge = MagicMock()
    mock_bridge.decode_payload.return_value = mock_result
    mock_bridge._save_jpeg_from_image.return_value = b"jpeg_reconstructed"
    manager._bridge = mock_bridge

    payload = b"test_payload"
    jpeg_out = manager.process_payload(payload, compression_level=1)

    assert jpeg_out == b"jpeg_reconstructed"
    mock_bridge.decode_payload.assert_called_once_with(b"test_payload")
    mock_bridge._save_jpeg_from_image.assert_called_once()

    status = manager.performance_status()
    assert status["frames_decoded"] == 1
    assert status["last_decode"]["payload_bytes"] == len(payload)
    assert status["last_decode"]["recon_jpeg_bytes"] == len(b"jpeg_reconstructed")
    assert status["decode_avg_ms"] >= 0


def test_semantic_image_manager_process_payload_level_zero_bypasses_decode(tmp_path):
    """Test compression level 0 bypasses semantic decode and still emits decode artifacts."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    manager = SemanticImageManager(cfg=_cfg(), service_name="test", output_dir=tmp_path)

    payload = _create_test_jpeg(color="yellow")
    mock_bridge = MagicMock()
    mock_bridge._save_jpeg_from_image.return_value = b"jpeg_passthrough"
    manager._bridge = mock_bridge

    jpeg_out = manager.process_payload(payload, compression_level=0)

    assert jpeg_out == b"jpeg_passthrough"
    mock_bridge.decode_payload.assert_not_called()
    mock_bridge._save_jpeg_from_image.assert_called_once()

    saved_result = mock_bridge._save_jpeg_from_image.call_args[0][0]
    assert saved_result.size == (8, 6)

    img_path = tmp_path / "recon_images" / "frame_000001.jpeg"
    assert not img_path.exists()

    status = manager.performance_status()
    assert status["frames_decoded"] == 1
    assert status["last_decode"]["img_idx"] == 1
    assert status["last_decode"]["payload_bytes"] == len(payload)
    assert status["last_decode"]["recon_jpeg_bytes"] == len(b"jpeg_passthrough")


def test_semantic_image_manager_saves_encoding_metadata(tmp_path):
    """Test that encoding metadata is saved to output directory."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    manager = SemanticImageManager(cfg=_cfg(), service_name="test", output_dir=tmp_path)
    manager.set_compression_level(1)

    # Mock the bridge
    mock_result = SimpleNamespace(
        payload=b"payload",
        size_log={"header": 1, "background": 2, "objects": 0},
        img_data=SimpleNamespace(
            img_idx=5,
            org_img_size=(8, 6),
            org_jpeg_bytes=100,
            crops=[SimpleNamespace(obj_size=(0, 0))],
        ),
        detections=[{"category": "vehicle", "confidence": 0.95}],
        timing_ms={"yolo": 1.0, "obj_comp": 2.0, "bg_comp": 3.0, "enc_total": 6.0},
        bg_quota_bytes=24,
        obj_quota_bytes=12,
        comp_rate=33.3,
        aggregated_comp_rate=44.4,
        tar_comp_rate=55.5,
        comp_level=1,
    )
    mock_bridge = MagicMock()
    mock_bridge.encode_from_jpeg.return_value = mock_result
    manager._bridge = mock_bridge

    jpeg_bytes = _create_test_jpeg()
    manager.process_image(jpeg_bytes)

    frame_log_path = tmp_path / "log" / "frame_000001_enc.json"
    assert not frame_log_path.exists()

    jsonl_path = tmp_path / "log" / "enc_log.json"
    assert jsonl_path.exists()
    with open(jsonl_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    metadata = records[-1]

    assert metadata["frame_id"] == 1
    assert metadata["img_id"] == 5
    assert metadata["img_idx"] == 5
    assert metadata["org_img_size"] == [8, 6]
    assert metadata["org_jpeg_bytes"] == 100
    assert metadata["image"]["orig_jpeg_bytes"] == 100
    assert metadata["objects"]["total_pixels"] == 0
    assert metadata["runtime_ms"]["enc_total"] == 6.0
    assert metadata["background"]["quota_bytes"] == 24
    assert metadata["objects"]["quota_bytes"] == 12
    assert "file_name" in metadata and metadata["file_name"] is None
    assert metadata["fast_path_selected"] is False
    assert metadata["fast_path_bg_selected"] is False
    assert metadata["fast_path_obj_selected"] is False
    assert metadata["obj_detection_skipped"] is False
    assert metadata["metrics"]["comp_rate"] == 33.3
    assert metadata["metrics"]["aggregated_comp_rate"] == 44.4
    assert metadata["metrics"]["tar_comp_rate"] == 55.5
    assert metadata["metrics"]["comp_level"] == 1

    with open(jsonl_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    assert records
    assert records[-1]["img_id"] == 5
    assert records[-1]["img_idx"] == 5
    assert records[-1]["runtime_ms"]["enc_total"] == 6.0
    assert records[-1]["background"]["quota_bytes"] == 24
    assert records[-1]["objects"]["quota_bytes"] == 12
    assert records[-1]["metrics"]["comp_rate"] == 33.3
    assert records[-1]["metrics"]["aggregated_comp_rate"] == 44.4
    assert records[-1]["metrics"]["tar_comp_rate"] == 55.5
    assert records[-1]["metrics"]["comp_level"] == 1


def test_semantic_image_manager_semantic_decode_skips_recon_image_save(tmp_path):
    """Test semantic decode logs artifacts but does not persist reconstructed JPEG files."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    manager = SemanticImageManager(cfg=_cfg(), service_name="test", output_dir=tmp_path)

    # Mock the bridge
    recon_img = Image.new("RGB", (8, 6), color="green")
    mock_result = SimpleNamespace(image=recon_img, img_idx=7, mask=None, org_img_size=(8, 6))
    mock_bridge = MagicMock()
    mock_bridge.decode_payload.return_value = mock_result
    mock_bridge._save_jpeg_from_image.return_value = b"jpeg_data"
    manager._bridge = mock_bridge

    payload = b"test_payload"
    manager.process_payload(payload, compression_level=1)

    img_path = tmp_path / "recon_images" / "frame_000007.jpeg"
    assert not img_path.exists()

    dec_jsonl_path = tmp_path / "log" / "dec_log.json"
    assert dec_jsonl_path.exists()
    with open(dec_jsonl_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    assert records
    assert records[-1]["img_idx"] == 7
    assert records[-1]["recon_image_path"] is None


def test_semantic_image_manager_clears_previous_runtime_logs_on_startup(tmp_path):
    """Test each manager run starts with fresh enc/dec JSON logs."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    log_dir = tmp_path / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "enc_log.json").write_text('{"event":"old_enc"}\n', encoding="utf-8")
    (log_dir / "dec_log.json").write_text('{"event":"old_dec"}\n', encoding="utf-8")

    SemanticImageManager._INITIALIZED_LOG_DIRS.clear()
    manager = SemanticImageManager(cfg=_cfg(), service_name="test", output_dir=tmp_path)

    mock_result = SimpleNamespace(
        payload=b"payload",
        size_log={"header": 1},
        img_data=SimpleNamespace(img_idx=1, org_img_size=(8, 6), org_jpeg_bytes=10, crops=[]),
        detections=[],
    )
    mock_bridge = MagicMock()
    mock_bridge.encode_from_jpeg.return_value = mock_result
    mock_bridge._save_jpeg_from_image.return_value = b"jpeg_passthrough"
    manager._bridge = mock_bridge
    manager.set_compression_level(1)

    manager.process_image(_create_test_jpeg())
    manager.process_payload(_create_test_jpeg(color="yellow"), compression_level=0)

    with open(log_dir / "enc_log.json", "r", encoding="utf-8") as f:
        enc_records = [json.loads(line) for line in f if line.strip()]
    with open(log_dir / "dec_log.json", "r", encoding="utf-8") as f:
        dec_records = [json.loads(line) for line in f if line.strip()]

    assert enc_records and all(record.get("event") != "old_enc" for record in enc_records)
    assert dec_records and all(record.get("event") != "old_dec" for record in dec_records)


def test_semantic_image_manager_skips_json_logs_when_disabled(tmp_path):
    """Test semantic bridge does not create enc/dec logs when write_json_logs is false."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    cfg = _cfg()
    cfg.io.write_json_logs = False
    SemanticImageManager._INITIALIZED_LOG_DIRS.clear()
    manager = SemanticImageManager(cfg=cfg, service_name="test", output_dir=tmp_path)
    manager.set_compression_level(1)

    mock_result = SimpleNamespace(
        payload=b"payload",
        size_log={"header": 1},
        img_data=SimpleNamespace(img_idx=1, org_img_size=(8, 6), org_jpeg_bytes=10, crops=[]),
        detections=[],
    )
    mock_bridge = MagicMock()
    mock_bridge.encode_from_jpeg.return_value = mock_result
    mock_bridge.decode_payload.return_value = SimpleNamespace(
        image=Image.new("RGB", (8, 6), color="blue"),
        img_idx=1,
        mask=None,
        org_img_size=(8, 6),
    )
    mock_bridge._save_jpeg_from_image.return_value = b"jpeg_data"
    manager._bridge = mock_bridge

    manager.process_image(_create_test_jpeg())
    manager.process_payload(b"semantic_payload", compression_level=1)

    assert not (tmp_path / "log" / "enc_log.json").exists()
    assert not (tmp_path / "log" / "dec_log.json").exists()


def test_image_readiness_status_transitions():
    from image.status import ImageReadiness

    readiness = ImageReadiness(service_name="image-transform", transform_name="d3x-image-transform")
    assert readiness.as_dict()["ready"] is False
    assert readiness.as_dict()["state"] == "starting"

    readiness.mark_loading("loading models")
    assert readiness.as_dict()["state"] == "loading"

    readiness.mark_ready()
    payload = readiness.as_dict()
    assert payload["ready"] is True
    assert payload["state"] == "ready"
    assert "ready_after_seconds" in payload


def test_semantic_image_manager_process_image_invalid_level_defaults_to_two():
    """Test invalid runtime compression levels are normalized to level 2."""
    from semantic_img_comp.integration.semantic_image_manager import SemanticImageManager

    manager = SemanticImageManager(cfg=_cfg(), service_name="test")
    manager.get_compression_level = MagicMock(return_value="invalid")

    mock_result = SimpleNamespace(
        payload=b"payload",
        size_log={"header": 1},
        img_data=SimpleNamespace(img_idx=1, org_img_size=(8, 6), crops=[]),
        detections=[],
    )
    mock_bridge = MagicMock()
    mock_bridge.encode_from_jpeg.return_value = mock_result
    manager._bridge = mock_bridge

    manager.process_image(_create_test_jpeg())

    assert mock_bridge.encode_from_jpeg.call_count == 1
    assert mock_bridge.encode_from_jpeg.call_args[1]["compression_level"] == 2

