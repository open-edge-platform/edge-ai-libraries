import json
from types import SimpleNamespace

from pathlib import Path

from PIL import Image

from semantic_img_comp.enhancement import cli
from semantic_img_comp.enhancement.config import load_enhancement_config
from semantic_img_comp.enhancement import pipeline as pipeline_module
from semantic_img_comp.enhancement.pipeline import collect_images, resolve_device, run_enhancement


def test_load_enhancement_config_from_yaml(tmp_path):
    cfg_path = tmp_path / "enhancement.yaml"
    cfg_path.write_text(
        """
input_dir: ./decoded
output_dir: ./enhanced
model_cache_dir: ./cache

device: auto
mode: txt2img
sd_model_id: runwayml/stable-diffusion-v1-5
controlnet_model_id: lllyasviel/sd-controlnet-canny
num_inference_steps: 20
guidance_scale: 6.0
strength: 0.4
canny_low: 80
canny_high: 160
save_controls: true
overwrite: false
""".strip(),
        encoding="utf-8",
    )

    cfg = load_enhancement_config(cfg_path)

    assert cfg.input_dir == Path("./decoded")
    assert cfg.output_dir == Path("./enhanced")
    assert cfg.model_cache_dir == Path("./cache")
    assert cfg.device == "auto"
    assert cfg.mode == "txt2img"
    assert cfg.canny_low == 80
    assert cfg.canny_high == 160


def test_collect_images_filters_supported_extensions(tmp_path):
    img1 = tmp_path / "a.png"
    img2 = tmp_path / "b.jpeg"
    txt = tmp_path / "notes.txt"

    Image.new("RGB", (4, 4), color="black").save(img1)
    Image.new("RGB", (4, 4), color="black").save(img2)
    txt.write_text("ignore", encoding="utf-8")

    files = collect_images(tmp_path)

    assert files == [img1, img2]


def test_cli_dry_run_writes_manifest(tmp_path):
    input_dir = tmp_path / "decoded"
    input_dir.mkdir()
    Image.new("RGB", (8, 8), color="white").save(input_dir / "frame_1.png")

    output_dir = tmp_path / "enhanced"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    cfg_path = tmp_path / "enhancement.yaml"
    cfg_path.write_text(
        f"""
input_dir: {input_dir.as_posix()}
output_dir: {output_dir.as_posix()}
model_cache_dir: {cache_dir.as_posix()}
""".strip(),
        encoding="utf-8",
    )

    exit_code = cli.main(["--config", str(cfg_path), "--dry-run"])

    assert exit_code == 0
    assert (output_dir / "manifest.json").exists()
    assert not any(p.is_dir() and p.name.startswith("run_") for p in output_dir.iterdir())


def test_resolve_device_auto_returns_cpu_or_cuda():
    resolved = resolve_device("auto")
    assert resolved.startswith("cpu") or resolved.startswith("cuda")


def test_parse_gpu_ids_parses_and_deduplicates():
    assert cli._parse_gpu_ids("0,2,2,1") == [0, 1, 2]


def test_parse_gpu_ids_rejects_invalid_values():
    try:
        cli._parse_gpu_ids("0,a")
        assert False, "Expected ValueError"
    except ValueError:
        assert True


def test_run_enhancement_continues_on_image_failure_and_writes_summary(tmp_path, monkeypatch):
    input_dir = tmp_path / "decoded"
    input_dir.mkdir()
    Image.new("RGB", (8, 8), color="white").save(input_dir / "frame_1.png")
    Image.new("RGB", (8, 8), color="gray").save(input_dir / "frame_2.png")

    output_dir = tmp_path / "enhanced"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    cfg_path = tmp_path / "enhancement.yaml"
    cfg_path.write_text(
        f"""
input_dir: {input_dir.as_posix()}
output_dir: {output_dir.as_posix()}
model_cache_dir: {cache_dir.as_posix()}
mode: txt2img
save_controls: false
""".strip(),
        encoding="utf-8",
    )
    cfg = load_enhancement_config(cfg_path)

    class _FakePipe:
        def __init__(self):
            self.calls = 0

        def __call__(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("synthetic failure")
            return SimpleNamespace(images=[Image.new("RGB", (8, 8), color="black")])

    monkeypatch.setattr(pipeline_module, "_load_pipeline", lambda cfg, device: (_FakePipe(), object()))

    run_dir = run_enhancement(cfg)

    log_path = run_dir / "log" / "enhance_log.jsonl"
    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    events = [line["event"] for line in lines]

    assert "image_failed" in events
    assert "image_enhanced" in events
    assert events[-1] == "run_summary"

    summary = lines[-1]
    assert summary["total_images"] == 2
    assert summary["processed"] == 2
    assert summary["succeeded"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 0

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["summary"]["had_failures"] is True


def test_cli_dry_run_multi_gpu_writes_multi_gpu_manifest(tmp_path):
    input_dir = tmp_path / "decoded"
    input_dir.mkdir()
    Image.new("RGB", (8, 8), color="white").save(input_dir / "frame_1.png")

    output_dir = tmp_path / "enhanced"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    cfg_path = tmp_path / "enhancement.yaml"
    cfg_path.write_text(
        f"""
input_dir: {input_dir.as_posix()}
output_dir: {output_dir.as_posix()}
model_cache_dir: {cache_dir.as_posix()}
""".strip(),
        encoding="utf-8",
    )

    exit_code = cli.main(["--config", str(cfg_path), "--dry-run", "--gpu-ids", "0,1,2,3"])

    assert exit_code == 0
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["multi_gpu"] is True
    assert manifest["gpu_ids"] == [0, 1, 2, 3]




