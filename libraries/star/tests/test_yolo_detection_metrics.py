from pathlib import Path

from PIL import Image

from semantic_img_comp.core.object import ObjData
from semantic_img_comp.evaluation.yolo_detection import _compute_metrics


def _write_image(path: Path, size=(100, 100)) -> None:
    img = Image.new("RGB", size, color="white")
    img.save(path)


def test_compute_metrics_counts_fn_when_gt_image_has_no_detections(tmp_path: Path):
    img_path = tmp_path / "img1.png"
    _write_image(img_path)

    metrics = _compute_metrics(
        detections={},
        ground_truth={"img1": [(0, 0.5, 0.5, 0.4, 0.4)]},
        img_paths={"img1": img_path},
        iou_threshold=0.5,
    )

    assert metrics["true_positives"] == 0
    assert metrics["false_positives"] == 0
    assert metrics["false_negatives"] == 1
    assert metrics["recall"] == 0.0


def test_compute_metrics_uses_class_aware_matching(tmp_path: Path):
    img_path = tmp_path / "img2.png"
    _write_image(img_path)

    # Perfect overlap but wrong class -> should not match.
    detections = {
        "img2": [ObjData(bbox=(30, 30, 70, 70), category_id=0, det_conf=0.95)]
    }
    ground_truth = {"img2": [(1, 0.5, 0.5, 0.4, 0.4)]}

    metrics = _compute_metrics(
        detections=detections,
        ground_truth=ground_truth,
        img_paths={"img2": img_path},
        iou_threshold=0.5,
    )

    assert metrics["true_positives"] == 0
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 1


def test_compute_metrics_returns_ap_near_one_for_perfect_prediction(tmp_path: Path):
    img_path = tmp_path / "img3.png"
    _write_image(img_path)

    detections = {
        "img3": [ObjData(bbox=(30, 30, 70, 70), category_id=2, det_conf=0.99)]
    }
    ground_truth = {"img3": [(2, 0.5, 0.5, 0.4, 0.4)]}

    metrics = _compute_metrics(
        detections=detections,
        ground_truth=ground_truth,
        img_paths={"img3": img_path},
        iou_threshold=0.5,
    )

    assert metrics["true_positives"] == 1
    assert metrics["false_positives"] == 0
    assert metrics["false_negatives"] == 0
    assert metrics["average_precision"] > 0.99

