# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

import pytest
from PIL import Image

from semantic_img_comp.core.background import BgData
from semantic_img_comp.decoder.decoder import Decoder
from semantic_img_comp.integration import semantic_codec_bridge
from semantic_img_comp.integration.semantic_codec_bridge import SemanticCodecBridge


class _FakeEncoder:
    def __init__(self):
        self.calls = []

    def extract_objs(self, pil_img):
        self.calls.append("extract_objs")
        return []

    def set_tar_objs_bytes(self, org_jpeg_bytes: int, num_objs: int = 0):
        self.calls.append("set_tar_objs_bytes")
        return 12, 24

    def compress_objs(self, crops, tar_objs_bytes: int, **kwargs):
        self.calls.append("compress_objs")
        return crops

    def compress_background(self, pil_img, tar_enc_data_bytes: int, crops, **kwargs):
        self.calls.append("compress_background")
        return BgData(pil=pil_img, encoded_data=b"bg", scaled_size=pil_img.size, encoder_index=1), 24

    def encode_payload(self, img_data):
        self.calls.append("encode_payload")
        return b"payload", {"header": 1, "background": 2, "objects": 0, "metadata": 3}


class _FakeDecoder:
    def __init__(self):
        self.bg_calls = 0
        self.obj_calls = 0

    def decompress_background(self, bg, org_img_size, crops=None):
        self.bg_calls += 1

    def decompress_objs(self, crops):
        self.obj_calls += 1


class _FakeFailingEncoder(_FakeEncoder):
    def compress_background(self, pil_img, tar_enc_data_bytes: int, crops, **kwargs):
        raise RuntimeError("bridge-bg-failure")


class _RateRecordingEncoder(_FakeEncoder):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.seen_rates = []
        self.bg_seen_rates = []

    def set_tar_objs_bytes(self, org_jpeg_bytes: int, num_objs: int = 0):
        self.seen_rates.append(float(self.cfg.enc.compression_rate))
        return super().set_tar_objs_bytes(org_jpeg_bytes=org_jpeg_bytes, num_objs=num_objs)

    def compress_background(self, pil_img, tar_enc_data_bytes: int, crops, **kwargs):
        self.bg_seen_rates.append(float(self.cfg.enc.compression_rate))
        return super().compress_background(pil_img, tar_enc_data_bytes, crops, **kwargs)


class _SkipObjBgTrackingEncoder(_FakeEncoder):
    def __init__(self):
        super().__init__()
        self.skip_obj_detection = True
        self.bg_fast_flags = []

    def extract_objs(self, pil_img):
        raise AssertionError("extract_objs should not be called when skip_obj_detection=True")

    def compress_objs(self, crops, tar_objs_bytes: int, **kwargs):
        raise AssertionError("compress_objs should not be called when skip_obj_detection=True")

    def compress_background(self, pil_img, tar_enc_data_bytes: int, crops, **kwargs):
        self.bg_fast_flags.append(bool(kwargs.get("use_fast_path", False)))
        return super().compress_background(pil_img, tar_enc_data_bytes, crops, **kwargs)


def _cfg():
    return SimpleNamespace(
        enc=SimpleNamespace(compression_rate=100.0, max_iter_bg=1, max_iter_obj=1),
        pipeline_manager=SimpleNamespace(
            queue_backlog_threshold_1=5,
            queue_backlog_threshold_2=10,
            queue_backlog_threshold_3=15,
            adaptive_compression_rate_warmup_frames=10,
            adaptive_compression_rate_max=300.0,
            large_dim_tile_threshold_px=1280,
        ),
        dec=SimpleNamespace(avif_timeout_sec=120, smooth_sigma=0.0, bg_max_level=150),
        io=SimpleNamespace(annot_file=None),
        mux_cfg=SimpleNamespace(),
        img_process=SimpleNamespace(
            encoders_tag_bg_level_1={"mono-2bit": 1},
            encoders_tag_objs_level_1={"mono-4bit": 2},
            active_encoders_tag_bg=None,
            active_encoders_tag_objs=None,
            encoders_tag={"mono-2bit": 1, "mono-4bit": 2},
            additional_crop_margin=2.0,
            paste_feather_ratio=0.4,
            paste_feather_min_px=2,
        ),
    )


