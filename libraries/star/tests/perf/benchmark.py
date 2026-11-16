# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Load/scaling benchmark for the encoder + decoder REST services.

Sweeps a list of concurrency levels (N simulated sender clients paired with N
simulated receiver clients, each against its own throwaway stream), submits
sample frames through the encoder, and measures:
  - submit latency: time for one POST /frames call to return (network + encode
    + forward-to-decoder)
  - end-to-end latency: time from a client stamping X-Client-Sent-At on submit
    to a receiver reading that same frame back off the decoder
  - achieved throughput (frames/sec)
  - error rate

Run `tests/sample_data/fetch_sample_data.py` first, then either:
  - against tests/docker-compose.yml (after `docker compose up`):
        python tests/perf/benchmark.py --encoder-url http://localhost:8001 \\
            --decoder-url http://localhost:8002 --concurrency-levels 1,2,4,8
  - against any other reachable encoder/decoder pair.

This is the tool for answering "how do the encoder/decoder scale with number of
clients" -- the services have no worker-pool knob to tune; each stream's
blocking work runs via asyncio.to_thread, so throughput scales with the number
of concurrently open streams.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

DEFAULT_SAMPLE_DIR = Path(__file__).resolve().parents[1] / "sample_data" / "images"
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}


@dataclass
class LevelResult:
    concurrency: int
    frames_submitted: int = 0
    frames_received: int = 0
    errors: int = 0
    duration_s: float = 0.0
    submit_latencies_ms: list[float] = field(default_factory=list)
    e2e_latencies_ms: list[float] = field(default_factory=list)
    input_bytes: int = 0
    payload_bytes: int = 0

    @property
    def throughput_fps(self) -> float:
        return self.frames_received / self.duration_s if self.duration_s > 0 else 0.0

    @property
    def comp_ratio(self) -> float:
        return self.input_bytes / self.payload_bytes if self.payload_bytes > 0 else 0.0


def _pct(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(pct / 100.0 * (len(ordered) - 1))))
    return ordered[idx]


async def _sender_worker(
    client: httpx.AsyncClient,
    encoder_url: str,
    stream_id: str,
    image_paths: list[Path],
    frames_per_sender: int,
    sender_index: int,
    result: LevelResult,
) -> None:
    for i in range(frames_per_sender):
        path = image_paths[(i + sender_index) % len(image_paths)]
        jpeg_bytes = path.read_bytes()
        headers = {"Content-Type": "image/jpeg", "X-Client-Sent-At": f"{time.time():.6f}"}
        t0 = time.perf_counter()
        try:
            resp = await client.post(
                f"{encoder_url}/v1/streams/{stream_id}/frames",
                params={"img_id": sender_index * 1_000_000 + i + 1},
                content=jpeg_bytes,
                headers=headers,
            )
            resp.raise_for_status()
            result.submit_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
            result.frames_submitted += 1
            payload_bytes = resp.json().get("payload_bytes")
            if payload_bytes:
                result.input_bytes += len(jpeg_bytes)
                result.payload_bytes += payload_bytes
        except httpx.HTTPError:
            result.errors += 1


async def _receiver_worker(
    client: httpx.AsyncClient,
    decoder_url: str,
    stream_id: str,
    consumer_id: str,
    target_frames: int,
    result: LevelResult,
    stop_event: asyncio.Event,
) -> None:
    received = 0
    while received < target_frames and not stop_event.is_set():
        try:
            resp = await client.get(
                f"{decoder_url}/v1/streams/{stream_id}/frames/next",
                params={"consumer_id": consumer_id, "wait_ms": 2000},
            )
        except httpx.HTTPError:
            result.errors += 1
            continue
        if resp.status_code == 204:
            continue
        sent_at = resp.headers.get("X-Client-Sent-At")
        if sent_at is not None:
            result.e2e_latencies_ms.append((time.time() - float(sent_at)) * 1000.0)
        received += 1
        result.frames_received += 1


