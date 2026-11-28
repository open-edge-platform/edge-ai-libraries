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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics_store  # noqa: E402

CHUNK = 1 << 20
MAX_VALUE = 2000
PREVIEW = 200
MAX_DEPTH = 3
BATCH = 200
HEAD_BYTES = 256
# A Router that was running when the file was rotated keeps appending to <file>.1 until it restarts.
DRAIN_SECONDS = 60
# Status codes that mean the batch itself is unacceptable (bad request, too large, wrong type, invalid).
REJECTED = (400, 413, 415, 422)
GATED_KEYS = {"metadata", "details"}
SKIP_KEYS = {"event_type", "timestamp", "request_id", "provider_name", "final_model",
             "total_input_tokens", "total_output_tokens"}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
SERVICE = "inference-router"


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
    last_drop = ""

    def __init__(self, path, max_rows):
        self.max_rows, self.inserted = max_rows, 0
        self.con = metrics_store.open_store(path)

    def send(self, spans):
        rows = [(
            s["end"], json.dumps(s["attrs"], default=str), s["trace_id"], s["span_id"], s["parent"] or None,
            None, s["name"], "ERROR" if s["error"] else "OK", s["start"], s["end"],
            max(s["end"] - s["start"], 0) / 1e6,
        ) for s in spans]
        try:
            self.con.executemany(metrics_store.INSERT_SPAN, rows)
            self.inserted += len(rows)
            if self.max_rows and self.inserted >= metrics_store.PRUNE_EVERY:
                self.inserted = 0
                metrics_store.prune(self.con, self.max_rows)
            self.con.commit()
        except sqlite3.Error as exc:
            self.con.rollback()
            raise Transient(f"sqlite: {exc}")
        return 0

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
    last_drop = ""

    def __init__(self, endpoint):
        parts = urllib.parse.urlsplit(endpoint.rstrip("/"))
        # A bare collector URL gets the standard path; an explicit path is used as given.
        self.url = endpoint.rstrip("/") if parts.path else endpoint.rstrip("/") + "/v1/traces"
        # Internal collectors are reached directly, never through a corporate proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def send(self, spans):
        """Returns how many spans the collector refused for good."""
        return sum(self._post(spans[i:i + BATCH]) for i in range(0, len(spans), BATCH))

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
            if exc.code in REJECTED:
                # The collector refuses this batch itself, so a retry cannot help; it is counted and shown.
                self.last_drop = f"HTTP {exc.code} from {self.url}"
                log(f"collector rejected {len(spans)} spans with HTTP {exc.code}; dropped")
                return len(spans)
            # Other errors (401/403/404/5xx...) are about the endpoint, not the batch: retried until fixed.
            raise Transient(f"HTTP {exc.code} from {self.url}")
        except (urllib.error.URLError, OSError) as exc:
            raise Transient(f"{self.url}: {getattr(exc, 'reason', exc)}")
        return 0

    def close(self):
        pass


# --- tailing ---------------------------------------------------------------

class Tailer:
    def __init__(self, path, checkpoint, sink, content, sink_id):
        self.path, self.checkpoint, self.sink, self.content, self.sink_id = path, checkpoint, sink, content, sink_id
        self.inode, self.offset, self.head, self.spans, self.error = None, 0, "", 0, ""
        self.dropped, self.drop_reason = 0, ""
        self.drain = None
        self.drain_handle = None
        self.draining = False
        try:
            with open(checkpoint, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            # A different sink starts from the beginning of the file and gets the full history.
            if saved.get("sink") == sink_id:
                self.inode = saved.get("inode")
                self.offset = int(saved.get("offset", 0))
                self.head = str(saved.get("head", ""))
                self.spans = int(saved.get("spans", 0))
                self.dropped = int(saved.get("dropped", 0))
                self.drop_reason = str(saved.get("drop_reason", ""))
                if isinstance(saved.get("drain"), dict):
                    d = saved["drain"]
                    self.drain = {"inode": int(d["inode"]), "offset": int(d["offset"]), "head": str(d.get("head", "")),
                                  "until": float(d["until"])}
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            pass

    def save(self):
        if self.draining:
            return  # the checkpoint always describes the live file
        tmp = f"{self.checkpoint}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump({"sink": self.sink_id, "inode": self.inode, "offset": self.offset, "head": self.head,
                           "spans": self.spans, "error": self.error, "dropped": self.dropped,
                           "drop_reason": self.drop_reason, "drain": self.drain}, handle)
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

    def _open_rotated(self, inode, head):
        """Opens <file>.1 if it is the generation with this inode and head; the handle outlives a later rotation."""
        try:
            handle = open(f"{self.path}.1", "rb")
        except OSError:
            return None
        want = bytes.fromhex(head)
        if os.fstat(handle.fileno()).st_ino != inode or handle.read(len(want)) != want:
            handle.close()
            return None
        return handle

    def _consume(self, path, size):
        with open(path, "rb") as handle:
            self._read(handle, size)

    def _read(self, handle, size):
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
                    lost = self.sink.send(spans) or 0
                    self.spans += len(spans) - lost
                    if lost:
                        self.dropped += lost
                        self.drop_reason = self.sink.last_drop[:300]
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

    def _end_drain(self):
        if self.drain_handle is not None:
            self.drain_handle.close()
        self.drain, self.drain_handle = None, None

    def _drain_rotated(self):
        drain = self.drain
        if drain is None:
            return
        if time.time() > drain["until"]:
            self._end_drain()
            self.save()
            return
        if self.drain_handle is None:
            # After a restart: the generation is still there only if it was not rotated away meanwhile.
            self.drain_handle = self._open_rotated(drain["inode"], drain["head"])
            if self.drain_handle is None:
                self._end_drain()
                self.save()
                return
        size = os.fstat(self.drain_handle.fileno()).st_size
        if size > drain["offset"]:
            live = (self.inode, self.offset, self.head)
            self.inode, self.offset, self.head = drain["inode"], drain["offset"], drain["head"]
            self.draining = True
            try:
                self._read(self.drain_handle, size)
            finally:
                self.draining = False
                drain["offset"] = self.offset
                self.inode, self.offset, self.head = live
            self.save()

    def poll(self):
        try:
            stat = os.stat(self.path)
        except FileNotFoundError:
            return
        if self.inode is not None and stat.st_ino != self.inode:
            # Rotated: the old generation is now <file>.1; finish it before starting the new file.
            self._drain_rotated()  # the generation before it, which a second rotation has just removed
            self._end_drain()
            old = self._open_rotated(self.inode, self.head)
            if old is not None:
                try:
                    self._read(old, os.fstat(old.fileno()).st_size)
                except BaseException:
                    old.close()
                    raise
                self.drain, self.drain_handle = {"inode": self.inode, "offset": self.offset, "head": self.head,
                                                 "until": time.time() + DRAIN_SECONDS}, old
            self._reset(stat.st_ino)
        elif self.inode is None:
            self._reset(stat.st_ino)
        elif stat.st_size < self.offset or not self._head_matches(self.path):
            self._reset(stat.st_ino)  # truncated (reset or clean) and possibly regrown
        self._drain_rotated()
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