def test_encode_from_jpeg_applies_pipeline_decision_and_restores(monkeypatch):
    cfg = _cfg()
    encoder = _FakeEncoder()
    bridge = SemanticCodecBridge(cfg=cfg, encoder=encoder, decoder=_FakeDecoder())

    class _TrackingPipelineManager:
        apply_calls = 0
        restore_calls = 0

        def __init__(self, _cfg):
            self.cfg = _cfg

        def decide_pipeline(
            self,
            image_size_bytes: int,
            queue_size: int,
            aggregated_comp_rate: float | None = None,
            processed_frames_count: int | None = None,
            compression_level: int = 1,
        ):
            return SimpleNamespace(skip_obj_detection=True, use_fast_path=True)

        def apply_pipeline_config(self, context, *, img_size=None):
            type(self).apply_calls += 1

        def restore_config(self):
            type(self).restore_calls += 1

    monkeypatch.setattr(semantic_codec_bridge, "EncoderPipelineManager", _TrackingPipelineManager)

    img = Image.new("RGB", (8, 5), color="white")
    jpeg_bytes = bridge._save_jpeg_from_image(img)
    result = bridge.encode_from_jpeg(jpeg_bytes, img_id=1, queue_length=10).result()

    assert result.fast_path_selected is True
    assert result.obj_detection_skipped is True
    assert "extract_objs" not in encoder.calls
    assert "compress_objs" not in encoder.calls
    assert _TrackingPipelineManager.apply_calls == 1
    assert _TrackingPipelineManager.restore_calls == 1


def test_encode_from_jpeg_restores_pipeline_config_on_failure(monkeypatch):
    cfg = _cfg()
    bridge = SemanticCodecBridge(cfg=cfg, encoder=_FakeFailingEncoder(), decoder=_FakeDecoder())

    class _TrackingPipelineManager:
        apply_calls = 0
        restore_calls = 0

        def __init__(self, _cfg):
            self.cfg = _cfg

        def decide_pipeline(
            self,
            image_size_bytes: int,
            queue_size: int,
            aggregated_comp_rate: float | None = None,
            processed_frames_count: int | None = None,
            compression_level: int = 1,
        ):
            return SimpleNamespace(skip_obj_detection=False, use_fast_path=True)

        def apply_pipeline_config(self, context, *, img_size=None):
            type(self).apply_calls += 1

        def restore_config(self):
            type(self).restore_calls += 1

    monkeypatch.setattr(semantic_codec_bridge, "EncoderPipelineManager", _TrackingPipelineManager)

    img = Image.new("RGB", (8, 5), color="white")
    jpeg_bytes = bridge._save_jpeg_from_image(img)

    with pytest.raises(RuntimeError, match="bridge-bg-failure"):
        bridge.encode_from_jpeg(jpeg_bytes, img_id=1, queue_length=10).result()

    assert _TrackingPipelineManager.apply_calls == 1
    assert _TrackingPipelineManager.restore_calls == 1



def test_encode_from_jpeg_applies_three_queue_tiers_in_bridge():
    cfg = _cfg()
    cfg.pipeline_manager.queue_backlog_threshold_1 = 2
    cfg.pipeline_manager.queue_backlog_threshold_2 = 4
    cfg.pipeline_manager.queue_backlog_threshold_3 = 6

    class _TierTrackingEncoder(_FakeEncoder):
        def __init__(self):
            super().__init__()
            self.obj_fast_flags = []
            self.bg_fast_flags = []
            self.extract_calls = 0

        def extract_objs(self, pil_img):
            self.extract_calls += 1
            return []

        def compress_objs(self, crops, tar_objs_bytes: int, **kwargs):
            self.obj_fast_flags.append(bool(kwargs.get("use_fast_path", False)))
            return crops

        def compress_background(self, pil_img, tar_enc_data_bytes: int, crops, **kwargs):
            self.bg_fast_flags.append(bool(kwargs.get("use_fast_path", False)))
            return super().compress_background(pil_img, tar_enc_data_bytes, crops, **kwargs)

    encoder = _TierTrackingEncoder()
    bridge = SemanticCodecBridge(cfg=cfg, encoder=encoder, decoder=_FakeDecoder())
    jpeg_bytes = bridge._save_jpeg_from_image(Image.new("RGB", (8, 5), color="white"))

    result_bg_fast_only = bridge.encode_from_jpeg(jpeg_bytes, img_id=1, queue_length=3).result()
    result_full_fast = bridge.encode_from_jpeg(jpeg_bytes, img_id=2, queue_length=5).result()
    # With fast-full active, reaching threshold_3 escalates to skip-obj state.
    result_skip_obj_from_latch = bridge.encode_from_jpeg(jpeg_bytes, img_id=3, queue_length=6).result()

    # On a fresh manager state, q=6 enters skip-obj tier.
    fresh_encoder = _TierTrackingEncoder()
    fresh_bridge = SemanticCodecBridge(cfg=cfg, encoder=fresh_encoder, decoder=_FakeDecoder())
    result_skip_obj = fresh_bridge.encode_from_jpeg(jpeg_bytes, img_id=1, queue_length=6).result()

    assert result_bg_fast_only.fast_path_selected is True
    assert result_bg_fast_only.obj_detection_skipped is False
    assert result_full_fast.fast_path_selected is True
    assert result_full_fast.obj_detection_skipped is False
    assert result_skip_obj_from_latch.fast_path_selected is True
    assert result_skip_obj_from_latch.obj_detection_skipped is True
    assert result_skip_obj.fast_path_selected is True
    assert result_skip_obj.obj_detection_skipped is True

    assert encoder.obj_fast_flags == [False, True]
    assert encoder.bg_fast_flags == [True, True, True]
    assert encoder.extract_calls == 2


