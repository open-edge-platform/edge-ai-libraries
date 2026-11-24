#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Forwards the Inference Router's JSONL telemetry as spans to SQLite or an OTLP/HTTP collector.

The Router has no OTLP exporter, only a `file` backend that appends one JSON event per line.
This daemon tails that file (offset checkpoint, rotation and truncation aware) and turns each
event into a span: `request_completed` becomes the root span of a trace keyed by `request_id`,
the other event types become its children. Spans are built after the request finished, so the
latency is taken from the event. Standard library only.
"""

import argparse
import hashlib
import json
import os
import signal
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CHUNK = 1 << 20
MAX_VALUE = 2000
PREVIEW = 200
MAX_DEPTH = 3
BATCH = 200
HEAD_BYTES = 256
GATED_KEYS = {"metadata", "details"}
SKIP_KEYS = {"event_type", "timestamp", "request_id", "provider_name", "final_model",
             "total_input_tokens", "total_output_tokens"}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
SERVICE = "inference-router"

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
    "ts INTEGER NOT NULL, data TEXT NOT NULL, trace_id TEXT, span_id TEXT, parent_span_id TEXT, "
    "session_id TEXT, name TEXT, status TEXT, start_ns INTEGER, end_ns INTEGER, duration_ms REAL, "
    "level INTEGER, logger TEXT, value REAL)"
)


class Transient(Exception):
    """The sink could not take the batch now; it is retried."""


class Fatal(Exception):
    """The checkpoint cannot be saved; continuing would re-send spans on every poll."""


def log(message):
    print(f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} {message}", file=sys.stderr, flush=True)


# --- event -> span ---------------------------------------------------------

def hid(*parts, n):
    return hashlib.sha256("\0".join(parts).encode("utf-8", "replace")).hexdigest()[:n]


def to_ns(value):
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return time.time_ns()
    # The Router writes naive timestamps; its container runs in UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = dt - EPOCH
    return (delta.days * 86400 + delta.seconds) * 10**9 + delta.microseconds * 1000


def number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def flatten(prefix, value, out, limit, depth=0):
    if value is None:
        return
    if isinstance(value, dict):
        if depth >= MAX_DEPTH:
            out[prefix] = json.dumps(value, default=str)[:limit]
            return
        for key, item in value.items():
            flatten(f"{prefix}.{key}", item, out, limit, depth + 1)
    elif isinstance(value, (list, tuple)):
        out[prefix] = json.dumps(value, default=str)[:limit]
    elif isinstance(value, str):
        out[prefix] = value[:limit]
    elif isinstance(value, (bool, int, float)):
        out[prefix] = value


def make_span(event, raw, content, offset=0):
    kind = str(event.get("event_type") or "event")
    request_id = event.get("request_id")
    line_id = hashlib.sha256(raw).hexdigest()
    end = to_ns(event.get("timestamp"))
    is_root = kind == "request_completed"
    if is_root:
        duration = number(event.get("total_latency_ms")) or 0.0
        name = "inference-router.request"
        span_id = hid("root", request_id or line_id, n=16)
        parent = ""
    else:
        duration = number(event.get("duration_ms")) or number(event.get("latency_ms")) or 0.0
        name = f"inference-router.{kind}"
        span_id = hid("span", line_id, str(offset), n=16)
        parent = hid("root", request_id, n=16) if request_id else ""
    attrs = {}
    if request_id:
        attrs["ir.request_id"] = str(request_id)[:MAX_VALUE]
    if is_root:
        models = event.get("models_used") or []
        attrs["gen_ai.system"] = str(event.get("provider_name") or "unknown")
        attrs["gen_ai.request.model"] = str(event.get("final_model") or (models[0] if models else ""))
        attrs["gen_ai.usage.input_tokens"] = event.get("total_input_tokens") or 0
        attrs["gen_ai.usage.output_tokens"] = event.get("total_output_tokens") or 0
    limit = PREVIEW if content == "preview" else MAX_VALUE
    for key, value in event.items():
        if key in SKIP_KEYS:
            continue
        if key in GATED_KEYS:
            if content == "off":
                continue
            flatten(f"ir.{key}", value, attrs, limit)
        else:
            flatten(f"ir.{key}", value, attrs, MAX_VALUE)
    failed = event.get("success") is False
    return {
        "trace_id": hid("trace", request_id or line_id, n=32),
        "span_id": span_id,
        "parent": parent,
        "name": name,
        "start": end - int(duration * 1e6),
        "end": end,
        "error": failed,
        "root": is_root,
        "attrs": attrs,
    }


# --- sinks -----------------------------------------------------------------

class SqliteSink:
    def __init__(self, path, max_rows):
        self.max_rows, self.inserted = max_rows, 0
        os.umask(0o077)
        self.con = sqlite3.connect(path, timeout=10)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute(SCHEMA)
        # Stores written before span ids were unique may hold replayed duplicates; keep the first of each.
        self.con.execute(
            "DELETE FROM events WHERE kind = 'span' AND seq NOT IN "
            "(SELECT MIN(seq) FROM events WHERE kind = 'span' GROUP BY trace_id, span_id)")
        self.con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS events_span_ids ON events (trace_id, span_id) WHERE kind = 'span'")
        self.con.commit()

    def send(self, spans):
        rows = [(
            s["end"], json.dumps(s["attrs"], default=str), s["trace_id"], s["span_id"], s["parent"] or None,
            None, s["name"], "ERROR" if s["error"] else "OK", s["start"], s["end"],
            max(s["end"] - s["start"], 0) / 1e6,
        ) for s in spans]
        try:
            self.con.executemany(
                "INSERT OR IGNORE INTO events (kind, ts, data, trace_id, span_id, parent_span_id, session_id, name, status, "
                "start_ns, end_ns, duration_ms) VALUES ('span', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            self.inserted += len(rows)
            if self.max_rows and self.inserted >= 500:
                self.inserted = 0
                self.con.execute("DELETE FROM events WHERE seq <= (SELECT MAX(seq) FROM events) - ?", (self.max_rows,))
            self.con.commit()
        except sqlite3.Error as exc:
            self.con.rollback()
            raise Transient(f"sqlite: {exc}")

    def close(self):
        try:
            self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            self.con.close()


def _attr(key, value):
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)}}


class OtlpSink:
    def __init__(self, endpoint):
        parts = urllib.parse.urlsplit(endpoint.rstrip("/"))
        # A bare collector URL gets the standard path; an explicit path is used as given.
        self.url = endpoint.rstrip("/") if parts.path else endpoint.rstrip("/") + "/v1/traces"
        # Internal collectors are reached directly, never through a corporate proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def send(self, spans):
        for i in range(0, len(spans), BATCH):
            self._post(spans[i:i + BATCH])

    def _post(self, spans):
        body = json.dumps({"resourceSpans": [{
            "resource": {"attributes": [_attr("service.name", SERVICE)]},
            "scopeSpans": [{"scope": {"name": "agent-harness-install.router-bridge"}, "spans": [{
                "traceId": s["trace_id"],
                "spanId": s["span_id"],
                **({"parentSpanId": s["parent"]} if s["parent"] else {}),
                "name": s["name"],
                "kind": 2 if s["root"] else 1,
                "startTimeUnixNano": str(s["start"]),
                "endTimeUnixNano": str(s["end"]),
                "attributes": [_attr(k, v) for k, v in s["attrs"].items()],
                "status": {"code": 2 if s["error"] else 1},
            } for s in spans]}],
        }]}).encode()
        request = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=10) as reply:
                reply.read()
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                # A batch the collector rejects will never be accepted; retrying would block the tail.
                log(f"collector rejected {len(spans)} spans with HTTP {exc.code}; dropped")
                return
            raise Transient(f"HTTP {exc.code} from {self.url}")
        except (urllib.error.URLError, OSError) as exc:
            raise Transient(f"{self.url}: {getattr(exc, 'reason', exc)}")

    def close(self):
        pass


# --- tailing ---------------------------------------------------------------

class Tailer:
    def __init__(self, path, checkpoint, sink, content, sink_id):
        self.path, self.checkpoint, self.sink, self.content, self.sink_id = path, checkpoint, sink, content, sink_id
        self.inode, self.offset, self.head, self.spans, self.error = None, 0, "", 0, ""
        try:
            with open(checkpoint, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            # A different sink starts from the beginning of the file and gets the full history.
            if saved.get("sink") == sink_id:
                self.inode = saved.get("inode")
                self.offset = int(saved.get("offset", 0))
                self.head = str(saved.get("head", ""))
                self.spans = int(saved.get("spans", 0))
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def save(self):
        tmp = f"{self.checkpoint}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump({"sink": self.sink_id, "inode": self.inode, "offset": self.offset, "head": self.head,
                           "spans": self.spans, "error": self.error}, handle)
            os.replace(tmp, self.checkpoint)
        except OSError as exc:
            raise Fatal(f"cannot save {self.checkpoint}: {exc}")

    def _reset(self, inode):
        self.inode, self.offset, self.head = inode, 0, ""

    def _head_matches(self, path):
        if not self.head:
            return True
        want = bytes.fromhex(self.head)
        try:
            with open(path, "rb") as handle:
                return handle.read(len(want)) == want
        except OSError:
            return False

    def _consume(self, path, size):
        with open(path, "rb") as handle:
            while self.offset < size:
                handle.seek(self.offset)
                chunk = handle.read(min(CHUNK, size - self.offset))
                cut = chunk.rfind(b"\n")
                if cut < 0:
                    if len(chunk) < CHUNK:
                        return  # a line still being written
                    log("skipped an oversized line in the Router telemetry file")
                    self.offset += len(chunk)
                    continue
                lines = chunk[:cut + 1].split(b"\n")[:-1]
                # One checkpoint per batch, so a failed send never repeats batches the sink already took.
                for i in range(0, len(lines), BATCH):
                    part = lines[i:i + BATCH]
                    spans = self._spans(part, self.offset)
                    if spans:
                        self.sink.send(spans)
                        self.spans += len(spans)
                    self.offset += sum(len(raw) + 1 for raw in part)
                    if not self.head:
                        handle.seek(0)
                        self.head = handle.read(min(HEAD_BYTES, self.offset)).hex()
                    self.save()

    def _spans(self, lines, offset):
        spans = []
        for raw in lines:
            position, offset = offset, offset + len(raw) + 1
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
                if isinstance(event, dict):
                    spans.append(make_span(event, raw, self.content, position))
            except Exception:  # one odd event must not stall the tail
                continue
        return spans

    def poll(self):
        try:
            stat = os.stat(self.path)
        except FileNotFoundError:
            return
        if self.inode is not None and stat.st_ino != self.inode:
            # Rotated: the old generation is now <file>.1; finish it before starting the new file.
            rotated = f"{self.path}.1"
            try:
                old = os.stat(rotated)
            except OSError:
                old = None
            if old is not None and old.st_ino == self.inode and self._head_matches(rotated):
                self._consume(rotated, old.st_size)
            self._reset(stat.st_ino)
        elif self.inode is None:
            self._reset(stat.st_ino)
        elif stat.st_size < self.offset or not self._head_matches(self.path):
            self._reset(stat.st_ino)  # truncated (reset or clean) and possibly regrown
        self._consume(self.path, stat.st_size)
        if self.error:
            self.error = ""
            self.save()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--checkpoint", required=True)
    sink = ap.add_mutually_exclusive_group(required=True)
    sink.add_argument("--db")
    sink.add_argument("--endpoint")
    ap.add_argument("--content", choices=("off", "preview", "full"), default="off")
    ap.add_argument("--max-rows", type=int, default=200000)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--pidfile")
    args = ap.parse_args()

    os.umask(0o077)
    sink = SqliteSink(args.db, args.max_rows) if args.db else OtlpSink(args.endpoint)
    tailer = Tailer(args.file, args.checkpoint, sink, args.content, args.db or args.endpoint.rstrip("/"))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    if args.pidfile:
        with open(args.pidfile, "w") as handle:
            handle.write(str(os.getpid()))
    wait = args.interval
    code = 0
    try:
        while not stop.is_set():
            try:
                tailer.poll()
                wait = args.interval
            except Transient as exc:
                if str(exc) != tailer.error:
                    log(f"waiting for the sink: {exc}")
                tailer.error = str(exc)[:300]
                try:
                    tailer.save()
                except Fatal:
                    pass
                wait = min(wait * 2, 30.0)
            except Fatal as exc:
                log(str(exc))
                code = 1
                break
            except OSError as exc:
                log(f"read error: {exc}")
                wait = min(wait * 2, 30.0)
            stop.wait(wait)
        # One last pass so events written just before the stop are not left behind.
        if not code:
            try:
                tailer.poll()
            except (Transient, Fatal, OSError):
                pass
    finally:
        try:
            sink.close()
        except sqlite3.Error:
            pass
        if args.pidfile:
            try:
                os.unlink(args.pidfile)
            except OSError:
                pass
    sys.exit(code)


if __name__ == "__main__":
    main()
