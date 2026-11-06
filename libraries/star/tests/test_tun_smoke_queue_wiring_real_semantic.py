# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Integration smoke: verify queue length wiring through the real SemanticCodecBridge."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
import threading
from typing import Any

import pytest

grpc = pytest.importorskip("grpc")
pytest.importorskip("PIL")

from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = WORKSPACE_ROOT / "semantic-img-comp" / "tests" / "fixtures"
INPUT_IMAGE_DIR = FIXTURES_DIR / "sample_images"
OUTPUT_DIR = FIXTURES_DIR / "output"


def _resolve_avif_tools_dir() -> Path | None:
    tools_root = WORKSPACE_ROOT / "semantic-img-comp" / "tools"
    candidates = [
        tools_root,
        tools_root / "bin",
        tools_root / "libavif",
        tools_root / "libavif" / "bin",
    ]
    for directory in candidates:
        if not directory.exists():
            continue
        has_enc = (directory / "avifenc").exists() or (directory / "avifenc.exe").exists()
        has_dec = (directory / "avifdec").exists() or (directory / "avifdec.exe").exists()
        if has_enc and has_dec:
            return directory
    return None


def _load_helicopter_frames(limit: int = 10) -> list[tuple[str, bytes]]:
    candidates = sorted(INPUT_IMAGE_DIR.glob("*.jpg"))
    if not candidates:
        candidates = sorted(INPUT_IMAGE_DIR.glob("*.jpeg"))
    if not candidates:
        candidates = sorted(INPUT_IMAGE_DIR.glob("*.png"))
    selected = candidates[:limit]
    if not selected:
        pytest.fail(f"missing helicopter fixture images in {INPUT_IMAGE_DIR}")

    frames: list[tuple[str, bytes]] = []
    for idx in range(limit):
        frame = selected[idx % len(selected)]
        frames.append((f"{idx + 1:04d}_{frame.name}", frame.read_bytes()))
    return frames


