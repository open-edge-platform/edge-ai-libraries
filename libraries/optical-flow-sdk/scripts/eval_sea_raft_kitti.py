#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""KITTI-2015 train Fl-all for SEA-RAFT-S (P2 quality gate vs NVOFA Medium).

Requires micromamba env with SEA-RAFT deps and the princeton-vl/SEA-RAFT checkout.
Default model: HuggingFace MemorySlices/Tartan-C-T-TSKH-kitti432x960-S
Default cfg:   SEA-RAFT/config/eval/kitti-S.json

NVOFA Medium reference (Ada, published): Fl-all ≈ 19.11% @1080p class.
Gate: SEA-RAFT Fl-all <= that Medium number on KITTI train (or better).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F


def read_kitti_flow_png(path: Path) -> tuple[np.ndarray, np.ndarray]:
    png = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if png is None or png.dtype != np.uint16 or png.ndim != 3 or png.shape[2] != 3:
        raise RuntimeError(f"bad KITTI flow PNG: {path}")
    # OpenCV BGR: B=valid, G=fy, R=fx for KITTI RGB packing
    valid = png[:, :, 0] > 0
    fx = (png[:, :, 2].astype(np.float32) - 32768.0) / 64.0
    fy = (png[:, :, 1].astype(np.float32) - 32768.0) / 64.0
    return np.stack([fx, fy], axis=-1), valid


def fl_all(pred: np.ndarray, gt: np.ndarray, valid: np.ndarray) -> tuple[float, int, int]:
    epe = np.sqrt(((pred - gt) ** 2).sum(axis=-1))
    mag = np.sqrt((gt**2).sum(axis=-1))
    m = valid & np.isfinite(epe) & np.isfinite(mag)
    if not np.any(m):
        return 0.0, 0, 0
    bad = (epe[m] > 3.0) & (epe[m] > 0.05 * mag[m])
    n = int(m.sum())
    b = int(bad.sum())
    return 100.0 * b / n, b, n


def load_rgb(path: Path) -> torch.Tensor:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError(f"failed to read {path}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
    return torch.from_numpy(rgb).permute(2, 0, 1)[None]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kitti", type=Path, required=True, help="root with training/image_2 + flow_occ")
    ap.add_argument("--sea-raft", type=Path, required=True, help="SEA-RAFT repo root")
    ap.add_argument("--cfg", type=str, default="config/eval/kitti-S.json")
    ap.add_argument("--url", type=str, default="MemorySlices/Tartan-C-T-TSKH-kitti432x960-S")
    ap.add_argument("--path", type=str, default=None, help="optional local .pth / directory")
    ap.add_argument("--device", type=str, default="cpu")
    ap.add_argument("--max-pairs", type=int, default=0)
    ap.add_argument("--nvofa-medium-fl-all", type=float, default=19.11)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args()

    sea = args.sea_raft.resolve()
    sys.path.insert(0, str(sea))
    sys.path.insert(0, str(sea / "core"))

    from config.parser import json_to_args
    from raft import RAFT
    from utils.utils import load_ckpt

    sea_args = json_to_args(str(sea / args.cfg))
    sea_args.cfg = str(sea / args.cfg)
    sea_args.path = args.path
    sea_args.url = args.url
    sea_args.device = args.device

    if args.path:
        model = RAFT(sea_args)
        load_ckpt(model, args.path)
    else:
        model = RAFT.from_pretrained(args.url, args=sea_args)

    device = torch.device(args.device)
    model = model.to(device).eval()

    img_dir = args.kitti / "training" / "image_2"
    flow_dir = args.kitti / "training" / "flow_occ"
    pairs = sorted(img_dir.glob("*_10.png"))
    if args.max_pairs > 0:
        pairs = pairs[: args.max_pairs]

    fl_sum = 0.0
    epe_sum = 0.0
    n_pairs = 0
    t0 = time.perf_counter()
    with torch.no_grad():
        for p0 in pairs:
            pid = p0.name[:6]
            p1 = img_dir / f"{pid}_11.png"
            gt_path = flow_dir / f"{pid}_10.png"
            if not p1.exists() or not gt_path.exists():
                continue
            image1 = load_rgb(p0).to(device)
            image2 = load_rgb(p1).to(device)
            scale = getattr(sea_args, "scale", 0)
            img1 = F.interpolate(image1, scale_factor=2**scale, mode="bilinear", align_corners=False)
            img2 = F.interpolate(image2, scale_factor=2**scale, mode="bilinear", align_corners=False)
            out = model(img1, img2, iters=sea_args.iters, test_mode=True)
            flow = out["flow"][-1]
            flow = F.interpolate(flow, scale_factor=0.5**scale, mode="bilinear", align_corners=False) * (
                0.5**scale
            )
            pred = flow[0].permute(1, 2, 0).cpu().numpy()
            gt, valid = read_kitti_flow_png(gt_path)
            if pred.shape[:2] != gt.shape[:2]:
                pred = cv2.resize(pred, (gt.shape[1], gt.shape[0]), interpolation=cv2.INTER_LINEAR)
                # scale flow vectors with resize
                sx = gt.shape[1] / flow.shape[-1]
                sy = gt.shape[0] / flow.shape[-2]
                # already full-res from model typically; if resized, scale components
                if abs(sx - 1.0) > 1e-3 or abs(sy - 1.0) > 1e-3:
                    pred[..., 0] *= sx
                    pred[..., 1] *= sy
            fl, _, _ = fl_all(pred, gt, valid)
            epe = np.sqrt(((pred - gt) ** 2).sum(axis=-1))
            epe_mean = float(epe[valid].mean()) if valid.any() else 0.0
            fl_sum += fl
            epe_sum += epe_mean
            n_pairs += 1
            if n_pairs % 10 == 0:
                print(f"  progress pairs={n_pairs} running_fl_all={fl_sum/n_pairs:.3f}", flush=True)

    elapsed = time.perf_counter() - t0
    fl_mean = fl_sum / max(n_pairs, 1)
    epe_mean = epe_sum / max(n_pairs, 1)
    gate = fl_mean <= args.nvofa_medium_fl_all
    result = {
        "model": args.path or args.url,
        "cfg": args.cfg,
        "device": args.device,
        "pairs": n_pairs,
        "fl_all_pct": fl_mean,
        "epe": epe_mean,
        "seconds": elapsed,
        "nvofa_medium_fl_all_ref": args.nvofa_medium_fl_all,
        "gate_fl_all_le_nvofa_medium": "PASS" if gate else "FAIL",
    }
    print(json.dumps(result, indent=2))
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if n_pairs > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
