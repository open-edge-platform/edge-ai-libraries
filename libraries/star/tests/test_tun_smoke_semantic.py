# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import shutil
import os
from pathlib import Path

import pytest

grpc = pytest.importorskip("grpc")
pytest.importorskip("PIL")

from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
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


def _load_helicopter_frames(limit: int = 3) -> list[tuple[str, bytes]]:
    candidates = sorted(INPUT_IMAGE_DIR.glob("*.jpg"))
    if not candidates:
        candidates = sorted(INPUT_IMAGE_DIR.glob("*.jpeg"))
    if not candidates:
        candidates = sorted(INPUT_IMAGE_DIR.glob("*.png"))
    selected = candidates[:limit]
    if not selected:
        pytest.fail(f"missing helicopter fixture images in {INPUT_IMAGE_DIR}")
    return [(path.name, path.read_bytes()) for path in selected]


def _build_mjpeg_stream(frames: list[tuple[str, bytes]]) -> bytes:
    header = b"HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n"
    parts = [header]
    for _, jpeg_bytes in frames:
        parts.append(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n")
    return b"".join(parts)


def _chunk_bytes(payload: bytes, chunk_size: int = 4096) -> list[bytes]:
    return [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)] or [b""]


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


async def _read_or_timeout(
    stream: object,
    *,
    timeout_sec: float,
    stage: str,
):
    try:
        return await asyncio.wait_for(stream.read(), timeout=timeout_sec)
    except TimeoutError as exc:
        raise AssertionError(f"timed out after {timeout_sec:.1f}s while waiting for {stage}") from exc


