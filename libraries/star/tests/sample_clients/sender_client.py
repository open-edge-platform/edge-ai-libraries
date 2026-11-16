# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Sample sender client: reads local images and submits them to the encoder's
REST endpoint (POST /v1/streams/{stream_id}/frames), one raw JPEG body per
request, optionally throttled to a target frame rate.

Usage:
    python tests/sample_clients/sender_client.py \\
        --encoder-url http://localhost:8001 --stream-id demo-stream --fps 2

Run `tests/sample_data/fetch_sample_data.py` first if tests/sample_data/images/
is empty.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import httpx

DEFAULT_INPUT_DIR = Path(__file__).resolve().parents[1] / "sample_data" / "images"
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def sleep_to_enforce_fps(frame_started_at: float, fps: float) -> None:
    """Sleep long enough to enforce a target send rate; no-op when fps <= 0.

    Kept as a small standalone copy (matches
    semantic_img_comp.utils.rate_limit.sleep_to_enforce_fps) so this client
    image doesn't need the main src/ package, just httpx + pillow.
    """
    if fps is None or not math.isfinite(fps) or fps <= 0:
        return
    remaining = (1.0 / fps) - (time.perf_counter() - frame_started_at)
    if remaining > 0:
        time.sleep(remaining)


def iter_image_paths(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.iterdir() if p.suffix.lower() in VALID_EXTENSIONS and p.is_file())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder-url", default="http://localhost:8001")
    parser.add_argument("--stream-id", default="demo-stream")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--fps", type=float, default=1.0, help="Target send rate; 0 disables throttling")
    parser.add_argument("--loop", action="store_true", help="Loop over the input images forever")
    parser.add_argument("--client-id", default="sender-1")
    args = parser.parse_args(argv)

    if not args.input_dir.is_dir():
        print(f"Input directory does not exist: {args.input_dir}", file=sys.stderr)
        return 2

    paths = iter_image_paths(args.input_dir)
    if not paths:
        print(f"No images found in {args.input_dir}. Run fetch_sample_data.py first.", file=sys.stderr)
        return 2

    with httpx.Client(timeout=30.0) as client:
        client.put(f"{args.encoder_url}/v1/streams/{args.stream_id}")

        img_id = 0
        while True:
            for path in paths:
                img_id += 1
                t_start = time.perf_counter()
                jpeg_bytes = path.read_bytes()
                headers = {"Content-Type": "image/jpeg", "X-Client-Sent-At": f"{time.time():.6f}"}
                resp = client.post(
                    f"{args.encoder_url}/v1/streams/{args.stream_id}/frames",
                    params={"img_id": img_id},
                    content=jpeg_bytes,
                    headers=headers,
                )
                if resp.status_code >= 400:
                    print(f"[{args.client_id}] frame {img_id} failed: {resp.status_code} {resp.text}", file=sys.stderr)
                else:
                    print(f"[{args.client_id}] sent frame {img_id} ({path.name}): {resp.json()}")
                sleep_to_enforce_fps(t_start, args.fps)
            if not args.loop:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
