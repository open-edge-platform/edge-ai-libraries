#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""SEA-RAFT OpenVINO wall timing on CPU/GPU (Series 2 iGPU reporting)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import openvino as ov


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True, help="OpenVINO .xml")
    ap.add_argument("--device", type=str, default="GPU")
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--iters", type=int, default=50)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args()

    core = ov.Core()
    devices = list(core.available_devices)
    if args.device not in devices:
        raise SystemExit(f"device {args.device} not in {devices}")

    model = core.read_model(str(args.model))
    compiled = core.compile_model(model, args.device)
    req = compiled.create_infer_request()
    inp0 = compiled.input(0)
    shape = list(inp0.shape)
    # NCHW
    n, c, h, w = [int(x) for x in shape]
    prev = np.random.randint(0, 255, (n, c, h, w)).astype(np.float32)
    nxt = np.random.randint(0, 255, (n, c, h, w)).astype(np.float32)

    for _ in range(args.warmup):
        req.infer({0: prev, 1: nxt})

    # sync wall
    t0 = time.perf_counter()
    for _ in range(args.iters):
        req.infer({0: prev, 1: nxt})
    t1 = time.perf_counter()
    ms = 1000.0 * (t1 - t0) / args.iters
    fps = 1000.0 / ms

    # device name
    try:
        full = str(core.get_property(args.device, "FULL_DEVICE_NAME"))
    except Exception:
        full = args.device

    result = {
        "model": str(args.model),
        "device": args.device,
        "device_name": full,
        "input_nchw": [n, c, h, w],
        "warmup": args.warmup,
        "iters": args.iters,
        "ms_per_pair": ms,
        "fps": fps,
        "note": "OpenVINO sync infer wall; fixed-shape IR; not including host decode/resize",
    }
    print(json.dumps(result, indent=2))
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