def _extract_single_jpeg(payload: bytes) -> bytes:
    buffer = bytearray(payload)
    frames = SimpleImageManager._extract_complete_frames(buffer)
    if len(frames) != 1:
        raise AssertionError(f"expected exactly one JPEG frame, got {len(frames)}")
    return frames[0][1]


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
    cfg: object | None = None,
    control_message_cls: type[ImageControlMsg] = ImageControlMsg,
) -> tuple[SemanticImageManager, TUNInterface, grpc.aio.Server, str, list[asyncio.Task[None]]]:
    """Start one queue-backed TUNInterface gRPC server for smoke testing."""

    assert cfg is not None
    manager = SemanticImageManager(
        cfg=cfg,
        service_name=service_name,
        transform_name=transform_name,
        output_dir=OUTPUT_DIR,
    )
    manager.set_compression_level(1)
    await asyncio.to_thread(manager.warmup)
    tun = TUNInterface(
        service_name,
        transform_name,
        svred_module=manager,
        control_message_cls=control_message_cls,
        loop_interval=0.01,
    )
    server = grpc.aio.server()
    tun.register(server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    if port == 0:
        raise RuntimeError(f"failed to bind TCP socket for {service_name}")
    address = f"127.0.0.1:{port}"
    tasks = [asyncio.create_task(coro) for coro in tun.create_tasks()]
    return manager, tun, server, address, tasks


@pytest.mark.integration
def test_tun_interface_smoke_roundtrip_writes_rehydrated_helicopter_frames() -> None:
    from semantic_img_comp.utils.config import load_config

    async def _run() -> None:
        original_path: str | None = None
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for path in OUTPUT_DIR.glob("helicopter_smoke_*.jpeg"):
            path.unlink()
        for path in (OUTPUT_DIR / "recon_images", OUTPUT_DIR / "recon_masks", OUTPUT_DIR / "log"):
            if path.exists():
                shutil.rmtree(path)

        frames = _load_helicopter_frames(limit=3)
        source_stream = _build_mjpeg_stream(frames)
        source_chunks = [_forward_message(chunk) for chunk in _chunk_bytes(source_stream, chunk_size=8192)]

        config_path = Path(__file__).resolve().parents[2] / "semantic-img-comp" / "configs" / "default.yaml"
        if not config_path.exists():
            pytest.skip(f"missing semantic config: {config_path}")
        cfg = load_config(str(config_path))

        # Resolve workstation-local model path if the semantic pipeline config
        # points at an in-container default path.
        configured_model_path = Path(cfg.model.enc_yolo_model_path)
        if not configured_model_path.exists():
            env_model_path = os.getenv("IMAGE_MODEL_PATH")
            local_model_candidates = [
                Path(__file__).resolve().parents[2] / "semantic-img-comp" / "models" / "obj_det_models" / "yolov8m_int8_openvino_model",
                Path(__file__).resolve().parents[2] / "semantic-img-comp" / "models" / "obj_det_models" / "yolov8m.pt",
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
            pytest.skip("missing AVIF tools; expected avifenc/avifdec on PATH or under semantic-img-comp/tools")

        if avif_tools_dir is not None:
            original_path = os.environ.get("PATH")
            os.environ["PATH"] = avif_search_path

        forward_manager, forward_tun, forward_server, forward_addr, forward_tasks = await _start_tun_server(
            service_name="image-forward-test",
            transform_name="image-forward",
            cfg=cfg,
        )
        inverse_manager, inverse_tun, inverse_server, inverse_addr, inverse_tasks = await _start_tun_server(
            service_name="image-inverse-test",
            transform_name="image-inverse",
            cfg=cfg,
        )
        assert isinstance(forward_manager, SemanticImageManager)
        assert isinstance(inverse_manager, SemanticImageManager)

        forward_channel = grpc.aio.insecure_channel(forward_addr)
        inverse_channel = grpc.aio.insecure_channel(inverse_addr)
        await forward_channel.channel_ready()
        await inverse_channel.channel_ready()
        orig_image_control_init = ImageControlMsg.__init__
        orig_get_compression_level = getattr(ImageControlMsg, "get_compression_level", None)

        def _compat_image_control_init(self, *args, compression_level=None, **kwargs):
            del compression_level
            return orig_image_control_init(self, *args, **kwargs)

        def _compat_get_compression_level(self) -> int:
            # Current ImageControlMsg payload format does not expose compression level.
            # This smoke test uses level 1 for forward and inverse paths.
            return 1

        ImageControlMsg.__init__ = _compat_image_control_init
        ImageControlMsg.get_compression_level = _compat_get_compression_level

        try:
            forward_stub = svred_pb2_grpc.OrchestratorToTransformServiceStub(forward_channel)
            inverse_stub = svred_pb2_grpc.OrchestratorToTransformServiceStub(inverse_channel)

            forward_acks = [
                ack
                async for ack in forward_stub.StreamOrchestratorToTransform(_iter_messages(source_chunks))
            ]
            assert len(forward_acks) == len(source_chunks)
            assert all(ack.success for ack in forward_acks)

            control_stream = forward_stub.StreamTransformToOrchestrator(
                svred_pb2.TransformToOrchestratorParams()
            )
            control_messages: list[svred_pb2.TransformToOrchestratorMessage] = []
            while len(control_messages) < len(frames):
                control_messages.append(
                    await _read_or_timeout(
                        control_stream,
                        timeout_sec=45.0,
                        stage="forward control message",
                    )
                )

            inverse_inputs: list[svred_pb2.OrchestratorToTransformMessage] = []
            for control in control_messages:
                msg = svred_pb2.OrchestratorToTransformMessage()
                msg.trace_context.update(control.trace_context)
                msg.header.CopyFrom(control.header)
                msg.metadata.CopyFrom(control.metadata)
                msg.payload = control.control_envelope.original_transport_payload
                inverse_inputs.append(msg)

            inverse_acks = [
                ack
                async for ack in inverse_stub.StreamOrchestratorToTransform(_iter_messages(inverse_inputs))
            ]
            assert len(inverse_acks) == len(frames)
            assert all(ack.success for ack in inverse_acks)

            output_stream = inverse_stub.StreamTransformToOrchestrator(
                svred_pb2.TransformToOrchestratorParams()
            )
            written_paths: list[Path] = []
            for index in range(len(frames)):
                message = await _read_or_timeout(
                    output_stream,
                    timeout_sec=45.0,
                    stage="inverse output packet",
                )
                jpeg_bytes = _extract_single_jpeg(message.ip_payload)
                out_path = OUTPUT_DIR / f"helicopter_smoke_{index + 1:04d}.jpeg"
                out_path.write_bytes(jpeg_bytes)
                written_paths.append(out_path)

            assert forward_manager.performance_status()["last_encode"]["timing_ms"]["yolo"] > 0

            recon_images = sorted((OUTPUT_DIR / "recon_images").glob("*.jpeg"))
            recon_masks = sorted((OUTPUT_DIR / "recon_masks").glob("*.jpeg"))
            enc_log = OUTPUT_DIR / "log" / "enc_log.json"
            dec_log = OUTPUT_DIR / "log" / "dec_log.json"

            assert len(written_paths) == len(frames)
            for path in written_paths:
                assert path.exists()
                with Image.open(path) as image:
                    image.load()
                    assert image.mode in {"RGB", "L"}

            assert len(recon_images) == 0
            assert len(recon_masks) == len(frames)
            # Encoder metadata logging is best-effort; if the file exists, it must be non-empty.
            if enc_log.exists():
                assert enc_log.stat().st_size > 0
            assert dec_log.exists() and dec_log.stat().st_size > 0

            assert forward_tun.queues.outbound.qsize() == 0
            assert inverse_tun.queues.outbound.qsize() == 0
        finally:
            ImageControlMsg.__init__ = orig_image_control_init
            if orig_get_compression_level is None:
                delattr(ImageControlMsg, "get_compression_level")
            else:
                ImageControlMsg.get_compression_level = orig_get_compression_level
            if original_path is not None:
                os.environ["PATH"] = original_path
            await forward_channel.close()
            await inverse_channel.close()
            for task in forward_tasks + inverse_tasks:
                await _cancel(task)
            await forward_manager.close()
            await inverse_manager.close()
            await forward_server.stop(0)
            await inverse_server.stop(0)

    asyncio.run(_run())
