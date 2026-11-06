import pytest
from types import SimpleNamespace

from semantic_img_comp.evaluation import eval_wrapper


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--recon_img_dir", "recon", "--output_dir", "out", "--annot_file", "ann.json"], False),
        (["--recon_img_dir", "recon", "--output_dir", "out", "--annot_file", "ann.json", "--save_plots"], True),
        (["--recon_img_dir", "recon", "--output_dir", "out", "--annot_file", "ann.json", "--no-save_plots"], False),
    ],
)
def test_eval_wrapper_parser_handles_boolean_optional_action(argv, expected):
    args = eval_wrapper.build_parser().parse_args(argv)

    assert args.save_plots is expected


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (
            [
                "--recon_img_dir",
                "recon",
                "--orig_img_dir",
                "orig",
                "--output_dir",
                "out",
                "--eval-metric",
                "cosine similarity",
            ],
            "cosine similarity",
        ),
        (
            [
                "--recon_img_dir",
                "recon",
                "--orig_img_dir",
                "orig",
                "--output_dir",
                "out",
                "--eval-metic",
                "semantic similarity",
            ],
            "semantic similarity",
        ),
    ],
)
def test_eval_wrapper_parser_accepts_eval_metric_alias(argv, expected):
    args = eval_wrapper.build_parser().parse_args(argv)
    assert args.eval_metric == expected


def test_eval_wrapper_parser_accepts_clip_proxy_options():
    args = eval_wrapper.build_parser().parse_args(
        [
            "--recon_img_dir",
            "recon",
            "--orig_img_dir",
            "orig",
            "--output_dir",
            "out",
            "--eval-metric",
            "cosine similarity",
            "--hf-http-proxy",
            "http://proxy.example:8080",
            "--hf-https-proxy",
            "http://proxy.example:8080",
            "--clip-local-files-only",
        ]
    )

    assert args.hf_http_proxy == "http://proxy.example:8080"
    assert args.hf_https_proxy == "http://proxy.example:8080"
    assert args.clip_local_files_only is True


def test_main_dispatches_to_cosine_path(monkeypatch, tmp_path):
    called = {"cosine": False, "det": False, "map": False}

    cfg = SimpleNamespace(
        io=SimpleNamespace(output_dir=tmp_path, annot_file=None, recon_img_dir=tmp_path, orig_img_dir=tmp_path),
        model=SimpleNamespace(enc_yolo_model_path=tmp_path / "yolo.pt"),
    )

    monkeypatch.setattr(eval_wrapper, "load_config", lambda _=None: cfg)
    def _cosine_mock(_, **kwargs):
        called["cosine"] = True
        called["kwargs"] = kwargs

    monkeypatch.setattr(eval_wrapper, "_compute_clip_cosine_similarity", _cosine_mock)
    monkeypatch.setattr(eval_wrapper, "generate_det_jsons", lambda _: called.__setitem__("det", True))

    rc = eval_wrapper.main(
        [
            "--recon_img_dir",
            str(tmp_path),
            "--orig_img_dir",
            str(tmp_path),
            "--output_dir",
            str(tmp_path),
            "--eval-metric",
            "cosine similarity",
            "--hf-http-proxy",
            "http://proxy.example:8080",
            "--hf-https-proxy",
            "http://proxy.example:8080",
            "--clip-local-files-only",
        ]
    )

    assert rc == 0
    assert called["cosine"] is True
    assert called["kwargs"].get("hf_http_proxy") == "http://proxy.example:8080"
    assert called["kwargs"].get("hf_https_proxy") == "http://proxy.example:8080"
    assert called["kwargs"].get("local_files_only") is True
    assert called["det"] is False
    assert called["map"] is False


def test_main_dispatches_to_semantic_path(monkeypatch, tmp_path):
    called = {"cosine": False, "det": False, "map": False}
    ann_file = tmp_path / "ann.json"
    ann_file.write_text("{}", encoding="utf-8")

    cfg = SimpleNamespace(
        io=SimpleNamespace(output_dir=tmp_path, annot_file=None, recon_img_dir=tmp_path, orig_img_dir=tmp_path),
        model=SimpleNamespace(enc_yolo_model_path=tmp_path / "yolo.pt"),
    )

    monkeypatch.setattr(eval_wrapper, "load_config", lambda _=None: cfg)
    monkeypatch.setattr(eval_wrapper, "_compute_clip_cosine_similarity", lambda _, **__: called.__setitem__("cosine", True))
    monkeypatch.setattr(eval_wrapper, "generate_det_jsons", lambda _: called.__setitem__("det", True))

    rc = eval_wrapper.main(
        [
            "--recon_img_dir",
            str(tmp_path),
            "--orig_img_dir",
            str(tmp_path),
            "--output_dir",
            str(tmp_path),
            "--annot_file",
            str(ann_file),
            "--eval-metric",
            "semantic similarity",
        ]
    )

    assert rc == 0
    assert called["cosine"] is False
    assert called["det"] is True


