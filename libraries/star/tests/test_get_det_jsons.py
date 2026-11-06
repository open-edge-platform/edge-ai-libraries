from types import SimpleNamespace

import pytest
from PIL import Image

from semantic_img_comp.evaluation.get_det_jsons import generate_det_jsons



def test_generate_det_jsons_raises_contextual_error_for_image_failures(tmp_path, monkeypatch):
    recon_path = tmp_path / "frame_001.jpg"
    orig_path = tmp_path / "frame_001_orig.jpg"
    Image.new("RGB", (4, 4), color="white").save(recon_path, format="JPEG")
    Image.new("RGB", (4, 4), color="white").save(orig_path, format="JPEG")

    cfg = SimpleNamespace(
        io=SimpleNamespace(
            output_dir=tmp_path,
            recon_img_dir=tmp_path / "recon",
            orig_img_dir=tmp_path / "orig",
            annot_file=None,
            save_plots=False,
        ),
        model=SimpleNamespace(
            enc_yolo_model_path=tmp_path,
            tile_size=None,
        ),
    )

    monkeypatch.setattr(
        "semantic_img_comp.evaluation.get_det_jsons.load_yolo_model",
        lambda model_path: (object(), {}),
    )
    monkeypatch.setattr(
        "semantic_img_comp.evaluation.get_det_jsons.load_paths",
        lambda path: [recon_path] if "recon" in str(path) else [orig_path],
    )
    monkeypatch.setattr(
        "semantic_img_comp.evaluation.get_det_jsons.run_yolo",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("yolo exploded")),
    )

    with pytest.raises(RuntimeError, match="frame_001.jpg") as excinfo:
        generate_det_jsons(cfg)

    assert "img_id=1" in str(excinfo.value)

