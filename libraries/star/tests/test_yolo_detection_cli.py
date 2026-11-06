from types import SimpleNamespace
from pathlib import Path

import pytest

import semantic_img_comp.evaluation.yolo_detection as yolo_detection


def test_build_parser_allows_omitting_yolo_model_path():
    parser = yolo_detection.build_parser()
    args = parser.parse_args(["--input_dir", "in", "--output_dir", "out"])
    assert args.yolo_model_path is None


def test_main_uses_model_path_from_config_when_cli_not_provided(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    model_path = tmp_path / "cfg_model.pt"
    input_dir.mkdir()
    output_dir.mkdir()
    model_path.write_bytes(b"x")

    cfg = SimpleNamespace(model=SimpleNamespace(enc_yolo_model_path=model_path))
    captured = {}

    monkeypatch.setattr(yolo_detection, "load_config", lambda _: cfg)

    def _fake_run_detection_on_images(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(yolo_detection, "run_detection_on_images", _fake_run_detection_on_images)

    rc = yolo_detection.main(["--input_dir", str(input_dir), "--output_dir", str(output_dir)])
    assert rc == 0
    assert captured["yolo_model_path"] == model_path


def test_main_cli_path_overrides_config_path(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    cfg_model_path = tmp_path / "cfg_model.pt"
    cli_model_path = tmp_path / "cli_model.pt"
    input_dir.mkdir()
    output_dir.mkdir()
    cfg_model_path.write_bytes(b"cfg")
    cli_model_path.write_bytes(b"cli")

    cfg = SimpleNamespace(model=SimpleNamespace(enc_yolo_model_path=cfg_model_path))
    captured = {}

    monkeypatch.setattr(yolo_detection, "load_config", lambda _: cfg)

    def _fake_run_detection_on_images(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(yolo_detection, "run_detection_on_images", _fake_run_detection_on_images)

    rc = yolo_detection.main(
        [
            "--input_dir",
            str(input_dir),
            "--output_dir",
            str(output_dir),
            "--yolo_model_path",
            str(cli_model_path),
        ]
    )
    assert rc == 0
    assert captured["yolo_model_path"] == cli_model_path


def test_main_raises_when_no_model_path_provided_anywhere(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    output_dir.mkdir()

    cfg = SimpleNamespace(model=SimpleNamespace(enc_yolo_model_path=None))
    monkeypatch.setattr(yolo_detection, "load_config", lambda _: cfg)

    with pytest.raises(ValueError, match="YOLO model path is not set"):
        yolo_detection.main(["--input_dir", str(input_dir), "--output_dir", str(output_dir)])