def test_encode_from_jpeg_forced_skip_uses_normal_bg_then_fast_bg_with_queue_growth():
    cfg = _cfg()
    cfg.pipeline_manager.queue_backlog_threshold_1 = 5
    cfg.pipeline_manager.queue_backlog_threshold_2 = 10
    cfg.pipeline_manager.queue_backlog_threshold_3 = 15

    encoder = _SkipObjBgTrackingEncoder()
    bridge = SemanticCodecBridge(cfg=cfg, encoder=encoder, decoder=_FakeDecoder())
    jpeg_bytes = bridge._save_jpeg_from_image(Image.new("RGB", (8, 5), color="white"))

    low_queue = bridge.encode_from_jpeg(jpeg_bytes, img_id=1, queue_length=0, compression_level=2).result()
    high_queue = bridge.encode_from_jpeg(jpeg_bytes, img_id=2, queue_length=7, compression_level=2).result()

    assert low_queue.obj_detection_skipped is True
    assert low_queue.fast_path_selected is False
    assert high_queue.obj_detection_skipped is True
    assert high_queue.fast_path_selected is True
    assert encoder.bg_fast_flags == [False, True]


def test_encode_from_jpeg_non_level_2_forces_skip_without_forcing_fast_bg():
    cfg = _cfg()

    class _LevelSkipTrackingEncoder(_FakeEncoder):
        def __init__(self):
            super().__init__()
            self.bg_fast_flags = []

        def extract_objs(self, pil_img):
            raise AssertionError("extract_objs should not be called when compression_level!=2")

        def compress_objs(self, crops, tar_objs_bytes: int, **kwargs):
            raise AssertionError("compress_objs should not be called when compression_level!=2")

        def compress_background(self, pil_img, tar_enc_data_bytes: int, crops, **kwargs):
            self.bg_fast_flags.append(bool(kwargs.get("use_fast_path", False)))
            return super().compress_background(pil_img, tar_enc_data_bytes, crops, **kwargs)

    encoder = _LevelSkipTrackingEncoder()
    bridge = SemanticCodecBridge(cfg=cfg, encoder=encoder, decoder=_FakeDecoder())
    jpeg_bytes = bridge._save_jpeg_from_image(Image.new("RGB", (8, 5), color="white"))

    result = bridge.encode_from_jpeg(jpeg_bytes, img_id=1, queue_length=0, compression_level=1).result()

    assert result.obj_detection_skipped is True
    assert result.fast_path_selected is False
    assert encoder.bg_fast_flags == [False]


