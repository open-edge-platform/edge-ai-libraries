# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import numpy as np
import pytest

import semantic_img_comp.decoder.demux as demux_module
import semantic_img_comp.utils.postprocessing as postprocessing_module
from semantic_img_comp.decoder import runner as runner_module
from semantic_img_comp.decoder.runner import run_semantic_decoder
from semantic_img_comp.integration.semantic_codec_bridge import SemanticCodecBridge


def _make_cfg(tmp_path):
    return SimpleNamespace(
        app=SimpleNamespace(log_level="INFO"),
        io=SimpleNamespace(
            output_dir=tmp_path,
            annot_file=None,
            save_visualizations=False,
            draw_bboxes=True,
            print_runtime_logs=True,
        ),
        mux_cfg=SimpleNamespace(fmt_payload_len="!I", fmt=lambda code: code),
        img_process=SimpleNamespace(
            encoders_tag_bg={"mono-2bit": 1},
            encoders_tag_objs={"mono-2bit": 1},
            encoders_tag={"mono-2bit": 1},
            additional_crop_margin=0.0,
            paste_feather_ratio=0.5,
            paste_feather_min_px=1,
        ),
    )


def _no_connections(logger, host, port):
    """Fake accept_clients: no encoder ever connects, so the accept loop ends immediately."""
    return iter([])


def _one_connection(conn, addr=("127.0.0.1", 5555)):
    """Fake accept_clients: yield exactly one (conn, addr) pair, then stop -- mirrors a
    single encoder connecting, finishing, and the (test-only, finite) accept loop ending."""
    return lambda logger, host, port: iter([(conn, addr)])


def _make_bridge(cfg, decoder=None):
    """Build a real SemanticCodecBridge wrapping a fake decoder, since
    _handle_connection calls bridge.decode_payload (which internally demuxes,
    decompresses via the decoder, and pastes the reconstruction)."""
    fake_decoder = decoder if decoder is not None else SimpleNamespace(
        img_names={},
        decompress_background=lambda *args: None,
        decompress_objs=lambda *args: None,
    )
    return SemanticCodecBridge(cfg, decoder=fake_decoder)


def test_decoder_runner_requires_valid_output_dir():
    cfg = _make_cfg(None)
    cfg.io.output_dir = None

    with pytest.raises(ValueError, match="output_dir"):
        run_semantic_decoder(cfg, host="localhost", port=9999, bridge=_make_bridge(cfg))


def test_decoder_runner_initializes_decoder(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)

    # Mock network layer so the accept loop ends immediately with no clients.
    monkeypatch.setattr(runner_module, "accept_clients", _no_connections)

    # Should not raise
    run_semantic_decoder(cfg, bridge=_make_bridge(cfg))

    # Verify output dir created
    assert (tmp_path / "log" / "decoder_log.json").exists()
    assert (tmp_path / "recon_images").exists()


def test_decoder_runner_suppresses_stdout_when_configured(tmp_path, monkeypatch, capsys):
    cfg = _make_cfg(tmp_path)
    cfg.io.print_runtime_logs = False
    fake_conn = SimpleNamespace()

    monkeypatch.setattr(runner_module, "accept_clients", _one_connection(fake_conn))
    monkeypatch.setattr(runner_module, "recv_frame", lambda conn, mux_cfg: None)

    run_semantic_decoder(cfg, bridge=_make_bridge(cfg))

    captured = capsys.readouterr()
    assert captured.out == ""

    log_lines = (tmp_path / "log" / "decoder_log.json").read_text(encoding="utf-8").strip().splitlines()
    assert any('"event":"decoder_started"' in line for line in log_lines)
    assert any('"event":"transmission_completed"' in line for line in log_lines)
    assert any('"event":"decoder_completed"' in line for line in log_lines)


