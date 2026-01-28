#!/usr/bin/env python3
"""Profile VDMS DataPrep throughput via pipeline manager and telemetry."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import requests
except ModuleNotFoundError as exc:  # pragma: no cover - dependency hint
    raise SystemExit(
        "Missing optional dependency 'requests'. Install it with 'pip install requests' before running the profiler."
    ) from exc


DEFAULT_PIPELINE_MANAGER_URL = os.getenv("PIPELINE_MANAGER_URL", "http://localhost:3001/manager")
DEFAULT_TELEMETRY_URL = os.getenv("VDMS_TELEMETRY_URL", "http://localhost:6016/v1/dataprep/telemetry")
_DEFAULT_VIDEO = (
    Path(__file__).resolve().parents[1] / "cli" / "resources" / "ceramic_store.mp4"
)


@dataclass
class ProfileArgs:
    pipeline_manager_url: str
    telemetry_url: str
    video_path: Path
    workers: List[int]
    batches: List[int]
    runs_per_combo: int
    poll_interval: float
    telemetry_timeout: float
    telemetry_limit: int
    upload_timeout: float
    processing_timeout: float
    output_path: Path
    tag_prefix: str


@dataclass
class ProfileResult:
    target_workers: int
    target_batch: int
    run_index: int
    tags: List[str]
    video_id: str
    request_id: Optional[str]
    pipeline_elapsed_seconds: float
    telemetry: Dict[str, Any]
    status: str

    @property
    def metrics_row(self) -> Dict[str, Any]:
        telemetry = self.telemetry or {}
        config = telemetry.get("config", {})
        throughput = telemetry.get("throughput", {})
        timestamps = telemetry.get("timestamps", {})
        counts = telemetry.get("counts", {})
        return {
            "target_workers": self.target_workers,
            "target_batch": self.target_batch,
            "actual_workers": config.get("sdk_parallel_workers"),
            "actual_batch": config.get("sdk_batch_size"),
            "embeddings_per_second": throughput.get("embeddings_per_second"),
            "wall_time_seconds": timestamps.get("wall_time_seconds"),
            "embeddings_stored": counts.get("embeddings_stored"),
            "frames_extracted": counts.get("frames_extracted"),
            "request_id": self.request_id,
            "video_id": self.video_id,
            "run": self.run_index,
            "status": self.status,
        }


def parse_args() -> ProfileArgs:
    parser = argparse.ArgumentParser(
        description="Profile VDMS DataPrep by sweeping worker and batch size combinations",
    )
    parser.add_argument(
        "--pipeline-manager-url",
        default=DEFAULT_PIPELINE_MANAGER_URL,
        help="Base URL for the pipeline manager service (default: %(default)s)",
    )
    parser.add_argument(
        "--telemetry-url",
        default=DEFAULT_TELEMETRY_URL,
        help="VDMS telemetry endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--video-path",
        type=Path,
        default=_DEFAULT_VIDEO,
        help="Video file to upload for profiling (default: %(default)s)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        nargs="+",
        required=True,
        help="List of MAX_PARALLEL_WORKERS values to test",
    )
    parser.add_argument(
        "--batches",
        type=int,
        nargs="+",
        required=True,
        help="List of EMBEDDING_BATCH_SIZE values to test",
    )
    parser.add_argument(
        "--runs-per-combo",
        type=int,
        default=1,
        help="Number of repeated runs for each worker/batch combination",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between telemetry polls",
    )
    parser.add_argument(
        "--telemetry-timeout",
        type=float,
        default=900.0,
        help="Maximum seconds to wait for telemetry per run",
    )
    parser.add_argument(
        "--telemetry-limit",
        type=int,
        default=100,
        help="Number of records to request from /telemetry",
    )
    parser.add_argument(
        "--upload-timeout",
        type=float,
        default=120.0,
        help="Timeout for the video upload request (seconds)",
    )
    parser.add_argument(
        "--processing-timeout",
        type=float,
        default=3600.0,
        help="Timeout for create-embeddings request (seconds)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to store the JSON report",
    )
    parser.add_argument(
        "--tag-prefix",
        default="profiling",
        help="Prefix added to video tags for easier telemetry filtering",
    )
    args = parser.parse_args()

    video_path = args.video_path.expanduser().resolve()
    if not video_path.exists():
        raise SystemExit(f"Video file not found: {video_path}")

    output_path = args.output
    if output_path is None:
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = Path.cwd() / f"vdms-profile-{stamp}.json"
    else:
        output_path = output_path.expanduser().resolve()

    return ProfileArgs(
        pipeline_manager_url=args.pipeline_manager_url,
        telemetry_url=args.telemetry_url,
        video_path=video_path,
        workers=args.workers,
        batches=args.batches,
        runs_per_combo=max(1, args.runs_per_combo),
        poll_interval=max(0.5, args.poll_interval),
        telemetry_timeout=max(args.poll_interval, args.telemetry_timeout),
        telemetry_limit=max(1, min(1000, args.telemetry_limit)),
        upload_timeout=max(30.0, args.upload_timeout),
        processing_timeout=max(60.0, args.processing_timeout),
        output_path=output_path,
        tag_prefix=args.tag_prefix.strip() or "profiling",
    )


def join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def human_tag(prefix: str, workers: int, batch: int, run_index: int) -> str:
    suffix = uuid.uuid4().hex[:8]
    return f"{prefix}-w{workers}-b{batch}-run{run_index}-{suffix}"


def upload_video(session: requests.Session, base_url: str, video_path: Path, tags: Iterable[str], timeout: float) -> str:
    url = join_url(base_url, "videos")
    data = {
        "tags": ",".join(tags),
        "name": video_path.name,
    }
    with video_path.open("rb") as handle:
        files = {"video": (video_path.name, handle, "video/mp4")}
        response = session.post(url, files=files, data=data, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    video_id = payload.get("videoId")
    if not video_id:
        raise RuntimeError(f"Pipeline manager did not return videoId: {payload}")
    return video_id


def create_search_embeddings(
    session: requests.Session,
    base_url: str,
    video_id: str,
    timeout: float,
) -> Dict[str, Any]:
    url = join_url(base_url, f"videos/search-embeddings/{video_id}")
    response = session.post(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def wait_for_telemetry(
    session: requests.Session,
    telemetry_url: str,
    video_id: str,
    expected_tag: str,
    poll_interval: float,
    timeout: float,
    limit: int,
) -> Dict[str, Any]:
    deadline = time.time() + timeout
    params = {"limit": limit}
    while time.time() < deadline:
        response = session.get(telemetry_url, params=params, timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("items", []):
            video = item.get("video") or {}
            tags = video.get("tags") or []
            if video.get("video_id") == video_id and expected_tag in tags:
                return item
        time.sleep(poll_interval)
    raise TimeoutError(
        f"Timed out waiting for telemetry entry (video_id={video_id}, tag={expected_tag})."
    )


def print_status(message: str) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {message}")


def format_table(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No successful runs captured."

    headers = [
        "target_workers",
        "target_batch",
        "actual_workers",
        "actual_batch",
        "embeddings_per_second",
        "wall_time_seconds",
        "embeddings_stored",
        "frames_extracted",
        "status",
    ]
    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            value = row.get(header)
            text = "-" if value is None else f"{value}" if not isinstance(value, float) else f"{value:.2f}"
            widths[header] = max(widths[header], len(text))

    def format_row(row: Dict[str, Any]) -> str:
        cells = []
        for header in headers:
            value = row.get(header)
            if isinstance(value, float):
                cell = f"{value:.2f}" if not value.is_integer() else f"{int(value)}"
            else:
                cell = "-" if value is None else str(value)
            cells.append(cell.ljust(widths[header]))
        return " | ".join(cells)

    header_line = " | ".join(header.ljust(widths[header]) for header in headers)
    divider = "-+-".join("-" * widths[header] for header in headers)
    body = "\n".join(format_row(row) for row in rows)
    return f"{header_line}\n{divider}\n{body}"


def run_profile(args: ProfileArgs) -> List[ProfileResult]:
    session = requests.Session()
    results: List[ProfileResult] = []

    for workers, batch in product(args.workers, args.batches):
        for run_index in range(1, args.runs_per_combo + 1):
            combo_label = f"workers={workers}, batch={batch}, run={run_index}"
            tag = human_tag(args.tag_prefix, workers, batch, run_index)
            tags = [args.tag_prefix, f"workers:{workers}", f"batch:{batch}", tag]

            print_status(f"[{combo_label}] Uploading video {args.video_path.name}")
            try:
                video_id = upload_video(
                    session,
                    args.pipeline_manager_url,
                    args.video_path,
                    tags,
                    timeout=args.upload_timeout,
                )
            except Exception as exc:
                print_status(f"[{combo_label}] Upload failed: {exc}")
                results.append(
                    ProfileResult(
                        target_workers=workers,
                        target_batch=batch,
                        run_index=run_index,
                        tags=tags,
                        video_id="",
                        request_id=None,
                        pipeline_elapsed_seconds=0.0,
                        telemetry={},
                        status=f"upload-failed: {exc}",
                    )
                )
                continue

            print_status(f"[{combo_label}] Triggering search embeddings for video {video_id}")
            started = time.time()
            try:
                _ = create_search_embeddings(
                    session,
                    args.pipeline_manager_url,
                    video_id,
                    timeout=args.processing_timeout,
                )
            except Exception as exc:
                print_status(f"[{combo_label}] Embedding request failed: {exc}")
                results.append(
                    ProfileResult(
                        target_workers=workers,
                        target_batch=batch,
                        run_index=run_index,
                        tags=tags,
                        video_id=video_id,
                        request_id=None,
                        pipeline_elapsed_seconds=time.time() - started,
                        telemetry={},
                        status=f"processing-failed: {exc}",
                    )
                )
                continue

            pipeline_elapsed = time.time() - started
            print_status(f"[{combo_label}] Waiting for telemetry (video_id={video_id})")
            try:
                telemetry = wait_for_telemetry(
                    session,
                    args.telemetry_url,
                    video_id,
                    tag,
                    args.poll_interval,
                    args.telemetry_timeout,
                    args.telemetry_limit,
                )
            except Exception as exc:
                print_status(f"[{combo_label}] Telemetry lookup failed: {exc}")
                results.append(
                    ProfileResult(
                        target_workers=workers,
                        target_batch=batch,
                        run_index=run_index,
                        tags=tags,
                        video_id=video_id,
                        request_id=None,
                        pipeline_elapsed_seconds=pipeline_elapsed,
                        telemetry={},
                        status=f"telemetry-failed: {exc}",
                    )
                )
                continue

            config = telemetry.get("config", {})
            request_id = telemetry.get("request_id")
            actual_workers = config.get("sdk_parallel_workers")
            actual_batch = config.get("sdk_batch_size")
            mismatch = actual_workers != workers or actual_batch != batch
            status = "ok" if not mismatch else "config-mismatch"
            throughput = telemetry.get("throughput", {})
            print_status(
                f"[{combo_label}] Completed: throughput={throughput.get('embeddings_per_second', 'n/a')} eps, "
                f"wall_time={telemetry.get('timestamps', {}).get('wall_time_seconds', 'n/a')}"
            )
            results.append(
                ProfileResult(
                    target_workers=workers,
                    target_batch=batch,
                    run_index=run_index,
                    tags=telemetry.get("video", {}).get("tags", tags),
                    video_id=video_id,
                    request_id=request_id,
                    pipeline_elapsed_seconds=pipeline_elapsed,
                    telemetry=telemetry,
                    status=status,
                )
            )

    return results


def save_report(results: List[ProfileResult], args: ProfileArgs) -> None:
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "pipeline_manager_url": args.pipeline_manager_url,
        "telemetry_url": args.telemetry_url,
        "video_path": str(args.video_path),
        "runs": [
            {
                "target_workers": result.target_workers,
                "target_batch": result.target_batch,
                "run_index": result.run_index,
                "tags": result.tags,
                "video_id": result.video_id,
                "request_id": result.request_id,
                "pipeline_elapsed_seconds": result.pipeline_elapsed_seconds,
                "status": result.status,
                "telemetry": result.telemetry,
            }
            for result in results
        ],
    }
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(payload, indent=2))
    print_status(f"Saved profiling report to {args.output_path}")


def main() -> None:
    args = parse_args()
    try:
        results = run_profile(args)
    except KeyboardInterrupt:
        print_status("Interrupted by user")
        return

    table_rows = [result.metrics_row for result in results if result.telemetry]
    print()
    print(format_table(table_rows))
    print()
    save_report(results, args)


if __name__ == "__main__":
    main()
