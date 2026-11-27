#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Loopback OTLP/HTTP trace receiver that keeps spans in a local SQLite store.

Started by `./install.sh observability enable --backend sqlite` for agents that
export OpenTelemetry themselves (OpenClaw, dcode through its agent-harness
extension, and Hermes inside an OpenShell sandbox). Rows use the same `events` table as the Hermes hermes-otel
plugin so `observability show/disable --clean` handle every agent alike. Standard
library only: the OTLP protobuf messages are decoded by hand (only the fields
stored here).
"""

import argparse
import http.server
import json
import os
import signal
import sqlite3
import struct
import threading
import zlib

MAX_BODY = 16 * 1024 * 1024
MAX_VALUE = 2000
MAX_CONTENT = 20000
PREVIEW = 200

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
    "ts INTEGER NOT NULL, data TEXT NOT NULL, trace_id TEXT, span_id TEXT, parent_span_id TEXT, "
    "session_id TEXT, name TEXT, status TEXT, start_ns INTEGER, end_ns INTEGER, duration_ms REAL, "
    "level INTEGER, logger TEXT, value REAL)"
)

OPENCLAW_SPANS = {
    "openclaw.run",
    "openclaw.model.call",
    "openclaw.tool.execution",
    "openclaw.model.usage",
    "openclaw.harness.run",
}
MAX_DEPTH = 16
REQUEST_TIMEOUT = 30

CONTENT_KEYS = {
    "gen_ai.prompt",
    "gen_ai.completion",
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
    "input.value",
    "output.value",
    "langfuse.observation.input",
    "langfuse.observation.output",
}
# Indexed forms such as gen_ai.prompt.0.content.
CONTENT_PREFIXES = ("gen_ai.prompt.", "gen_ai.completion.", "llm.prompts", "llm.completions", "openclaw.content.")
DROP_KEYS = {"gen_ai.tool.definitions", "openclaw.content.tool_definitions"}
SESSION_KEYS = (
    "openclaw.sessionKey",
    "session.id",
)


def keep_span(agent, span):
    if agent == "openclaw":
        return span["name"] in OPENCLAW_SPANS
    return True


def is_content(key):
    return key in CONTENT_KEYS or key.startswith(CONTENT_PREFIXES)


def span_data(span, content):
    out = {}
    for key, val in span["attrs"].items():
        if key in DROP_KEYS:
            continue
        if is_content(key):
            if content == "off":
                continue
            limit = PREVIEW if content == "preview" else MAX_CONTENT
            if not isinstance(val, str):
                val = json.dumps(val, default=str)
        else:
            limit = MAX_VALUE
        out[key] = val[:limit] if isinstance(val, str) else val
    return out


# --- minimal protobuf wire-format reader -----------------------------------

def _varint(buf, i):
    result = shift = 0
    while True:
        if i >= len(buf) or shift > 63:
            raise ValueError("bad varint")
        byte = buf[i]
        i += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, i
        shift += 7


def _fields(buf):
    i, n = 0, len(buf)
    while i < n:
        tag, i = _varint(buf, i)
        field, wire = tag >> 3, tag & 7
        if wire == 0:
            val, i = _varint(buf, i)
        elif wire == 1:
            if i + 8 > n:
                raise ValueError("truncated field")
            val, i = buf[i:i + 8], i + 8
        elif wire == 2:
            size, i = _varint(buf, i)
            if i + size > n:
                raise ValueError("truncated field")
            val, i = buf[i:i + size], i + size
        elif wire == 5:
            if i + 4 > n:
                raise ValueError("truncated field")
            val, i = buf[i:i + 4], i + 4
        else:
            raise ValueError("unsupported wire type")
        yield field, wire, val


def _any_value(buf, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError("value nested too deeply")
    for field, wire, val in _fields(buf):
        if field == 1 and wire == 2:
            return val.decode("utf-8", "replace")
        if field == 2 and wire == 0:
            return bool(val)
        if field == 3 and wire == 0:
            return val - (1 << 64) if val >= 1 << 63 else val
        if field == 4 and wire == 1:
            return struct.unpack("<d", val)[0]
        if field == 5 and wire == 2:
            return [_any_value(v, depth + 1) for f, w, v in _fields(val) if f == 1 and w == 2]
        if field == 6 and wire == 2:
            return dict(_key_value(v, depth + 1) for f, w, v in _fields(val) if f == 1 and w == 2)
        if field == 7 and wire == 2:
            return val.hex()
    return None


def _key_value(buf, depth=0):
    key, val = "", None
    for field, wire, v in _fields(buf):
        if field == 1 and wire == 2:
            key = v.decode("utf-8", "replace")
        elif field == 2 and wire == 2:
            val = _any_value(v, depth)
    return key, val


def _span(buf):
    span = {"trace_id": "", "span_id": "", "parent": "", "name": "", "start": 0, "end": 0, "status": 0, "attrs": {}}
    for field, wire, val in _fields(buf):
        if field == 1 and wire == 2:
            span["trace_id"] = val.hex()
        elif field == 2 and wire == 2:
            span["span_id"] = val.hex()
        elif field == 4 and wire == 2:
            span["parent"] = val.hex()
        elif field == 5 and wire == 2:
            span["name"] = val.decode("utf-8", "replace")
        elif field == 7 and wire == 1:
            span["start"] = struct.unpack("<Q", val)[0]
        elif field == 8 and wire == 1:
            span["end"] = struct.unpack("<Q", val)[0]
        elif field == 9 and wire == 2:
            key, v = _key_value(val)
            span["attrs"][key] = v
        elif field == 15 and wire == 2:
            for f, w, v in _fields(val):
                if f == 3 and w == 0:
                    span["status"] = v
    return span


def parse_export_request(buf):
    for f1, w1, resource_spans in _fields(buf):
        if f1 != 1 or w1 != 2:
            continue
        for f2, w2, scope_spans in _fields(resource_spans):
            if f2 != 2 or w2 != 2:
                continue
            for f3, w3, span in _fields(scope_spans):
                if f3 == 2 and w3 == 2:
                    yield _span(span)


# --- storage and server ----------------------------------------------------

class Store:
    def __init__(self, path, agent, content, max_rows):
        self.agent, self.content, self.max_rows = agent, content, max_rows
        self.lock = threading.Lock()
        self.inserted = 0
        os.umask(0o077)
        self.con = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute(SCHEMA)
        self.con.commit()

    def add(self, spans):
        rows = []
        for span in spans:
            if not keep_span(self.agent, span):
                continue
            session = next((str(span["attrs"][k]) for k in SESSION_KEYS if span["attrs"].get(k)), None)
            rows.append((
                span["end"], json.dumps(span_data(span, self.content), default=str), span["trace_id"], span["span_id"],
                span["parent"] or None, session, span["name"], "ERROR" if span["status"] == 2 else "OK",
                span["start"], span["end"], max(span["end"] - span["start"], 0) / 1e6,
            ))
        if not rows:
            return
        with self.lock:
            try:
                self.con.executemany(
                    "INSERT INTO events (kind, ts, data, trace_id, span_id, parent_span_id, session_id, name, status, "
                    "start_ns, end_ns, duration_ms) VALUES ('span', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
                self.inserted += len(rows)
                if self.max_rows and self.inserted >= 500:
                    self.inserted = 0
                    self.con.execute(
                        "DELETE FROM events WHERE seq <= (SELECT MAX(seq) FROM events) - ?", (self.max_rows,))
                self.con.commit()
            except sqlite3.Error:
                self.con.rollback()
                raise

    def close(self):
        with self.lock:
            try:
                self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                self.con.close()


def read_body(handler):
    if "chunked" in (handler.headers.get("Transfer-Encoding") or "").lower():
        body = b""
        while True:
            size = int((handler.rfile.readline(64).split(b";")[0].strip() or b"0"), 16)
            if size < 0 or size > MAX_BODY - len(body):
                raise ValueError("body too large")
            if size == 0:
                handler.rfile.readline()
                return body
            body += handler.rfile.read(size)
            handler.rfile.readline()
    size = int(handler.headers.get("Content-Length") or 0)
    if size < 0 or size > MAX_BODY:
        raise ValueError("body too large")
    return handler.rfile.read(size)


def make_handler(store):
    class Handler(http.server.BaseHTTPRequestHandler):
        timeout = REQUEST_TIMEOUT

        def log_message(self, *_):
            pass

        def _reply(self, code, ctype="application/x-protobuf"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            self._reply(200 if self.path == "/healthz" else 404, "text/plain")

        def do_POST(self):
            if self.path.split("?")[0] != "/v1/traces":
                return self._reply(404, "text/plain")
            if "protobuf" not in (self.headers.get("Content-Type") or ""):
                return self._reply(415, "text/plain")
            try:
                body = read_body(self)
                if (self.headers.get("Content-Encoding") or "").lower() == "gzip":
                    inflater = zlib.decompressobj(31)
                    body = inflater.decompress(body, MAX_BODY)
                spans = list(parse_export_request(body))
            except Exception:
                # Any malformed or hostile payload must end in a reply, not a dead handler thread.
                try:
                    self._reply(400, "text/plain")
                except OSError:
                    pass
                return
            try:
                store.add(spans)
            except sqlite3.Error:
                # 400 would make the exporter drop a valid batch; 503 is retried.
                try:
                    self._reply(503, "text/plain")
                except OSError:
                    pass
                return
            self._reply(200)

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--agent", choices=("openclaw", "hermes", "deepagents-code"), required=True)
    ap.add_argument("--content", choices=("off", "preview", "full"), default="off")
    ap.add_argument("--max-rows", type=int, default=200000)
    ap.add_argument("--pidfile")
    args = ap.parse_args()

    store = Store(args.db, args.agent, args.content, args.max_rows)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
    server.daemon_threads = True
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    if args.pidfile:
        with open(args.pidfile, "w") as f:
            f.write(str(os.getpid()))
    try:
        server.serve_forever()
    finally:
        server.server_close()
        store.close()
        if args.pidfile:
            try:
                os.unlink(args.pidfile)
            except OSError:
                pass


if __name__ == "__main__":
    main()
