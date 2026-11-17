# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Sample receiver client: polls the decoder's REST endpoint
(GET /v1/streams/{stream_id}/frames/next) and saves each decoded JPEG to disk.
Any number of receivers can run this against the same --stream-id with distinct
--consumer-id values; each gets every frame independently (pub/sub-style fan-out).

Usage:
    python tests/sample_clients/receiver_client.py \\
        --decoder-url http://localhost:8002 --stream-id demo-stream --consumer-id receiver-1
"""
from __future__ import annotations

import argparse
import socket
import sys
import time
import uuid
from pathlib import Path

import httpx

# Default consumer_id must be unique per process: with `docker compose up
# --scale receiver=N`, every replica runs this same command, so a fixed
# default would make all replicas share one cursor instead of each
# independently reading every frame (the fan-out behavior the demo is meant
# to show). Container hostname is unique per replica under compose; the uuid
# suffix keeps repeated bare-metal runs from colliding too.
_DEFAULT_CONSUMER_ID = f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decoder-url", default="http://localhost:8002")
    parser.add_argument("--stream-id", default="demo-stream")
    parser.add_argument("--consumer-id", default=_DEFAULT_CONSUMER_ID)
    parser.add_argument("--output-dir", type=Path, default=Path("./received"))
    parser.add_argument("--wait-ms", type=int, default=5000, help="Long-poll wait per request, capped at 30000")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after this many frames (0 = run forever)")
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=args.wait_ms / 1000.0 + 10.0) as client:
        client.put(f"{args.decoder_url}/v1/streams/{args.stream_id}")

        received = 0
        while args.max_frames <= 0 or received < args.max_frames:
            resp = client.get(
                f"{args.decoder_url}/v1/streams/{args.stream_id}/frames/next",
                params={"consumer_id": args.consumer_id, "wait_ms": args.wait_ms},
            )
            if resp.status_code == 204:
                continue
            resp.raise_for_status()

            frame_seq = resp.headers.get("X-Frame-Seq", "unknown")
            out_path = args.output_dir / f"frame_{frame_seq}.jpeg"
            out_path.write_bytes(resp.content)
            received += 1

            sent_at = resp.headers.get("X-Client-Sent-At")
            latency_ms = (time.time() - float(sent_at)) * 1000.0 if sent_at is not None else None
            print(f"[{args.consumer_id}] received frame {frame_seq} -> {out_path} (latency_ms={latency_ms})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
