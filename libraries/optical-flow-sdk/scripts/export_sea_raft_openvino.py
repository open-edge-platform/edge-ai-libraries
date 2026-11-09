#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Export SEA-RAFT-S to ONNX then OpenVINO IR (fixed iters, fixed H×W)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
import torch.nn as nn


class SeaRaftExportWrapper(nn.Module):
    def __init__(self, model, iters: int, scale: int):
        super().__init__()
        self.model = model
        self.iters = iters
        self.scale = scale

    def forward(self, image1: torch.Tensor, image2: torch.Tensor) -> torch.Tensor:
        # image*: NCHW float RGB 0..255
        import torch.nn.functional as F

        img1 = torch.nn.functional.interpolate(
            image1, scale_factor=2**self.scale, mode="bilinear", align_corners=False
        )
        img2 = torch.nn.functional.interpolate(
            image2, scale_factor=2**self.scale, mode="bilinear", align_corners=False
        )
        out = self.model(img1, img2, iters=self.iters, test_mode=True)
        flow = out["flow"][-1]
        flow = torch.nn.functional.interpolate(
            flow, scale_factor=0.5**self.scale, mode="bilinear", align_corners=False
        ) * (0.5**self.scale)
        return flow


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sea-raft", type=Path, required=True)
    ap.add_argument("--cfg", type=str, default="config/eval/kitti-S.json")
    ap.add_argument("--url", type=str, default="MemorySlices/Tartan-C-T-TSKH-kitti432x960-S")
    ap.add_argument("--height", type=int, default=375)
    ap.add_argument("--width", type=int, default=1242)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    sea = args.sea_raft.resolve()
    sys.path.insert(0, str(sea))
    sys.path.insert(0, str(sea / "core"))
    from config.parser import json_to_args
    from raft import RAFT

    sea_args = json_to_args(str(sea / args.cfg))
    sea_args.url = args.url
    model = RAFT.from_pretrained(args.url, args=sea_args).eval()
    wrapped = SeaRaftExportWrapper(model, iters=sea_args.iters, scale=sea_args.scale).eval()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = args.out_dir / f"sea_raft_s_{args.height}x{args.width}.onnx"
    dummy1 = torch.zeros(1, 3, args.height, args.width)
    dummy2 = torch.zeros(1, 3, args.height, args.width)
    torch.onnx.export(
        wrapped,
        (dummy1, dummy2),
        str(onnx_path),
        input_names=["prev", "next"],
        output_names=["flow"],
        opset_version=17,
        dynamo=False,
    )
    print("wrote", onnx_path)

    import openvino as ov

    ov_model = ov.convert_model(str(onnx_path))
    xml_path = args.out_dir / f"sea_raft_s_{args.height}x{args.width}.xml"
    ov.save_model(ov_model, str(xml_path))
    print("wrote", xml_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
