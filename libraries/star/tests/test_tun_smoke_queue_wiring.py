# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Queue wiring smoke test for TUNInterface -> SemanticImageManager pipeline decisions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

grpc = pytest.importorskip("grpc")
pytest.importorskip("PIL")

from PIL import Image

from semantic_img_comp.encoder.pipeline_manager import EncoderPipelineManager, PipelineContext


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = WORKSPACE_ROOT / "semantic-img-comp" / "tests" / "fixtures"
INPUT_IMAGE_DIR = FIXTURES_DIR / "sample_images"
OUTPUT_DIR = FIXTURES_DIR / "output"


def _load_frames(limit: int = 12) -> list[bytes]:
    candidates = sorted(INPUT_IMAGE_DIR.glob("*.jpg"))
    if not candidates:
        candidates = sorted(INPUT_IMAGE_DIR.glob("*.jpeg"))
    if candidates:
        payloads: list[bytes] = []
        for index in range(limit):
            payloads.append(candidates[index % len(candidates)].read_bytes())
        return payloads

    generated: list[bytes] = []
    for index in range(limit):
        image = Image.new("RGB", (24, 18), color=(40 + index * 8, 60, 120))
        output = BytesIO()
        image.save(output, format="JPEG")
        generated.append(output.getvalue())
    return generated