async def run_level(
    encoder_url: str,
    decoder_url: str,
    concurrency: int,
    frames_per_sender: int,
    image_paths: list[Path],
    drain_timeout_s: float,
) -> LevelResult:
    result = LevelResult(concurrency=concurrency)
    stream_id = f"bench-{concurrency}-{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.put(f"{encoder_url}/v1/streams/{stream_id}")
        await client.put(f"{decoder_url}/v1/streams/{stream_id}")

        stop_event = asyncio.Event()
        t_start = time.perf_counter()

        senders = [
            _sender_worker(client, encoder_url, stream_id, image_paths, frames_per_sender, i, result)
            for i in range(concurrency)
        ]
        receivers = [
            _receiver_worker(
                client, decoder_url, stream_id, f"bench-consumer-{i}", frames_per_sender, result, stop_event
            )
            for i in range(concurrency)
        ]

        await asyncio.gather(*senders)
        try:
            await asyncio.wait_for(asyncio.gather(*receivers), timeout=drain_timeout_s)
        except asyncio.TimeoutError:
            stop_event.set()

        result.duration_s = time.perf_counter() - t_start

        await client.delete(f"{encoder_url}/v1/streams/{stream_id}")
        await client.delete(f"{decoder_url}/v1/streams/{stream_id}")

    return result


def _print_and_write(results: list[LevelResult], csv_path: Path | None) -> None:
    header = [
        "concurrency", "submitted", "received", "errors", "throughput_fps",
        "submit_p50_ms", "submit_p95_ms", "e2e_p50_ms", "e2e_p95_ms", "comp_ratio",
    ]
    rows = []
    for r in results:
        rows.append([
            r.concurrency, r.frames_submitted, r.frames_received, r.errors,
            round(r.throughput_fps, 2),
            round(_pct(r.submit_latencies_ms, 50) or 0.0, 1),
            round(_pct(r.submit_latencies_ms, 95) or 0.0, 1),
            round(_pct(r.e2e_latencies_ms, 50) or 0.0, 1),
            round(_pct(r.e2e_latencies_ms, 95) or 0.0, 1),
            f"{r.comp_ratio:.1f}x" if r.comp_ratio else "n/a",
        ])

    widths = [max(len(str(h)), *(len(str(row[i])) for row in rows)) for i, h in enumerate(header)]
    print("  ".join(h.ljust(w) for h, w in zip(header, widths)))
    for row in rows:
        print("  ".join(str(v).ljust(w) for v, w in zip(row, widths)))

    if csv_path is not None:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        print(f"\nWrote {csv_path}")


def _maybe_plot(results: list[LevelResult], plot_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping --plot", file=sys.stderr)
        return

    concurrencies = [r.concurrency for r in results]
    throughput = [r.throughput_fps for r in results]
    e2e_p50 = [_pct(r.e2e_latencies_ms, 50) or 0.0 for r in results]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    ax1.plot(concurrencies, throughput, marker="o")
    ax1.set_xlabel("Concurrency (senders = receivers)")
    ax1.set_ylabel("Throughput (frames/sec)")
    ax1.set_title("Throughput vs concurrency")
    ax1.grid(True)

    ax2.plot(concurrencies, e2e_p50, marker="o", color="tab:orange")
    ax2.set_xlabel("Concurrency (senders = receivers)")
    ax2.set_ylabel("End-to-end p50 latency (ms)")
    ax2.set_title("Latency vs concurrency")
    ax2.grid(True)

    fig.tight_layout()
    fig.savefig(plot_path)
    print(f"Wrote {plot_path}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder-url", default="http://localhost:8001")
    parser.add_argument("--decoder-url", default="http://localhost:8002")
    parser.add_argument("--sample-dir", type=Path, default=DEFAULT_SAMPLE_DIR)
    parser.add_argument(
        "--concurrency-levels", default="1,2,4,8",
        help="Comma-separated list of sender/receiver counts to sweep",
    )
    parser.add_argument("--frames-per-sender", type=int, default=20)
    parser.add_argument("--drain-timeout-s", type=float, default=30.0,
                         help="Max time to wait for receivers to catch up after senders finish")
    parser.add_argument("--csv", type=Path, default=None)
    parser.add_argument("--plot", type=Path, default=None)
    args = parser.parse_args(argv)

    image_paths = (
        sorted(p for p in args.sample_dir.iterdir() if p.suffix.lower() in VALID_EXTENSIONS)
        if args.sample_dir.exists() else []
    )
    if not image_paths:
        print(
            f"No sample images found in {args.sample_dir}. Run tests/sample_data/fetch_sample_data.py first.",
            file=sys.stderr,
        )
        return 2

    levels = [int(x) for x in args.concurrency_levels.split(",") if x.strip()]
    results = []
    for level in levels:
        print(f"\n=== concurrency={level} ===")
        result = asyncio.run(
            run_level(args.encoder_url, args.decoder_url, level, args.frames_per_sender, image_paths, args.drain_timeout_s)
        )
        results.append(result)

    _print_and_write(results, args.csv)
    if args.plot is not None:
        _maybe_plot(results, args.plot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