def test_decoder_runner_passes_stdout_flag_to_logger(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.io.print_runtime_logs = False
    setup_kwargs = {}

    def fake_setup_logger(**kwargs):
        setup_kwargs.update(kwargs)
        return runner_module.logging.getLogger("decoder-test")

    monkeypatch.setattr(runner_module, "setup_logger", fake_setup_logger)
    monkeypatch.setattr(runner_module, "accept_clients", _no_connections)

    run_semantic_decoder(cfg, bridge=_make_bridge(cfg))

    # log_path/enable_stdout/propagate are now derived inside setup_logger from cfg;
    # the runner only needs to forward name + cfg.
    assert setup_kwargs["cfg"] is cfg
    assert setup_kwargs["name"] == "decoder"


def test_decoder_runner_disables_json_log_file_when_configured(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.io.write_json_logs = False

    monkeypatch.setattr(runner_module, "accept_clients", _no_connections)

    run_semantic_decoder(cfg, bridge=_make_bridge(cfg))

    # setup_logger derives log_path from cfg.io.write_json_logs itself; verify no file is written.
    assert not (tmp_path / "log" / "decoder_log.json").exists()


def test_decoder_runner_handles_connection_error(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)

    def _fail_accept(logger, host, port):
        raise ConnectionError("Network unavailable")

    monkeypatch.setattr(runner_module, "accept_clients", _fail_accept)

    with pytest.raises(ConnectionError):
        run_semantic_decoder(cfg, host="localhost", port=9999, bridge=_make_bridge(cfg))


def test_decoder_runner_keeps_listening_after_a_client_disconnects(tmp_path, monkeypatch):
    """Regression test: a prior bug made the decoder accept exactly one encoder connection
    for the life of the process, then exit -- leaving the port refusing every subsequent
    connection attempt (e.g. after an encoder restart). The accept loop must keep running
    across multiple, sequential client connections."""
    cfg = _make_cfg(tmp_path)

    first_conn = SimpleNamespace()
    second_conn = SimpleNamespace()
    addrs = [("127.0.0.1", 1111), ("127.0.0.1", 2222)]

    def _two_connections(logger, host, port):
        return iter([(first_conn, addrs[0]), (second_conn, addrs[1])])

    monkeypatch.setattr(runner_module, "accept_clients", _two_connections)
    monkeypatch.setattr(runner_module, "recv_frame", lambda conn, mux_cfg: None)

    run_semantic_decoder(cfg, host="localhost", port=9999, bridge=_make_bridge(cfg))

    log_lines = (tmp_path / "log" / "decoder_log.json").read_text(encoding="utf-8").strip().splitlines()
    disconnected_events = [line for line in log_lines if '"event":"client_disconnected"' in line]
    assert len(disconnected_events) == 2
    assert '"client":"127.0.0.1:1111"' in disconnected_events[0]
    assert '"client":"127.0.0.1:2222"' in disconnected_events[1]


def test_decoder_runner_detects_malformed_payload(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    fake_conn = SimpleNamespace()

    monkeypatch.setattr(runner_module, "accept_clients", _one_connection(fake_conn))
    monkeypatch.setattr(runner_module, "recv_frame", lambda conn, mux_cfg: b"corrupted")

    # Mock demux (called internally by SemanticCodecBridge.decode_payload) to raise
    monkeypatch.setattr(
        demux_module,
        "demux_frame",
        lambda payload, mux_cfg, img_idx=None, **kwargs: (_ for _ in ()).throw(ValueError("Bad struct")),
    )

    # A malformed payload disconnects just that client; it no longer crashes the
    # whole decoder process (see test_decoder_runner_keeps_listening_after_a_client_disconnects).
    run_semantic_decoder(cfg, host="localhost", port=9999, bridge=_make_bridge(cfg))

    log_lines = (tmp_path / "log" / "decoder_log.json").read_text(encoding="utf-8").strip().splitlines()
    assert any('"event":"frame_processing_error"' in line and "decode failed" in line for line in log_lines)


def test_decoder_runner_frame_count_limit(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    fake_conn = SimpleNamespace()
    call_count = [0]

    def _recv_many(conn, mux_cfg):
        call_count[0] += 1
        # +1 call to account for the one-time client_id handshake read in the accept
        # loop before _handle_connection's per-frame loop even starts.
        if call_count[0] <= 1_000_002:
            return b"x"
        return None

    def _valid_demux(payload, mux_cfg, img_idx=None, **kwargs):
        # Return minimal valid demuxed data
        return SimpleNamespace(
            img_idx=img_idx,
            org_img_size=(1, 1),
            bg=SimpleNamespace(
                encoder_index=1,
                encoded_data=b"x",
                scaled_size=(1, 1),
                mask=None,
                recon_pil=None,
            ),
            crops=[],
        )

    monkeypatch.setattr(runner_module, "accept_clients", _one_connection(fake_conn))
    monkeypatch.setattr(runner_module, "recv_frame", _recv_many)
    monkeypatch.setattr(demux_module, "demux_frame", _valid_demux)
    monkeypatch.setattr(postprocessing_module, "paste_with_margin", lambda *args, **kwargs: SimpleNamespace(
        size=(1, 1),
    ))

    with pytest.raises(RuntimeError, match="Abnormal frame count"):
        run_semantic_decoder(cfg, host="localhost", port=9999, bridge=_make_bridge(cfg))


def test_decoder_runner_saves_visualizations_under_recon_subdirectories(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.io.save_visualizations = True
    fake_conn = SimpleNamespace()
    saved = {}

    monkeypatch.setattr(runner_module, "accept_clients", _one_connection(fake_conn))

    payloads = iter([b"encoder-1", b"frame", None])
    monkeypatch.setattr(runner_module, "recv_frame", lambda conn, mux_cfg: next(payloads))

    monkeypatch.setattr(
        demux_module,
        "demux_frame",
        lambda payload, mux_cfg, img_idx=None, **kwargs: SimpleNamespace(
            img_idx=img_idx,
            org_img_size=(4, 3),
            bg=SimpleNamespace(
                encoder_index=1,
                encoded_data=b"bg",
                scaled_size=(4, 3),
                mask=np.ones((2, 2), dtype=np.uint8),
                recon_pil=None,
            ),
            crops=[],
        ),
    )
    monkeypatch.setattr(postprocessing_module, "paste_with_margin", lambda *args, **kwargs: SimpleNamespace(size=(4, 3)))
    monkeypatch.setattr(runner_module, "save_composite_img", lambda img, path: saved.setdefault("image", path))

    run_semantic_decoder(cfg, host="localhost", port=9999, bridge=_make_bridge(cfg))

    assert saved["image"] == tmp_path / "recon_images" / "encoder-1_1.jpeg"


def test_decoder_runner_closes_connection_on_shutdown(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)

    class _Conn:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    fake_conn = _Conn()

    monkeypatch.setattr(runner_module, "accept_clients", _one_connection(fake_conn))
    monkeypatch.setattr(runner_module, "recv_frame", lambda conn, mux_cfg: None)

    run_semantic_decoder(cfg, host="localhost", port=9999, bridge=_make_bridge(cfg))

    assert fake_conn.closed is True


def test_decoder_runner_passes_feather_tuning_to_postprocessing(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.img_process.additional_crop_margin = 12.0
    cfg.img_process.paste_feather_ratio = 0.25
    cfg.img_process.paste_feather_min_px = 3

    fake_conn = SimpleNamespace(closed=False)
    payloads = iter([b"encoder-1", b"frame", None])
    call_kwargs = {}

    monkeypatch.setattr(runner_module, "accept_clients", _one_connection(fake_conn))
    monkeypatch.setattr(runner_module, "recv_frame", lambda conn, mux_cfg: next(payloads))
    monkeypatch.setattr(
        demux_module,
        "demux_frame",
        lambda payload, mux_cfg, img_idx=None, **kwargs: SimpleNamespace(
            img_idx=img_idx,
            org_img_size=(4, 3),
            bg=SimpleNamespace(
                encoder_index=1,
                encoded_data=b"bg",
                scaled_size=(4, 3),
                mask=None,
                recon_pil=None,
            ),
            crops=[],
        ),
    )

    def _fake_paste_with_margin(img_dec_data, margin_percent, **kwargs):
        call_kwargs["margin_percent"] = margin_percent
        call_kwargs.update(kwargs)
        return SimpleNamespace(size=(4, 3))

    monkeypatch.setattr(postprocessing_module, "paste_with_margin", _fake_paste_with_margin)

    run_semantic_decoder(cfg, host="localhost", port=9999, bridge=_make_bridge(cfg))

    assert call_kwargs["margin_percent"] == 12.0
    assert call_kwargs["feather_ratio"] == 0.25
    assert call_kwargs["feather_min_px"] == 3


def test_decoder_runner_draws_boxes_on_reconstruction_before_saving(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.io.save_visualizations = True
    cfg.io.draw_bboxes = True
    fake_conn = SimpleNamespace()
    payloads = iter([b"encoder-1", b"frame", None])
    calls = {}

    class _FakeImage:
        def __init__(self):
            self.size = (4, 3)

        def copy(self):
            return self

    crops = [SimpleNamespace(bbox=(0, 0, 1, 1), category_id=1, det_conf=0.8)]

    monkeypatch.setattr(runner_module, "accept_clients", _one_connection(fake_conn))
    monkeypatch.setattr(runner_module, "recv_frame", lambda conn, mux_cfg: next(payloads))
    monkeypatch.setattr(
        demux_module,
        "demux_frame",
        lambda payload, mux_cfg, img_idx=None, **kwargs: SimpleNamespace(
            img_idx=img_idx,
            org_img_size=(4, 3),
            bg=SimpleNamespace(
                encoder_index=1,
                encoded_data=b"bg",
                scaled_size=(4, 3),
                mask=None,
                recon_pil=None,
            ),
            crops=crops,
        ),
    )
    monkeypatch.setattr(postprocessing_module, "paste_with_margin", lambda *args, **kwargs: _FakeImage())

    def _fake_draw_boxes_on_pil(img, in_crops, names=None, box_thickness=3, show_labels=True):
        calls["draw_img"] = img
        calls["draw_crops"] = in_crops
        calls["show_labels"] = show_labels
        return img

    monkeypatch.setattr(runner_module, "draw_boxes_on_pil", _fake_draw_boxes_on_pil)
    monkeypatch.setattr(runner_module, "save_composite_img", lambda img, path: calls.setdefault("saved_img", img))

    run_semantic_decoder(cfg, host="localhost", port=9999, bridge=_make_bridge(cfg))

    assert calls["draw_crops"] == crops
    assert calls["show_labels"] is False
    assert calls["saved_img"] is calls["draw_img"]


def test_decoder_runner_skips_draw_boxes_when_draw_bboxes_false(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.io.save_visualizations = True
    cfg.io.draw_bboxes = False
    fake_conn = SimpleNamespace()
    payloads = iter([b"encoder-1", b"frame", None])
    calls = {}

    class _FakeImage:
        def __init__(self):
            self.size = (4, 3)

        def copy(self):
            return self

    crops = [SimpleNamespace(bbox=(0, 0, 1, 1), category_id=1, det_conf=0.8)]

    monkeypatch.setattr(runner_module, "accept_clients", _one_connection(fake_conn))
    monkeypatch.setattr(runner_module, "recv_frame", lambda conn, mux_cfg: next(payloads))
    monkeypatch.setattr(
        demux_module,
        "demux_frame",
        lambda payload, mux_cfg, img_idx=None, **kwargs: SimpleNamespace(
            img_idx=img_idx,
            org_img_size=(4, 3),
            bg=SimpleNamespace(
                encoder_index=1,
                encoded_data=b"bg",
                scaled_size=(4, 3),
                mask=None,
                recon_pil=None,
            ),
            crops=crops,
        ),
    )

    original_img = _FakeImage()
    monkeypatch.setattr(postprocessing_module, "paste_with_margin", lambda *args, **kwargs: original_img)
    monkeypatch.setattr(
        runner_module,
        "draw_boxes_on_pil",
        lambda *args, **kwargs: calls.setdefault("draw_called", True),
    )
    monkeypatch.setattr(runner_module, "save_composite_img", lambda img, path: calls.setdefault("saved_img", img))

    run_semantic_decoder(cfg, host="localhost", port=9999, bridge=_make_bridge(cfg))

    assert "draw_called" not in calls, "draw_boxes_on_pil must not be called when draw_bboxes=False"
    assert calls["saved_img"] is original_img