def test_encode_from_jpeg_passes_aggregated_comp_rate_to_pipeline_manager(monkeypatch):
    cfg = _cfg()
    cfg.pipeline_manager.adaptive_compression_rate_warmup_frames = 1
    encoder = _FakeEncoder()
    bridge = SemanticCodecBridge(cfg=cfg, encoder=encoder, decoder=_FakeDecoder())

    class _RecordingPipelineManager:
        aggregated_inputs = []
        processed_frame_inputs = []

        def __init__(self, _cfg):
            self.cfg = _cfg

        def decide_pipeline(
            self,
            image_size_bytes: int,
            queue_size: int,
            aggregated_comp_rate: float | None = None,
            processed_frames_count: int | None = None,
            compression_level: int = 1,
        ):
            type(self).aggregated_inputs.append(aggregated_comp_rate)
            type(self).processed_frame_inputs.append(processed_frames_count)
            return SimpleNamespace(skip_obj_detection=False, use_fast_path=False)

        def apply_pipeline_config(self, context, *, img_size=None):
            return None

        def restore_config(self):
            return None

    monkeypatch.setattr(semantic_codec_bridge, "EncoderPipelineManager", _RecordingPipelineManager)

    jpeg_bytes = bridge._save_jpeg_from_image(Image.new("RGB", (8, 5), color="white"))

    bridge.encode_from_jpeg(jpeg_bytes, img_id=1, queue_length=1).result()
    bridge.encode_from_jpeg(jpeg_bytes, img_id=2, queue_length=1).result()

    assert _RecordingPipelineManager.aggregated_inputs[0] is None
    assert _RecordingPipelineManager.processed_frame_inputs[0] == 0
    assert _RecordingPipelineManager.aggregated_inputs[1] == pytest.approx(len(jpeg_bytes) / 6.0)
    assert _RecordingPipelineManager.processed_frame_inputs[1] == 1


def test_encode_from_jpeg_applies_level_specific_compression_rate_during_encode_and_restores_afterward():
    cfg = _cfg()
    cfg.enc.compression_rate = 55.0
    cfg.enc.compression_levels = SimpleNamespace(level_1=10.0, level_2=100.0)
    cfg.img_process.encoders_tag_bg_level_2 = {"mono-2bit": 1}
    cfg.img_process.encoders_tag_objs_level_2 = {"mono-4bit": 2}

    encoder = _RateRecordingEncoder(cfg)
    bridge = SemanticCodecBridge(cfg=cfg, encoder=encoder, decoder=_FakeDecoder())
    jpeg_bytes = bridge._save_jpeg_from_image(Image.new("RGB", (8, 5), color="white"))

    bridge.encode_from_jpeg(jpeg_bytes, img_id=1, queue_length=1, compression_level=2).result()

    assert encoder.seen_rates == [100.0]
    assert encoder.bg_seen_rates == [100.0]
    assert cfg.enc.compression_rate == 55.0


def test_encode_from_jpeg_resets_aggregate_history_when_compression_level_changes(monkeypatch):
    cfg = _cfg()
    cfg.pipeline_manager.adaptive_compression_rate_warmup_frames = 1
    encoder = _FakeEncoder()
    bridge = SemanticCodecBridge(cfg=cfg, encoder=encoder, decoder=_FakeDecoder())

    real_pipeline_manager = semantic_codec_bridge.EncoderPipelineManager

    class _RecordingPipelineManager:
        aggregated_inputs = []
        processed_frame_inputs = []

        def __init__(self, _cfg):
            self._delegate = real_pipeline_manager(_cfg)

        def decide_pipeline(
            self,
            image_size_bytes: int,
            queue_size: int,
            aggregated_comp_rate: float | None = None,
            processed_frames_count: int | None = None,
            compression_level: int = 1,
        ):
            type(self).aggregated_inputs.append(aggregated_comp_rate)
            type(self).processed_frame_inputs.append(processed_frames_count)
            return self._delegate.decide_pipeline(
                image_size_bytes=image_size_bytes,
                queue_size=queue_size,
                aggregated_comp_rate=aggregated_comp_rate,
                processed_frames_count=processed_frames_count,
                compression_level=compression_level,
            )

        def apply_pipeline_config(self, context, *, img_size=None):
            self._delegate.apply_pipeline_config(context, img_size=img_size)

        def restore_config(self):
            self._delegate.restore_config()

        def __getattr__(self, name):
            return getattr(self._delegate, name)

    monkeypatch.setattr(semantic_codec_bridge, "EncoderPipelineManager", _RecordingPipelineManager)

    jpeg_small = bridge._save_jpeg_from_image(Image.new("RGB", (8, 5), color="white"))
    jpeg_large = bridge._save_jpeg_from_image(Image.new("RGB", (16, 10), color="blue"))

    bridge.encode_from_jpeg(jpeg_small, img_id=1, queue_length=1, compression_level=1).result()
    bridge.encode_from_jpeg(jpeg_large, img_id=2, queue_length=1, compression_level=2).result()
    bridge.encode_from_jpeg(jpeg_small, img_id=3, queue_length=1, compression_level=2).result()

    assert _RecordingPipelineManager.aggregated_inputs[0] is None
    assert _RecordingPipelineManager.processed_frame_inputs[0] == 0
    assert _RecordingPipelineManager.aggregated_inputs[1] == pytest.approx(len(jpeg_small) / 6.0)
    assert _RecordingPipelineManager.processed_frame_inputs[1] == 1

    # After the level change on frame 2, frame 3 must see only frame 2 history.
    assert _RecordingPipelineManager.aggregated_inputs[2] == pytest.approx(len(jpeg_large) / 6.0)
    assert _RecordingPipelineManager.processed_frame_inputs[2] == 1


