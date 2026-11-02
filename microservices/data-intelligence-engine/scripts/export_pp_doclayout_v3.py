# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Export PP-DocLayoutV3 to ONNX for OpenVINO inference.

Run this once in an isolated environment with Transformers 5.5.4 or newer:

    PYTHONPATH=src python scripts/export_pp_doclayout_v3.py

The engine's OpenVINO runtime only needs the generated ONNX file and does not
need the newer Transformers package used during conversion.
"""

import argparse
import json
import os

import config
from core.embedding import resolve_model_path, workspace_model_dir
from core.layout import pp_doclayout_v3_onnx_path


def export_pp_doclayout_v3(model_source: str, out_dir: str) -> str:
    """Prepare the ONNX artifact explicitly, never from the engine runtime."""
    import inspect

    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModelForObjectDetection

    onnx_path = pp_doclayout_v3_onnx_path(out_dir)
    if os.path.exists(onnx_path):
        return onnx_path
    try:
        model = AutoModelForObjectDetection.from_pretrained(model_source)
        processor = AutoImageProcessor.from_pretrained(model_source)
    except ValueError as error:
        if "pp_doclayout_v3" not in str(error).lower():
            raise
        raise RuntimeError(
            "Exporting PP-DocLayoutV3 requires a Transformers release that "
            "supports pp_doclayout_v3 (verified with 5.5.4). Run this script in "
            "an isolated conversion environment; OpenVINO inference does not "
            "require that upgrade."
        ) from error
    model.eval()

    class Wrapper(torch.nn.Module):
        def __init__(self, detector):
            super().__init__()
            self.detector = detector

        def forward(self, pixel_values):
            output = self.detector(pixel_values=pixel_values)
            return output.logits, output.pred_boxes

    dummy = Image.new("RGB", (800, 800), (255, 255, 255))
    pixel_values = processor(images=dummy, return_tensors="pt")["pixel_values"]
    os.makedirs(out_dir, exist_ok=True)
    export_kwargs = {
        "input_names": ["pixel_values"],
        "output_names": ["logits", "pred_boxes"],
        "dynamic_axes": {
            "pixel_values": {0: "batch"},
            "logits": {0: "batch"},
            "pred_boxes": {0: "batch"},
        },
        "opset_version": 17,
        "do_constant_folding": False,
    }
    if "dynamo" in inspect.signature(torch.onnx.export).parameters:
        export_kwargs["dynamo"] = False
    with torch.no_grad():
        torch.onnx.export(
            Wrapper(model).eval(), (pixel_values,), onnx_path, **export_kwargs
        )

    processor.save_pretrained(out_dir)
    id2label = {int(k): str(v) for k, v in (model.config.id2label or {}).items()}
    with open(os.path.join(out_dir, "id2label.json"), "w", encoding="utf-8") as handle:
        json.dump(id2label, handle, ensure_ascii=False)
    return onnx_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", default=config.LAYOUT_MODEL_PATH)
    parser.add_argument("--model-id", default=config.LAYOUT_MODEL_ID)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    resolved = resolve_model_path(args.model_path)
    source = resolved if os.path.isdir(resolved) else args.model_id
    output_dir = args.output_dir or (
        resolved if os.path.isdir(resolved) else workspace_model_dir(args.model_path)
    )
    onnx_path = export_pp_doclayout_v3(source, output_dir)
    print(f"PP-DocLayoutV3 ONNX model: {onnx_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())