def _build_mjpeg_stream(frames: list[bytes]) -> bytes:
    header = b"HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n"
    parts = [header]
    for jpeg_bytes in frames:
        parts.append(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n")
    return b"".join(parts)


def _forward_message(payload: bytes) -> svred_pb2.OrchestratorToTransformMessage:
    message = svred_pb2.OrchestratorToTransformMessage()
    message.payload = payload
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


def _build_cfg_for_queue_ratchet() -> SimpleNamespace:
    return SimpleNamespace(
        enc=SimpleNamespace(
            compression_rate=100.0,
            max_iter_bg=8,
            max_iter_obj=3,
        ),
        model=SimpleNamespace(
            tile_size=None,
            tile_overlap=None,
        ),
        pipeline_manager=SimpleNamespace(
            queue_backlog_threshold_1=1,
            queue_backlog_threshold_2=2,
            queue_backlog_threshold_3=3,
            fast_full_hysteresis_exit=1.5,
            skip_obj_hysteresis_exit=2.5,
            adaptive_compression_rate_warmup_frames=10,
            adaptive_compression_rate_max=300.0,
            adaptive_compression_rate_boost_factor=1.5,
            large_dim_tile_threshold_px=1280,
        ),
    )


@dataclass
class _FakeImgData:
    img_idx: int
    crops: list[object]


@dataclass
class _FakeEncodeResult:
    payload: bytes
    img_data: _FakeImgData
    timing_ms: dict[str, float]
    size_log: dict[str, int]


class _FakeSemanticBridge:
    """Records queue length wiring and runs real queue-tier ratchet logic."""

    def __init__(self, cfg: SimpleNamespace) -> None:
        self.pipeline_mgr = EncoderPipelineManager(cfg)
        self.queue_lengths: list[int] = []
        self.pipeline_contexts: list[PipelineContext] = []
        self._release_first_encode = threading.Event()
        self._first_encode_started = threading.Event()
        self._first_encode_seen = False

    def encode_from_jpeg(self, jpeg_bytes: bytes, *, img_id: int | None = None, queue_length: int | None = None, compression_level: int = 1) -> _FakeEncodeResult:
        del jpeg_bytes
        if not self._first_encode_seen:
            self._first_encode_seen = True
            self._first_encode_started.set()
            self._release_first_encode.wait(timeout=5.0)

        queue_size = int(queue_length or 0)
        self.queue_lengths.append(queue_size)

        ctx = self.pipeline_mgr.decide_pipeline(
            image_size_bytes=50_000,
            queue_size=queue_size,
            aggregated_comp_rate=None,
            processed_frames_count=0,
            compression_level=compression_level,
        )
        self.pipeline_contexts.append(ctx)

        encoded = f"enc:{img_id}:{queue_size}".encode("ascii")
        return _FakeEncodeResult(
            payload=encoded,
            img_data=_FakeImgData(img_idx=int(img_id or 0), crops=[]),
            timing_ms={"yolo": 0.01, "obj_comp": 0.01, "bg_comp": 0.01, "enc_total": 0.05},
            size_log={"payload": len(encoded)},
        )


async def _start_semantic_tun_server(
    *,
    service_name: str,
    transform_name: str,
    cfg: SimpleNamespace,
) -> tuple[SemanticImageManager, _FakeSemanticBridge, TUNInterface, grpc.aio.Server, str, list[asyncio.Task[None]]]:
    manager = SemanticImageManager(
        cfg=cfg,
        service_name=service_name,
        transform_name=transform_name,
        output_dir=None,
    )
    manager.set_compression_level(1)
    fake_bridge = _FakeSemanticBridge(cfg)
    manager._bridge = fake_bridge

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
    return manager, fake_bridge, tun, server, f"127.0.0.1:{port}", tasks


def test_tun_smoke_queue_length_wiring_ratchets_pipeline_context() -> None:
    async def _run() -> None:
        frames = _load_frames(limit=12)
        source_stream = _build_mjpeg_stream(frames)
        source_messages = [_forward_message(source_stream)]

        cfg = _build_cfg_for_queue_ratchet()
        manager, fake_bridge, tun, server, address, tasks = await _start_semantic_tun_server(
            service_name="image-queue-wiring-test",
            transform_name="image-queue-wiring",
            cfg=cfg,
        )

        channel = grpc.aio.insecure_channel(address)
        await channel.channel_ready()
        orig_image_control_init = ImageControlMsg.__init__

        def _compat_image_control_init(self, *args, compression_level=None, **kwargs):
            del compression_level
            return orig_image_control_init(self, *args, **kwargs)

        ImageControlMsg.__init__ = _compat_image_control_init

        try:
            stub = svred_pb2_grpc.OrchestratorToTransformServiceStub(channel)

            acks = [ack async for ack in stub.StreamOrchestratorToTransform(_iter_messages(source_messages))]
            assert len(acks) == len(source_messages)
            assert all(ack.success for ack in acks)

            # Ensure encode worker is blocked once so the queue can build backlog.
            for _ in range(50):
                if fake_bridge._first_encode_started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert fake_bridge._first_encode_started.is_set()
            fake_bridge._release_first_encode.set()

            control_stream = stub.StreamTransformToOrchestrator(svred_pb2.TransformToOrchestratorParams())
            controls: list[svred_pb2.TransformToOrchestratorMessage] = []
            while len(controls) < len(frames):
                controls.append(await asyncio.wait_for(control_stream.read(), timeout=5.0))

            assert len(controls) == len(frames)
            assert manager.performance_status()["frames_encoded"] == len(frames)

            # Verify queue length is wired through manager -> bridge and reaches skip tier.
            assert len(fake_bridge.queue_lengths) == len(frames)
            assert max(fake_bridge.queue_lengths) >= cfg.pipeline_manager.queue_backlog_threshold_3
            assert min(fake_bridge.queue_lengths) == 0

            contexts = fake_bridge.pipeline_contexts
            assert any((not c.skip_obj_detection and not c.use_fast_path_bg and not c.use_fast_path_obj) for c in contexts)
            assert any((not c.skip_obj_detection and c.use_fast_path_bg and not c.use_fast_path_obj) for c in contexts)
            assert any((not c.skip_obj_detection and c.use_fast_path_bg and c.use_fast_path_obj) for c in contexts)
            assert any((c.skip_obj_detection and c.use_fast_path_bg) for c in contexts)

            # Sanity-check wiring at TUN boundary too: all generated controls are flushed.
            assert tun.queues.outbound.qsize() == 0
        finally:
            ImageControlMsg.__init__ = orig_image_control_init
            await channel.close()
            for task in tasks:
                await _cancel(task)
            await manager.close()
            await server.stop(0)

    asyncio.run(_run())