def test_decode_payload_runs_demux_decompress_and_paste(monkeypatch):
    decoder = _FakeDecoder()
    bridge = SemanticCodecBridge(cfg=_cfg(), encoder=_FakeEncoder(), decoder=decoder)
    paste_call = {}

    fake_img_dec_data = SimpleNamespace(
        img_idx=None,
        org_img_size=(8, 5),
        bg=SimpleNamespace(),
        crops=[],
    )

    def _fake_demux(payload, mux_cfg, img_idx=None, **kwargs):
        fake_img_dec_data.img_idx = img_idx
        return fake_img_dec_data

    monkeypatch.setattr(semantic_codec_bridge, "_demux_frame", _fake_demux)

    def _fake_paste(img_dec_data, margin_percent, **kwargs):
        paste_call["margin_percent"] = margin_percent
        paste_call.update(kwargs)
        return Image.new("RGB", (8, 5), color="black")

    monkeypatch.setattr(
        semantic_codec_bridge,
        "_paste_with_margin",
        _fake_paste,
    )

    result = bridge.decode_payload(b"frame")

    assert result.img_idx == 1
    assert result.image.size == (8, 5)
    assert decoder.bg_calls == 1
    assert paste_call == {
        "margin_percent": 2.0,
        "feather_ratio": 0.4,
        "feather_min_px": 2,
    }


def test_decode_payload_rejects_reconstruction_size_mismatch(monkeypatch):
    bridge = SemanticCodecBridge(cfg=_cfg(), encoder=_FakeEncoder(), decoder=_FakeDecoder())

    fake_img_dec_data = SimpleNamespace(
        img_idx=None,
        org_img_size=(8, 5),
        bg=SimpleNamespace(),
        crops=[],
    )
    def _fake_demux(payload, mux_cfg, img_idx=None, **kwargs):
        fake_img_dec_data.img_idx = img_idx
        return fake_img_dec_data

    monkeypatch.setattr(semantic_codec_bridge, "_demux_frame", _fake_demux)
    monkeypatch.setattr(
        semantic_codec_bridge,
        "_paste_with_margin",
        lambda img_dec_data, margin_percent, **kwargs: Image.new("RGB", (7, 5), color="black"),
    )

    with pytest.raises(ValueError, match="Reconstructed image size"):
        bridge.decode_payload(b"frame")


def test_bridge_decode_payload_uses_split_bg_obj_tags(monkeypatch):
    cfg = _cfg()
    bridge = SemanticCodecBridge(cfg=cfg, encoder=_FakeEncoder(), decoder=Decoder(cfg))

    crop = SimpleNamespace(
        encoder_index=2,
        decoded_obj=b"obj",
        obj_size_scaled=(2, 2),
        expanded_bbox=(0, 0, 2, 2),
        recon_pil=None,
    )
    fake_img_dec_data = SimpleNamespace(
        img_idx=None,
        org_img_size=(8, 5),
        bg=SimpleNamespace(
            encoder_index=1,
            encoded_data=b"bg",
            scaled_size=(2, 2),
            recon_pil=None,
            mask=None,
        ),
        crops=[crop],
    )

    called = []

    def _fake_decode_img(cls, **kwargs):
        called.append(kwargs["enc_name"])
        size = kwargs.get("scaled_size") or (2, 2)
        return Image.new("L", size, color=0), None

    def _fake_demux(payload, mux_cfg, img_idx=None, **kwargs):
        fake_img_dec_data.img_idx = img_idx
        return fake_img_dec_data

    monkeypatch.setattr(semantic_codec_bridge, "_demux_frame", _fake_demux)
    monkeypatch.setattr(Decoder, "decode_img", classmethod(_fake_decode_img))
    monkeypatch.setattr(
        semantic_codec_bridge,
        "_paste_with_margin",
        lambda img_dec_data, margin_percent, **kwargs: Image.new("RGB", (8, 5), color="black"),
    )

    bridge.decode_payload(b"frame")

    assert called == ["mono-2bit", "mono-4bit"]


