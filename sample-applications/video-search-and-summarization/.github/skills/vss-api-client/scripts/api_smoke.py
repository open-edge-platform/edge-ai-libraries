#!/usr/bin/env python3
"""Small VSS REST smoke test.

Uses only the Python standard library. It checks health, optionally uploads a
video, starts a summary pipeline, polls the UI summary endpoint, and optionally
runs a one-off search query. It does not implement Socket.IO; use the event names
in SKILL.md/reference docs to subscribe from JS or a Socket.IO-capable client.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def join_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def request_json(method: str, url: str, body: object | None = None, timeout: int = 60) -> tuple[int, object | str]:
    data = None
    headers: dict[str, str] = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return resp.status, ""
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: object | str = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed


def multipart_upload(url: str, video_path: Path, tags: str | None, timeout: int = 300) -> tuple[int, object | str]:
    boundary = "----vss-smoke-" + uuid.uuid4().hex
    mime = mimetypes.guess_type(video_path.name)[0] or "application/octet-stream"
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode(),
            b"\r\n",
        ])

    def add_file(name: str, path: Path) -> None:
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            path.read_bytes(),
            b"\r\n",
        ])

    add_file("video", video_path)
    if tags:
        add_field("tags", tags)
    parts.append(f"--{boundary}--\r\n".encode())
    data = b"".join(parts)

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(data)),
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: object | str = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed


def print_step(name: str, status: int, payload: object | str) -> None:
    ok = 200 <= status < 300
    print(f"[{ 'OK' if ok else 'FAIL' }] {name}: HTTP {status}")
    if not ok:
        print(json.dumps(payload, indent=2) if not isinstance(payload, str) else payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test VSS Pipeline Manager API")
    parser.add_argument("--base", default=os.environ.get("VSS_BASE_URL", "http://localhost:12345/manager"), help="Pipeline Manager base URL; include /manager when using nginx")
    parser.add_argument("--video", default=os.environ.get("VSS_VIDEO"), help="MP4 path to upload; if omitted, upload/summary steps are skipped")
    parser.add_argument("--tags", default=os.environ.get("VSS_TAGS", "api-smoke"), help="Comma-separated upload/search tags")
    parser.add_argument("--title", default=os.environ.get("VSS_TITLE", "API smoke summary"))
    parser.add_argument("--polls", type=int, default=int(os.environ.get("VSS_POLLS", "20")), help="Summary poll attempts")
    parser.add_argument("--poll-interval", type=float, default=float(os.environ.get("VSS_POLL_INTERVAL", "5")), help="Seconds between polls")
    parser.add_argument("--search-query", default=os.environ.get("VSS_SEARCH_QUERY"), help="Optional one-off search query to run through /search/query")
    args = parser.parse_args()

    status, payload = request_json("GET", join_url(args.base, "/health"))
    print_step("health", status, payload)
    if status < 200 or status >= 300:
        return 1

    video_id = None
    if args.video:
        path = Path(args.video)
        if not path.is_file():
            print(f"[FAIL] video path not found: {path}", file=sys.stderr)
            return 2
        status, payload = multipart_upload(join_url(args.base, "/videos"), path, args.tags)
        print_step("upload video", status, payload)
        if not (200 <= status < 300) or not isinstance(payload, dict) or "videoId" not in payload:
            return 1
        video_id = str(payload["videoId"])

        summary_body = {
            "videoId": video_id,
            "title": args.title,
            "sampling": {"chunkDuration": 30, "samplingFrame": 4, "frameOverlap": 1, "multiFrame": 5},
            "evam": {"evamPipeline": "video_ingestion"},
        }
        status, payload = request_json("POST", join_url(args.base, "/summary"), summary_body, timeout=120)
        print_step("start summary", status, payload)
        if not (200 <= status < 300) or not isinstance(payload, dict) or "summaryPipelineId" not in payload:
            return 1
        state_id = str(payload["summaryPipelineId"])
        print(f"[INFO] Socket.IO room/state ID: {state_id}; connect to app origin with path /ws/ and emit join")

        for attempt in range(1, args.polls + 1):
            status, summary = request_json("GET", join_url(args.base, f"/summary/{urllib.parse.quote(state_id)}"), timeout=60)
            if status < 200 or status >= 300:
                print_step(f"poll summary attempt {attempt}", status, summary)
                return 1
            if isinstance(summary, dict):
                video_status = summary.get("videoSummaryStatus")
                text = summary.get("summary") or ""
                print(f"[OK] poll {attempt}: videoSummaryStatus={video_status!r}, summary_chars={len(text)}")
                if video_status == "complete" or text:
                    print("[OK] summary available")
                    break
            else:
                print(f"[OK] poll {attempt}: {summary!r}")
            time.sleep(args.poll_interval)
        else:
            print("[WARN] summary not complete before poll limit")

    if args.search_query:
        body = {"query": args.search_query, "tags": args.tags, "timeFilter": {"value": 24, "unit": "hours"}}
        status, payload = request_json("POST", join_url(args.base, "/search/query"), body, timeout=180)
        print_step("one-off search", status, payload)
        if not (200 <= status < 300):
            return 1

    print("[DONE] VSS API smoke finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