def _build_mjpeg_stream(frames: list[tuple[str, bytes]]) -> bytes:
    header = b"HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n"
    parts = [header]
    for _, jpeg_bytes in frames:
        parts.append(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n")
    return b"".join(parts)


def _forward_message(chunk: bytes) -> svred_pb2.OrchestratorToTransformMessage:
    message = svred_pb2.OrchestratorToTransformMessage()
    message.payload = chunk
    message.header.src_ip = "10.20.1.1"
    message.header.src_port = 5001
    message.header.dst_ip = "10.20.2.2"
    message.header.dst_port = 5002
    message.header.proto = 6
    return message


async def _iter_messages(messages: list[object]):
    for message in messages:
        yield message


async def _cancel(task: asyncio.Task[object]) -> None:
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def _start_tun_server(
    *,
    service_name: str,
    transform_name: str,
    cfg: Any,
) -> tuple[SemanticImageManager, TUNInterface, grpc.aio.Server, str, list[asyncio.Task[None]]]:
    manager = SemanticImageManager(
        cfg=cfg,
        service_name=service_name,
        transform_name=transform_name,
        output_dir=OUTPUT_DIR,
    )
    # Use semantic encode path so queue-length wiring reaches the real bridge.
    manager.set_compression_level(1)
    await asyncio.to_thread(manager.warmup)

    tun = TUNInterface(
        service_name,
        transform_name,
        svred_module=manager,
        control_message_cls=ImageControlMsg,
        loop_interval=0.01,
    )
    server = grpc.aio.server()
    tun.register(server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    if port == 0:
        raise RuntimeError(f"failed to bind TCP socket for {service_name}")

    tasks = [asyncio.create_task(coro) for coro in tun.create_tasks()]
    return manager, tun, server, f"127.0.0.1:{port}", tasks


@pytest.mark.integration
def test_tun_queue_wiring_uses_real_semantic_bridge_and_emits_semantic_payloads() -> None:
    from semantic_img_comp.utils.config import load_config

    async def _run() -> None:
        original_path: str | None = None
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        manifest_path = OUTPUT_DIR / "queue_wiring_real_semantic_manifest.json"
        if manifest_path.exists():
            manifest_path.unlink()
        for path in OUTPUT_DIR.glob("queue_wiring_real_semantic_*.bin"):
            path.unlink()
        for path in OUTPUT_DIR.glob("queue_wiring_real_semantic_recon_*.jpeg"):
            path.unlink()
        for path in (OUTPUT_DIR / "recon_images", OUTPUT_DIR / "recon_masks", OUTPUT_DIR / "log"):
            if path.exists():
                shutil.rmtree(path)

        config_path = WORKSPACE_ROOT / "semantic-img-comp" / "configs" / "default.yaml"
        if not config_path.exists():
            pytest.skip(f"missing semantic config: {config_path}")
        cfg = load_config(str(config_path))
        cfg.io.write_json_logs = False

        configured_model_path = Path(cfg.model.enc_yolo_model_path)
        if not configured_model_path.exists():
            env_model_path = os.getenv("IMAGE_MODEL_PATH")
            local_model_candidates = [
                WORKSPACE_ROOT / "semantic-img-comp" / "models" / "obj_det_models" / "yolov8m_int8_openvino_model",
                WORKSPACE_ROOT / "semantic-img-comp" / "models" / "obj_det_models" / "yolov8m.pt",
            ]
            if env_model_path:
                local_model_candidates.insert(0, Path(env_model_path))
            resolved = next((p for p in local_model_candidates if str(p) and p.exists()), None)
            if resolved is None:
                pytest.skip(
                    f"missing encoder model path: {cfg.model.enc_yolo_model_path}; "
                    "set IMAGE_MODEL_PATH or place a local model under semantic-img-comp/models/obj_det_models"
                )
            cfg.model.enc_yolo_model_path = resolved

        avif_tools_dir = _resolve_avif_tools_dir()
        avif_search_path = os.environ.get("PATH", "")
        if avif_tools_dir is not None:
            avif_search_path = f"{avif_tools_dir}{os.pathsep}{avif_search_path}"

        if shutil.which("avifenc", path=avif_search_path) is None or shutil.which("avifdec", path=avif_search_path) is None:
            pytest.skip(
                "missing AVIF tools; expected avifenc/avifdec on PATH or under semantic-img-comp/tools"
            )

        if avif_tools_dir is not None:
            original_path = os.environ.get("PATH")
            os.environ["PATH"] = avif_search_path

        # Low thresholds make backlog transitions observable in a short smoke run.
        cfg.pipeline_manager.queue_backlog_threshold_1 = 1
        cfg.pipeline_manager.queue_backlog_threshold_2 = 2
        cfg.pipeline_manager.queue_backlog_threshold_3 = 3
        cfg.pipeline_manager.fast_full_hysteresis_exit = 1.5
        cfg.pipeline_manager.skip_obj_hysteresis_exit = 2.5

        manager, tun, server, address, tasks = await _start_tun_server(
            service_name="image-real-semantic-queue-test",
            transform_name="image-real-semantic-queue",
            cfg=cfg,
        )

        queue_lengths_seen: list[int] = []
        fast_flags: list[bool] = []
        skip_flags: list[bool] = []
        first_started = threading.Event()
        release_first = threading.Event()
        seen_first = False

        bridge = manager.bridge
        orig_encode = bridge.encode_from_jpeg
        orig_image_control_init = ImageControlMsg.__init__

        def _compat_image_control_init(self, *args, compression_level=None, **kwargs):
            # ImageManager currently passes compression_level; drop it for ImageControlMsg compatibility.
            del compression_level
            return orig_image_control_init(self, *args, **kwargs)

        ImageControlMsg.__init__ = _compat_image_control_init

        def _recording_encode(*args, **kwargs):
            nonlocal seen_first
            if not seen_first:
                seen_first = True
                first_started.set()
                release_first.wait(timeout=5.0)

            queue_lengths_seen.append(int(kwargs.get("queue_length") or 0))
            result = orig_encode(*args, **kwargs)
            fast_flags.append(bool(getattr(result, "fast_path_selected", False)))
            skip_flags.append(bool(getattr(result, "obj_detection_skipped", False)))
            return result

        bridge.encode_from_jpeg = _recording_encode

        channel = grpc.aio.insecure_channel(address)
        await channel.channel_ready()

        frames = _load_helicopter_frames(limit=10)
        source_stream = _build_mjpeg_stream(frames)

        try:
            stub = svred_pb2_grpc.OrchestratorToTransformServiceStub(channel)
            source_messages = [_forward_message(source_stream)]

            acks = [ack async for ack in stub.StreamOrchestratorToTransform(_iter_messages(source_messages))]
            assert len(acks) == 1
            assert all(ack.success for ack in acks)

            for _ in range(50):
                if first_started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert first_started.is_set()
            release_first.set()

            control_stream = stub.StreamTransformToOrchestrator(svred_pb2.TransformToOrchestratorParams())
            controls: list[svred_pb2.TransformToOrchestratorMessage] = []
            while len(controls) < len(frames):
                controls.append(await asyncio.wait_for(control_stream.read(), timeout=30.0))

            assert len(controls) == len(frames)
            assert all(len(c.control_envelope.original_transport_payload) > 0 for c in controls)

            manifest_frames: list[dict[str, object]] = []
            for index, message in enumerate(controls):
                out_path = OUTPUT_DIR / f"queue_wiring_real_semantic_{index + 1:04d}.bin"
                wrapped_payload = bytes(message.control_envelope.original_transport_payload)
                control_msg = ImageControlMsg.from_bytes(
                    wrapped_payload,
                    expected_preamble=wrapped_payload[0],
                )
                semantic_payload = control_msg.get_jpeg_bytes()
                out_path.write_bytes(semantic_payload)

                recon_jpeg = await asyncio.to_thread(
                    manager.process_payload,
                    semantic_payload,
                    manager.get_compression_level(),
                )
                recon_path = OUTPUT_DIR / f"queue_wiring_real_semantic_recon_{index + 1:04d}.jpeg"
                recon_path.write_bytes(recon_jpeg)

                manifest_frames.append(
                    {
                        "frame_index": index + 1,
                        "queue_length": queue_lengths_seen[index] if index < len(queue_lengths_seen) else None,
                        "fast_path_selected": fast_flags[index] if index < len(fast_flags) else None,
                        "obj_detection_skipped": skip_flags[index] if index < len(skip_flags) else None,
                        "semantic_payload_file": out_path.name,
                        "semantic_payload_bytes": out_path.stat().st_size,
                        "recon_jpeg_file": recon_path.name,
                        "recon_jpeg_bytes": recon_path.stat().st_size,
                    }
                )

            status = manager.performance_status()
            assert status["frames_encoded"] == len(frames)
            assert status["frames_decoded"] == len(frames)
            assert len(queue_lengths_seen) == len(frames)
            assert max(queue_lengths_seen) >= cfg.pipeline_manager.queue_backlog_threshold_3
            assert min(queue_lengths_seen) == 0
            assert any(fast_flags)
            assert any(skip_flags)

            written_payloads = sorted(OUTPUT_DIR.glob("queue_wiring_real_semantic_*.bin"))
            assert len(written_payloads) == len(frames)
            assert all(path.stat().st_size > 0 for path in written_payloads)

            recon_jpegs = sorted(OUTPUT_DIR.glob("queue_wiring_real_semantic_recon_*.jpeg"))
            assert len(recon_jpegs) == len(frames)
            assert all(path.stat().st_size > 0 for path in recon_jpegs)
            for path in recon_jpegs:
                with Image.open(path) as image:
                    image.load()
                    assert image.mode in {"RGB", "L"}

            manager_recon_images = sorted((OUTPUT_DIR / "recon_images").glob("frame_*.jpeg"))
            manager_recon_masks = sorted((OUTPUT_DIR / "recon_masks").glob("frame_*.jpeg"))
            encoder_log = OUTPUT_DIR / "log" / "encoder_log.json"
            decoder_log = OUTPUT_DIR / "log" / "decoder_log.json"
            assert len(manager_recon_images) == 0
            assert len(manager_recon_masks) == 0
            assert not encoder_log.exists()
            assert not decoder_log.exists()

            manifest = {
                "frame_count": len(frames),
                "queue_thresholds": {
                    "t1": cfg.pipeline_manager.queue_backlog_threshold_1,
                    "t2": cfg.pipeline_manager.queue_backlog_threshold_2,
                    "t3": cfg.pipeline_manager.queue_backlog_threshold_3,
                },
                "frames": manifest_frames,
            }
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            assert manifest_path.exists() and manifest_path.stat().st_size > 0
            assert len(manifest_frames) == len(frames)
            assert [item["frame_index"] for item in manifest_frames] == list(range(1, len(frames) + 1))
            assert all(isinstance(item["queue_length"], int) for item in manifest_frames)
            assert all(item["semantic_payload_bytes"] > 0 for item in manifest_frames)
            assert all(item["recon_jpeg_bytes"] > 0 for item in manifest_frames)
            assert tun.queues.outbound.qsize() == 0
        finally:
            bridge.encode_from_jpeg = orig_encode
            ImageControlMsg.__init__ = orig_image_control_init
            if original_path is not None:
                os.environ["PATH"] = original_path
            await channel.close()
            for task in tasks:
                await _cancel(task)
            await manager.close()
            await server.stop(0)

    asyncio.run(_run())