def test_bridge_decode_payload_routes_mono_skel_obj_tag(monkeypatch):
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs_level_1 = {"mono-skel-v1": 8}
    cfg.img_process.encoders_tag = {"mono-2bit": 1, "mono-skel-v1": 8}
    bridge = SemanticCodecBridge(cfg=cfg, encoder=_FakeEncoder(), decoder=Decoder(cfg))

    crop = SimpleNamespace(
        encoder_index=8,
        decoded_obj=b"obj",
        obj_size_scaled=(2, 2),
        expanded_bbox=(0, 0, 2, 2),
        recon_pil=None,
    )
    fake_img_dec_data = SimpleNamespace(
        img_idx=None,
        org_img_size=(8, 5),
        bg=SimpleNamespace(
            encoder_index=1,
            encoded_data=b"bg",
            scaled_size=(2, 2),
            recon_pil=None,
            mask=None,
        ),
        crops=[crop],
    )

    called = []

    def _fake_decode_img(cls, **kwargs):
        called.append(kwargs["enc_name"])
        size = kwargs.get("scaled_size") or (2, 2)
        return Image.new("L", size, color=0), None

    def _fake_demux(payload, mux_cfg, img_idx=None, **kwargs):
        fake_img_dec_data.img_idx = img_idx
        return fake_img_dec_data

    monkeypatch.setattr(semantic_codec_bridge, "_demux_frame", _fake_demux)
    monkeypatch.setattr(Decoder, "decode_img", classmethod(_fake_decode_img))
    monkeypatch.setattr(
        semantic_codec_bridge,
        "_paste_with_margin",
        lambda img_dec_data, margin_percent, **kwargs: Image.new("RGB", (8, 5), color="black"),
    )

    bridge.decode_payload(b"frame")

    assert called == ["mono-2bit", "mono-skel-v1"]


def test_bridge_decode_payload_routes_mono_shape_obj_tag(monkeypatch):
    cfg = _cfg()
    cfg.img_process.encoders_tag_objs_level_1 = {"mono-shape-v1": 9}
    cfg.img_process.encoders_tag = {"mono-2bit": 1, "mono-shape-v1": 9}
    bridge = SemanticCodecBridge(cfg=cfg, encoder=_FakeEncoder(), decoder=Decoder(cfg))

    crop = SimpleNamespace(
        encoder_index=9,
        decoded_obj=b"obj",
        obj_size_scaled=(2, 2),
        expanded_bbox=(0, 0, 2, 2),
        recon_pil=None,
    )
    fake_img_dec_data = SimpleNamespace(
        img_idx=None,
        org_img_size=(8, 5),
        bg=SimpleNamespace(
            encoder_index=1,
            encoded_data=b"bg",
            scaled_size=(2, 2),
            recon_pil=None,
            mask=None,
        ),
        crops=[crop],
    )

    called = []

    def _fake_decode_img(cls, **kwargs):
        called.append(kwargs["enc_name"])
        size = kwargs.get("scaled_size") or (2, 2)
        return Image.new("L", size, color=0), None

    def _fake_demux(payload, mux_cfg, img_idx=None, **kwargs):
        fake_img_dec_data.img_idx = img_idx
        return fake_img_dec_data

    monkeypatch.setattr(semantic_codec_bridge, "_demux_frame", _fake_demux)
    monkeypatch.setattr(Decoder, "decode_img", classmethod(_fake_decode_img))
    monkeypatch.setattr(
        semantic_codec_bridge,
        "_paste_with_margin",
        lambda img_dec_data, margin_percent, **kwargs: Image.new("RGB", (8, 5), color="black"),
    )

    bridge.decode_payload(b"frame")

    assert called == ["mono-2bit", "mono-shape-v1"]


