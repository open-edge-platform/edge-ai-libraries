# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from types import SimpleNamespace

import pytest

from semantic_img_comp import main


def _make_cfg(tmp_path: Path):
    return SimpleNamespace(
        app=SimpleNamespace(log_level="INFO"),
        model=SimpleNamespace(enc_yolo_model_path=tmp_path / "missing-model.pt"),
        img_process=SimpleNamespace(canny_mode="old"),
        io=SimpleNamespace(
            input_dir=tmp_path,
            output_dir=tmp_path / "out",
            annot_file=None,
            annot_dir=None,
            print_runtime_logs=False,
        ),
        enc=SimpleNamespace(obj_budget_ratio=1.0),
    )


def test_parser_accepts_skip_obj_detection_flag():
    parser = main.build_parser()
    args = parser.parse_args(["--role", "encoder", "--skip-obj-detction"])
    assert args.skip_obj_detection is True


def test_parser_accepts_skip_obj_detection_flag_alias():
    parser = main.build_parser()
    args = parser.parse_args(["--role", "encoder", "--skip-obj-detection"])
    assert args.skip_obj_detection is True


def test_parser_accepts_zero_fps_for_unthrottled_run():
    parser = main.build_parser()
    args = parser.parse_args(["--role", "encoder", "--fps", "0"])
    assert args.fps == 0.0


