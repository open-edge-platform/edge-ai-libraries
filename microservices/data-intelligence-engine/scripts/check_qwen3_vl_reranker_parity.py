#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Compare an exported OV reranker against the official reference implementation.

Input JSONL rows: {"query": "...", "target": "audio|image|video",
"text": "..."} for audio, or "path": "/local/file" for image/video.
Rows with the same query and target form one ranking comparison. This script is offline:
it loads the official PyTorch checkpoint solely as a P0 validation oracle.
"""

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _reference(source, frames):
    import torch

    script = source / "scripts" / "qwen3_vl_reranker.py"
    if not script.is_file():
        raise FileNotFoundError(f"official reference script missing: {script}")
    spec = importlib.util.spec_from_file_location("official_qwen3_vl_reranker", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reference = module.Qwen3VLReranker(
        str(source), num_frames=frames, max_frames=frames,
        dtype=torch.float16,
    )
    # The published script defines sample_frames at module scope but calls it
    # as self._sample_frames for list-valued videos. Bind that exact function.
    reference._sample_frames = module.sample_frames
    return reference


def _document(row, frames_count):
    target = row["target"]
    if target == "audio":
        return {"text": row["text"]}
    if target == "image":
        from PIL import Image

        with Image.open(row["path"]) as image:
            return {"image": image.convert("RGB")}
    if target == "video":
        from core.multimodal.frames import sample_frames
        from inference.multimodal.qwen3_vl_reranker_inputs import pad_frames

        return {"video": pad_frames(sample_frames(row["path"], frames_count), frames_count)}
    raise ValueError(f"unsupported fixture target: {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="official HF checkpoint directory")
    parser.add_argument("--ov", type=Path, required=True, help="converted OV package directory")
    parser.add_argument("--fixtures", type=Path, required=True, help="frozen JSONL pairs")
    parser.add_argument("--device", default="CPU")
    parser.add_argument("--tolerance", type=float, default=0.02)
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--reference-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.tolerance < 0 or args.frames < 1:
        parser.error("tolerance must be non-negative and frames must be positive")

    prepared = []
    for line in args.fixtures.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        prepared.append((row, _document(row, args.frames)))
    if not prepared:
        parser.error("fixture file is empty")

    if args.reference_output is not None:
        reference = _reference(args.source, args.frames)
        expected_scores = []
        for index, (row, document) in enumerate(prepared, 1):
            score = float(reference.process({
                "query": {"text": row["query"]}, "documents": [document],
            })[0])
            expected_scores.append(score)
            print(f"Reference {index}/{len(prepared)}: {row['target']} {score:.6f}", flush=True)
        args.reference_output.write_text(json.dumps(expected_scores))
        return

    # Exit the PyTorch process before OpenVINO compiles its multi-GB IRs. A
    # Python gc.collect() cannot guarantee native allocations are released.
    with tempfile.TemporaryDirectory(prefix="qwen3vl-parity-") as temporary:
        scores_path = Path(temporary) / "scores.json"
        subprocess.run([
            sys.executable, str(Path(__file__).resolve()),
            "--source", str(args.source), "--ov", str(args.ov),
            "--fixtures", str(args.fixtures), "--frames", str(args.frames),
            "--reference-output", str(scores_path),
        ], check=True)
        expected_scores = json.loads(scores_path.read_text())
    from inference.multimodal.qwen3_vl_reranker_ov import OpenVINOVLReranking

    ov_model = OpenVINOVLReranking(str(args.ov), device=args.device)
    rankings = defaultdict(list)
    max_error = 0.0
    for (row, document), expected in zip(prepared, expected_scores):
        query = row["query"]
        observed = float(ov_model.score(query, document))
        error = abs(observed - expected)
        max_error = max(max_error, error)
        rankings[(query, row["target"])].append((expected, observed))
        print(json.dumps({"query": query, "target": row["target"],
                          "reference": expected, "openvino": observed,
                          "absolute_error": error}, ensure_ascii=False))
    rank_ok = all(
        sorted(range(len(scores)), key=lambda i: scores[i][0], reverse=True)
        == sorted(range(len(scores)), key=lambda i: scores[i][1], reverse=True)
        for scores in rankings.values()
    )
    print(json.dumps({"pairs": len(prepared), "max_absolute_error": max_error,
                      "same_ranking": rank_ok, "tolerance": args.tolerance}))
    if max_error > args.tolerance or not rank_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
