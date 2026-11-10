# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Fast in-process smoke tests for the encoder/decoder REST services -- no docker,
no real sockets, no YOLO weights required. These exercise the new multi-client
stream/pub-sub/polling behavior directly; tests/docker-compose.yml + the sample
clients are the slower, fully-networked end-to-end check.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from semantic_img_comp.decoder.decoder import Decoder  # noqa: E402
from semantic_img_comp.decoder.service import DecoderService, create_app as create_decoder_app  # noqa: E402
from semantic_img_comp.encoder.encoder import Encoder  # noqa: E402
from semantic_img_comp.encoder.service import EncoderService, create_app as create_encoder_app  # noqa: E402
from semantic_img_comp.integration.semantic_codec_bridge import SemanticCodecBridge  # noqa: E402
from semantic_img_comp.utils.config import load_config  # noqa: E402


def _make_jpeg_bytes(color=(10, 20, 30), size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def cfg():
    cfg = load_config(str(REPO_ROOT / "configs" / "default.yaml"))
    # Keep the smoke test fast and offline: no YOLO weights needed to encode.
    cfg.model.skip_obj_detection = True
    return cfg


@pytest.fixture()
def decoder_client(cfg, tmp_path):
    bridge = SemanticCodecBridge(cfg, decoder=Decoder(cfg))
    service = DecoderService(cfg, buffer_size=50, output_dir=tmp_path, save_visualizations=False, bridge=bridge)
    app = create_decoder_app(service)
    with TestClient(app) as client:
        yield client


def test_stream_create_is_idempotent(decoder_client):
    r1 = decoder_client.put("/v1/streams/s1")
    r2 = decoder_client.put("/v1/streams/s1")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert decoder_client.get("/v1/streams/s1").json()["stream_id"] == "s1"
    assert decoder_client.get("/v1/streams/unknown").status_code == 404


def test_decoder_round_trip(cfg, decoder_client):
    """Encode locally, POST the payload straight to the decoder service, poll it back out."""
    bridge = SemanticCodecBridge(cfg)
    jpeg_bytes = _make_jpeg_bytes()
    encode_result = bridge.encode_from_jpeg(jpeg_bytes, img_id=1).result()

    decoder_client.put("/v1/streams/roundtrip")
    post_resp = decoder_client.post("/v1/streams/roundtrip/payloads", content=encode_result.payload)
    assert post_resp.status_code == 202
    frame_seq = post_resp.json()["frame_seq"]

    get_resp = decoder_client.get("/v1/streams/roundtrip/frames/next", params={"consumer_id": "c1", "wait_ms": 0})
    assert get_resp.status_code == 200
    assert get_resp.headers["X-Frame-Seq"] == str(frame_seq)
    decoded_img = Image.open(io.BytesIO(get_resp.content))
    assert decoded_img.size == (64, 48)

    # Nothing new for this consumer until another frame arrives.
    empty_resp = decoder_client.get("/v1/streams/roundtrip/frames/next", params={"consumer_id": "c1", "wait_ms": 0})
    assert empty_resp.status_code == 204


def test_multiple_consumers_each_get_every_frame(cfg, decoder_client):
    """Two independent receivers against the same stream: pub/sub fan-out, not a partitioned queue."""
    bridge = SemanticCodecBridge(cfg)
    decoder_client.put("/v1/streams/fanout")

    for i in range(1, 4):
        payload = bridge.encode_from_jpeg(_make_jpeg_bytes(color=(i, i, i)), img_id=i).result().payload
        decoder_client.post("/v1/streams/fanout/payloads", content=payload)

    for consumer_id in ("reader-a", "reader-b"):
        seqs = []
        while True:
            resp = decoder_client.get("/v1/streams/fanout/frames/next", params={"consumer_id": consumer_id, "wait_ms": 0})
            if resp.status_code == 204:
                break
            seqs.append(int(resp.headers["X-Frame-Seq"]))
        assert seqs == [1, 2, 3]


def test_get_frame_by_seq_reads_from_disk(cfg, tmp_path):
    """/frames/{frame_seq} is served from the saved visualization file, not the in-memory buffer."""
    decoder_bridge = SemanticCodecBridge(cfg, decoder=Decoder(cfg))
    service = DecoderService(cfg, buffer_size=50, output_dir=tmp_path, save_visualizations=True, bridge=decoder_bridge)
    app = create_decoder_app(service)
    bridge = SemanticCodecBridge(cfg)

    with TestClient(app) as client:
        client.put("/v1/streams/disk")
        payload = bridge.encode_from_jpeg(_make_jpeg_bytes(), img_id=1).result().payload
        post_resp = client.post("/v1/streams/disk/payloads", content=payload)
        frame_seq = post_resp.json()["frame_seq"]

        assert (tmp_path / "recon_images" / f"disk_{frame_seq}.jpeg").is_file()

        get_resp = client.get(f"/v1/streams/disk/frames/{frame_seq}")
        assert get_resp.status_code == 200
        assert get_resp.headers["X-Frame-Seq"] == str(frame_seq)
        Image.open(io.BytesIO(get_resp.content)).load()

        assert client.get(f"/v1/streams/disk/frames/{frame_seq + 1}").status_code == 404


def test_get_frame_by_seq_404_when_visualizations_not_saved(decoder_client):
    """save_visualizations defaults to False in the shared decoder_client fixture, so no files exist on disk."""
    decoder_client.put("/v1/streams/no-disk")
    assert decoder_client.get("/v1/streams/no-disk/frames/1").status_code == 404


def test_encoder_forwards_payload_to_decoder(cfg):
    """Encoder accepts the frame without blocking; its forwarder thread posts the result
    to a mocked decoder HTTP endpoint (no real decoder process needed)."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body_len"] = len(request.content)
        return httpx.Response(202, json={"frame_seq": 7, "img_idx": 1})

    transport = httpx.MockTransport(handler)
    bridge = SemanticCodecBridge(cfg, encoder=Encoder(cfg))
    service = EncoderService(cfg, decoder_url="http://decoder.local:8000", http_transport=transport, bridge=bridge)
    app = create_encoder_app(service)

    with TestClient(app) as client:
        client.put("/v1/streams/s1")
        resp = client.post(
            "/v1/streams/s1/frames",
            params={"img_id": 1},
            content=_make_jpeg_bytes(),
            headers={"Content-Type": "image/jpeg", "X-Client-Sent-At": "123.456"},
        )

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "accepted"

        # Closing the stream joins its forwarder thread, guaranteeing the async
        # encode+forward above has completed before asserting on it below.
        assert client.delete("/v1/streams/s1").status_code == 204

    assert "/v1/streams/s1/payloads" in captured["url"]
    assert captured["headers"].get("x-client-sent-at") == "123.456"
    assert captured["body_len"] > 0
