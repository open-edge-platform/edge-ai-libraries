# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Benchmark prepared ViCLIP-B/L and Cosmos-224p OpenVINO video embeddings.

Read MSR-VTT test JSON directly, or JSONL rows with media_path and captions.
Rank by exact cosine similarity, crediting each video with its best caption rank.
Models run in separate processes; no downloads, exports or engine API calls.
"""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time


ENGINE_ROOT = Path(__file__).resolve().parents[3]
MODELS = {
    "viclip-b": ("OpenGVLab/ViCLIP-B-16-hf", "viclip", 512, 32, "clip_bpe"),
    "viclip-l": ("OpenGVLab/ViCLIP-L-14-hf", "viclip", 768, 32, "clip_bpe"),
    "cosmos-224p": ("nvidia/Cosmos-Embed1-224p", "cosmos", 256, 128, "bert"),
}
CSV_FIELDS = (
    "model", "precision", "items", "captions", "dimension", "parameters",
    "R@1", "R@5", "R@10", "MedR", "MeanR", "total duration (s)", "avg query (s)",
)


def dataset_rows(path):
    """Normalize downloaded MSR-VTT annotations in memory; keep JSONL support."""
    if path.suffix.lower() == ".json":
        annotations = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(annotations, list):
            raise ValueError("MSR-VTT JSON must contain a list of video/caption annotations")
        grouped = {}
        for index, entry in enumerate(annotations, 1):
            if not isinstance(entry, dict):
                raise ValueError(f"MSR-VTT annotation {index}: expected an object")
            video_id, caption = entry.get("video_id"), entry.get("caption")
            if (not isinstance(video_id, str) or not video_id.strip()
                    or not isinstance(caption, str) or not caption.strip()):
                raise ValueError(f"MSR-VTT annotation {index}: video_id and caption required")
            filename = entry.get("video", f"{video_id}.mp4")
            if (not isinstance(filename, str) or not filename
                    or Path(filename).name != filename):
                raise ValueError(f"MSR-VTT annotation {index}: expected a video filename")
            media = str(path.parent / "video" / filename)
            item = grouped.setdefault(video_id, {"media_path": media, "captions": []})
            if item["media_path"] != media:
                raise ValueError(f"MSR-VTT annotation {index}: conflicting video for {video_id}")
            item["captions"].append(caption)
        yield from enumerate((grouped[key] for key in sorted(grouped)), 1)
        return
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if line.strip():
                yield line_number, json.loads(line)


def read_manifest(path, limit):
    items, seen = [], set()
    for line_number, row in dataset_rows(path):
        if not isinstance(row, dict):
            raise ValueError(f"Dataset row {line_number}: expected an object")
        media, captions = row.get("media_path"), row.get("captions")
        if (not isinstance(media, str) or not media.strip()
                or not isinstance(captions, list) or not captions
                or any(not isinstance(text, str) or not text.strip() for text in captions)):
            raise ValueError(f"Dataset row {line_number}: media_path and nonempty captions required")
        video = Path(media).expanduser()
        video = (video if video.is_absolute() else path.parent / video).resolve()
        if not video.is_file():
            raise ValueError(f"Dataset row {line_number}: video not found: {video}")
        if video in seen:
            raise ValueError(f"Dataset row {line_number}: duplicate video: {video}")
        seen.add(video)
        items.append({"media_path": str(video), "captions": captions})
        if limit and len(items) >= limit:
            break
    if not items:
        raise ValueError("Manifest contains no videos")
    return items


def check_package(name, path):
    """File-only preflight, including the tokenizer; never load model tensors."""
    marker = path / "video_embedding.json"
    if marker.is_symlink() or not marker.is_file():
        raise ValueError(f"{name}: missing {marker}; run scripts/prepare-models.sh {name}")
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    model_id, preprocessing, dimension, context, tokenizer = MODELS[name]
    expected = {
        "format": 1, "name": name, "model_id": model_id, "frames": 8, "image_size": 224,
        "preprocessing": preprocessing, "dimension": dimension,
        "context_length": context, "tokenizer_type": tokenizer,
    }
    if not isinstance(metadata, dict) or any(metadata.get(k) != v for k, v in expected.items()):
        raise ValueError(f"{name}: package identity/format/geometry mismatch: {marker}")
    precision = metadata.get("precision")
    if precision not in ("fp16", "fp32"):
        raise ValueError(f"{name}: invalid package precision")
    suffix = path.name.rsplit("-", 1)[-1]
    if suffix in ("fp16", "fp32") and suffix != precision:
        raise ValueError(f"{name}: directory precision conflicts with manifest")
    count = metadata.get("parameter_count")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError(f"{name}: missing positive parameter_count")
    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"video_encoder", "text_encoder", "tokenizer"}:
        raise ValueError(f"{name}: package must declare both encoders and tokenizer")
    required = {"tokenizer_config.json", "special_tokens_map.json"}
    required.update(("vocab.txt",) if name == "cosmos-224p" else ("vocab.json", "merges.txt"))
    for tower in ("video_encoder", "text_encoder"):
        if artifacts[tower] != [f"{tower}.xml", f"{tower}.bin"]:
            raise ValueError(f"{name}: invalid {tower} artifacts")
    for files in artifacts.values():
        if not isinstance(files, list) or not files or any(not isinstance(f, str) for f in files):
            raise ValueError(f"{name}: invalid artifact list")
        required.update(files)
    for filename in required:
        artifact = path / filename
        if (not filename or Path(filename).name != filename or artifact.is_symlink()
                or not artifact.is_file() or artifact.stat().st_size == 0):
            raise ValueError(f"{name}: missing, empty or unsafe artifact: {filename}")
    return metadata


def load_model(name, path, device):
    """Use the production encoders and preprocessing for every model."""
    sys.path.insert(0, str(ENGINE_ROOT / "src"))
    if name == "cosmos-224p":
        from inference.multimodal.cosmos_openvino import CosmosOpenVINOEmbedding

        return CosmosOpenVINOEmbedding(str(path), device=device, family="cosmos")
    from inference.multimodal.viclip_openvino import ViClipOpenVINOEmbedding

    return ViClipOpenVINOEmbedding(str(path), device=device, family="viclip")


def normalized(values, rows, dimension):
    import numpy as np

    matrix = np.asarray(values, dtype=np.float32)
    if matrix.shape != (rows, dimension) or not np.isfinite(matrix).all():
        raise ValueError(f"Invalid embedding shape/values: {matrix.shape}, expected {(rows, dimension)}")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms <= 1e-12):
        raise ValueError("Model returned a zero embedding")
    return matrix / norms


def evaluate(name, args, items, path, metadata):
    import numpy as np

    started = time.perf_counter()
    model = load_model(name, path, args.device)
    from core.multimodal.frames import sample_frames

    load_seconds = time.perf_counter() - started
    videos = []
    phase = time.perf_counter()
    for index, item in enumerate(items, 1):
        try:
            frames = sample_frames(item["media_path"], 8)
            videos.append(model.get_video_embedding(frames))
        except Exception as exc:
            raise RuntimeError(f"{name}: video {index} ({item['media_path']}): {exc}") from exc
        if index % 25 == 0 or index == len(items):
            print(f"{name}: videos {index}/{len(items)}", flush=True)
    video_vectors = normalized(videos, len(items), metadata["dimension"])
    video_seconds = time.perf_counter() - phase
    texts, owners = [], []
    for index, item in enumerate(items):
        texts.extend(item["captions"])
        owners.extend([index] * len(item["captions"]))
    phase = time.perf_counter()
    text_vectors = []
    for offset in range(0, len(texts), args.text_batch_size):
        text_vectors.extend(model.get_text_embeddings(texts[offset:offset + args.text_batch_size]))
    text_vectors = normalized(text_vectors, len(texts), metadata["dimension"])
    text_seconds = time.perf_counter() - phase
    phase = time.perf_counter()
    ranks = np.full(len(items), len(items) + 1, dtype=np.int64)
    for offset in range(0, len(texts), args.text_batch_size):
        similarities = text_vectors[offset:offset + args.text_batch_size] @ video_vectors.T
        targets = np.asarray(owners[offset:offset + args.text_batch_size])
        # Count all ties against the correct video, including its own score:
        # this is 1 + the number of OTHER videos scoring >= the target.
        correct = similarities[np.arange(len(targets)), targets]
        caption_ranks = (similarities >= correct[:, None]).sum(axis=1)
        np.minimum.at(ranks, targets, caption_ranks)
    scores = {
        "queries": len(items),
        "recall": {str(k): float(np.mean(ranks <= k)) for k in (1, 5, 10)},
        "median_rank": float(np.median(ranks)), "mean_rank": float(np.mean(ranks)),
    }
    ranking_seconds = time.perf_counter() - phase
    return {
        "exact": {"item": scores},
        "metadata": {
            "model": name, "model_path": str(path), "runtime": "openvino", "device": args.device,
            "precision": metadata["precision"], "execution_precision_hint": model.execution_precision,
            "items": len(items), "captions": len(texts), "dimension": model.dimension,
            "input_size": "8x224x224", "parameter_count": metadata["parameter_count"],
            "manifest": str(args.manifest),
            "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            "limit": args.limit, "text_batch_size": args.text_batch_size,
            "protocol": "exact cosine; best caption per video; ties against target",
            "load_seconds": load_seconds, "video_seconds": video_seconds,
            "text_seconds": text_seconds, "ranking_seconds": ranking_seconds,
            "total_seconds": time.perf_counter() - started,
        },
    }


def write_json(path, value):
    with path.open("x", encoding="utf-8") as target:
        json.dump(value, target, indent=2, ensure_ascii=False, allow_nan=False)
        target.write("\n")


def worker_command(name, path, args):
    return [
        sys.executable, "-B", "-u", str(Path(__file__).resolve()), "--worker",
        "--models", name, f"--{name}-model-path", str(path),
        "--manifest", str(args.manifest), "--device", args.device,
        "--text-batch-size", str(args.text_batch_size), "--limit", str(args.limit),
        "--out-dir", str(args.out_dir),
    ]


def run_models(args, packages):
    """One subprocess per model so all model/device memory is released on exit."""
    environment = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    results = {}
    with (args.out_dir / "results.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        handle.flush()
        for name, (path, _) in packages.items():
            print(f"\n=== {name} ===", flush=True)
            started_at = datetime.now(timezone.utc).isoformat()
            started = time.perf_counter()
            with (args.out_dir / f"{name}.log").open("x", encoding="utf-8") as log:
                with subprocess.Popen(worker_command(name, path, args), stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, env=environment) as process:
                    try:
                        for line in process.stdout:
                            print(line, end="", flush=True)
                            log.write(line)
                        status = process.wait()
                    except BaseException:
                        process.terminate()
                        process.wait()
                        raise
            wall_seconds = time.perf_counter() - started
            if status:
                write_json(args.out_dir / f"{name}.error.json", {
                    "model": name, "returncode": status, "wall_seconds": wall_seconds,
                    "started_at_utc": started_at,
                })
                raise RuntimeError(f"{name} failed; see {args.out_dir / (name + '.log')}; earlier results retained")
            result_path = args.out_dir / f"{name}.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            scores, metadata = result["exact"]["item"], result["metadata"]
            metadata.update(wall_seconds=wall_seconds, started_at_utc=started_at)
            row = {
                "model": name, "precision": metadata["precision"], "items": metadata["items"],
                "captions": metadata["captions"], "dimension": metadata["dimension"],
                "parameters": metadata["parameter_count"],
                **{f"R@{k}": round(scores["recall"][str(k)] * 100, 4) for k in (1, 5, 10)},
                "MedR": scores["median_rank"], "MeanR": scores["mean_rank"],
                "total duration (s)": round(wall_seconds, 6),
                "avg query (s)": round(wall_seconds / metadata["captions"], 6),
            }
            writer.writerow(row)
            handle.flush()
            results[name] = result
            print(f"{name}: R@1={row['R@1']:.2f}% R@5={row['R@5']:.2f}% R@10={row['R@10']:.2f}%", flush=True)
    write_json(args.out_dir / "summary.json", results)
    print(f"\nResults: {args.out_dir}\nCSV: {args.out_dir / 'results.csv'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Downloaded MSR-VTT test JSON or video/caption JSONL manifest")
    parser.add_argument("--models", nargs="+", choices=tuple(MODELS), default=["viclip-b"])
    model_root = os.getenv("ENGINE_MODEL_ROOT_PATH") or str(
        Path(os.getenv("ENGINE_WORKSPACE") or ENGINE_ROOT / "workspace") / "models")
    parser.add_argument("--model-root", type=Path, default=model_root, help="Prepared package root (default: engine workspace/models)")
    for name in MODELS:
        parser.add_argument(f"--{name}-model-path", type=Path, help=f"Override <model-root>/{name}-fp16 (also accepts fp32 packages)")
    parser.add_argument("--device", default="CPU", help="OpenVINO device, e.g. CPU or GPU.0 (default: CPU)")
    parser.add_argument("--text-batch-size", type=int, default=32)
    parser.add_argument("--limit", type=int, default=0, help="First N videos; 0 evaluates the full manifest")
    parser.add_argument("--out-dir", type=Path, default=Path("./results/video-embeddings"), help="New/empty results directory")
    parser.add_argument("--dry-run", action="store_true", help="Validate files and print commands; no inference/output files")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.limit < 0 or args.text_batch_size <= 0:
        parser.error("--limit must be nonnegative and --text-batch-size positive")
    args.manifest = args.manifest.expanduser().resolve()
    args.model_root = args.model_root.expanduser().resolve()
    args.out_dir = args.out_dir.expanduser().resolve()
    args.models = list(dict.fromkeys(args.models))
    if args.worker and (len(args.models) != 1 or args.dry_run):
        parser.error("Internal worker requires exactly one model and no --dry-run")
    items = read_manifest(args.manifest, args.limit)
    packages = {}
    for name in args.models:
        override = getattr(args, name.replace("-", "_") + "_model_path")
        path = (override or args.model_root / f"{name}-fp16").expanduser().resolve()
        metadata = check_package(name, path)
        packages[name] = (path, metadata)
        print(f"{name}: {path} ({metadata['precision']}, {metadata['dimension']} dimensions)", flush=True)
    print(f"Dataset: {len(items)} videos, {sum(len(item['captions']) for item in items)} captions", flush=True)
    if args.dry_run:
        for name, (path, _) in packages.items():
            print(shlex.join(worker_command(name, path, args)))
        return 0
    if args.worker:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        name = args.models[0]
        path, metadata = packages[name]
        result = evaluate(name, args, items, path, metadata)
        write_json(args.out_dir / f"{name}.json", result)
    else:
        if args.out_dir.exists() and (not args.out_dir.is_dir() or any(args.out_dir.iterdir())):
            parser.error("--out-dir must be new or empty; existing results are never overwritten")
        args.out_dir.mkdir(parents=True, exist_ok=True)
        run_models(args, packages)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, ImportError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)