def test_apply_cli_overrides_forces_obj_budget_ratio_to_zero(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    args = main.build_parser().parse_args([
        "--role",
        "encoder",
        "--input",
        str(tmp_path),
        "--output",
        str(tmp_path / "out"),
        "--skip-obj-detction",
    ])

    main._apply_cli_overrides(cfg, args)

    assert cfg.enc.obj_budget_ratio == 0.0
    assert cfg.model.skip_obj_detection is True


def test_parser_accepts_canny_mode_flag():
    parser = main.build_parser()
    args = parser.parse_args(["--role", "encoder", "--canny-mode", "new"])
    assert args.canny_mode == "new"


def test_apply_cli_overrides_sets_canny_mode(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    args = main.build_parser().parse_args([
        "--role",
        "encoder",
        "--input",
        str(tmp_path),
        "--output",
        str(tmp_path / "out"),
        "--canny-mode",
        "new",
    ])

    main._apply_cli_overrides(cfg, args)

    assert cfg.img_process.canny_mode == "new"


def test_parser_accepts_dlstreamer_pipeline_name_flag():
    parser = main.build_parser()
    args = parser.parse_args([
        "--role", "encoder", "--dlstreamer-pipeline-name", "star_image_object_detection_npu",
    ])
    assert args.dlstreamer_pipeline_name == "star_image_object_detection_npu"


def test_apply_cli_overrides_sets_dlstreamer_pipeline_name(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    cfg.model.dlstreamer_pipeline_name = "star_image_object_detection"
    args = main.build_parser().parse_args([
        "--role",
        "encoder",
        "--input",
        str(tmp_path),
        "--output",
        str(tmp_path / "out"),
        "--dlstreamer-pipeline-name",
        "star_image_object_detection_npu",
    ])

    main._apply_cli_overrides(cfg, args)

    assert cfg.model.dlstreamer_pipeline_name == "star_image_object_detection_npu"


def test_apply_cli_overrides_leaves_dlstreamer_pipeline_name_unset_when_omitted(tmp_path: Path):
    cfg = _make_cfg(tmp_path)
    cfg.model.dlstreamer_pipeline_name = "star_image_object_detection"
    args = main.build_parser().parse_args([
        "--role",
        "encoder",
        "--input",
        str(tmp_path),
        "--output",
        str(tmp_path / "out"),
    ])

    main._apply_cli_overrides(cfg, args)

    assert cfg.model.dlstreamer_pipeline_name == "star_image_object_detection"


def test_main_passes_skip_obj_detection_to_encoder_runner(tmp_path: Path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.io.output_dir.mkdir(parents=True, exist_ok=True)
    called = {}

    monkeypatch.setattr(main, "load_config", lambda _: cfg)
    monkeypatch.setattr(main, "_configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_attach_root_file_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_validate_runtime_paths", lambda cfg, role, skip_obj_detection=False: None)
    monkeypatch.setattr(main.healthcheck, "start_status_server", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_run_feeder", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "Encoder", lambda cfg: SimpleNamespace())

    def _fake_run_semantic_encoder(cfg, host, port, fps, skip_obj_detection=False, bridge=None):
        called["skip_obj_detection"] = skip_obj_detection
        called["obj_budget_ratio"] = cfg.enc.obj_budget_ratio

    monkeypatch.setattr(main, "_run_encoder", _fake_run_semantic_encoder)
    monkeypatch.setattr(main, "_run_encoder_service", lambda *_args, **_kwargs: None)

    exit_code = main.main([
        "--role",
        "encoder",
        "--input",
        str(tmp_path),
        "--output",
        str(tmp_path / "out"),
        "--skip-obj-detction",
        "--decoder-url",
        "http://decoder:8000",
    ])

    assert exit_code == main.EXIT_OK
    assert called["skip_obj_detection"] is True
    assert called["obj_budget_ratio"] == 0.0


def test_main_encoder_role_requires_decoder_url(tmp_path: Path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.io.output_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(main, "load_config", lambda _: cfg)
    monkeypatch.setattr(main, "_configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_attach_root_file_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_validate_runtime_paths", lambda cfg, role, skip_obj_detection=False: None)
    monkeypatch.setattr(main.healthcheck, "start_status_server", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("DECODER_URL", raising=False)
    monkeypatch.setattr(main, "_run_encoder", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not run without --decoder-url")))
    monkeypatch.setattr(main, "_run_encoder_service", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not run without --decoder-url")))

    exit_code = main.main([
        "--role",
        "encoder",
        "--input",
        str(tmp_path),
        "--output",
        str(tmp_path / "out"),
    ])

    assert exit_code == main.EXIT_BAD_ARGS


def test_main_decoder_role_does_not_call_encoder_runner(tmp_path: Path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.io.output_dir.mkdir(parents=True, exist_ok=True)
    called = {}

    monkeypatch.setattr(main, "load_config", lambda _: cfg)
    monkeypatch.setattr(main, "_configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_attach_root_file_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_validate_runtime_paths", lambda cfg, role, skip_obj_detection=False: None)
    monkeypatch.setattr(main.healthcheck, "start_status_server", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "Decoder", lambda cfg: SimpleNamespace())
    monkeypatch.setattr(main, "_run_encoder", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("encoder runner should not be called")))
    monkeypatch.setattr(main, "_run_encoder_service", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("encoder service should not be called")))

    def _fake_run_semantic_decoder(cfg, host, port, bridge=None):
        called["decoder_called"] = True

    monkeypatch.setattr(main, "_run_decoder", _fake_run_semantic_decoder)
    monkeypatch.setattr(main, "_run_decoder_service", lambda *_args, **_kwargs: called.setdefault("decoder_service_called", True))

    exit_code = main.main([
        "--role",
        "decoder",
        "--input",
        str(tmp_path),
        "--output",
        str(tmp_path / "out"),
    ])

    assert exit_code == main.EXIT_OK
    assert called["decoder_called"] is True
    assert called["decoder_service_called"] is True


def test_parser_rejects_legacy_service_role_choices():
    parser = main.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--role", "encoder-service"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--role", "decoder-service"])


def test_parser_defaults_service_host_and_port():
    parser = main.build_parser()
    args = parser.parse_args(["--role", "encoder"])
    assert args.service_host == "0.0.0.0"  # nosec B104 - default bind matches container usage
    assert args.service_port == 8000


def test_run_concurrently_runs_every_target():
    called = []
    main._run_concurrently("test", [lambda: called.append("a"), lambda: called.append("b")])
    assert sorted(called) == ["a", "b"]


def test_run_concurrently_propagates_first_exception():
    def _boom():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        main._run_concurrently("test", [_boom, lambda: None])


def test_main_encoder_role_runs_tcp_and_service_concurrently(tmp_path: Path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.io.output_dir.mkdir(parents=True, exist_ok=True)
    called = {}

    monkeypatch.setattr(main, "load_config", lambda _: cfg)
    monkeypatch.setattr(main, "_configure_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_attach_root_file_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_validate_runtime_paths", lambda cfg, role, skip_obj_detection=False: None)
    monkeypatch.setattr(main.healthcheck, "start_status_server", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_run_feeder", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "Encoder", lambda cfg: SimpleNamespace())
    monkeypatch.setattr(main, "_run_encoder", lambda *_args, **_kwargs: called.setdefault("encoder_called", True))
    monkeypatch.setattr(main, "_run_encoder_service", lambda *_args, **_kwargs: called.setdefault("encoder_service_called", True))

    exit_code = main.main([
        "--role",
        "encoder",
        "--input",
        str(tmp_path),
        "--output",
        str(tmp_path / "out"),
        "--decoder-url",
        "http://decoder:8000",
    ])

    assert exit_code == main.EXIT_OK
    assert called["encoder_called"] is True
    assert called["encoder_service_called"] is True


