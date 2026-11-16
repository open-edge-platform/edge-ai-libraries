#!/usr/bin/env python3
"""Audio Analyzer streaming transcription benchmark.

Benchmarks only ``POST /v1/audio/transcriptions`` with ``stream=true`` (OpenAI-compatible
SSE: ``transcript.text.delta`` ... ``transcript.text.done`` ... ``[DONE]``). Every audio
file in ``data/`` is used as input (cycled across requests).

Per-request timeline (all measured on the client from the same request start):

    start ── upload ──┬── decode ──┬── inference ──┐
                      upload_time  ttft            e2e_latency

    upload_time    request start -> multipart body (incl. closing boundary) fully written
    decode_time    upload end -> first transcript chunk (ttft - upload_time): server-side
                   save + FFmpeg decode/chunking + first-chunk ASR
    ttft           request start -> first non-empty transcript chunk
    inference_time first chunk -> end of stream (e2e_latency - ttft)
    itl            gap between consecutive transcript chunks
    output_tokens  final transcript tokenized with the tokenizer of the model served by
                   the running container (from GET /v1/model-info)

Examples:
  python3 bench_audio_analyzer.py --concurrency 1 --num-requests 1 --no-resource-util
  python3 bench_audio_analyzer.py --concurrency 1,2,4 --num-requests 4

Run sequence: warmup -> start resource monitor -> measured concurrency points -> stop monitor -> plot graphs.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import itertools
import json
import math
import mimetypes
import shutil
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import aiohttp
except ImportError:
    sys.exit("Missing dependency: pip install 'aiohttp>=3.8'")

try:
    from tokenizers import Tokenizer
except ImportError:
    sys.exit("Missing dependency: pip install tokenizers")


TARGET_NAME = "Audio Analyzer - streaming transcription (SSE)"
BASE_URL = "http://localhost:8010"
ENDPOINT = "/v1/audio/transcriptions"
# OpenAI-compatible alias accepted by the service; the served model is set server-side.
MODEL_ALIAS = "whisper-1"
LANGUAGE = "en"

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".webm", ".mp4"}
NAN = math.nan

CSV_COLS = ["concurrency", "req_id", "audio_file", "status", "error",
            "e2e_latency_s", "upload_time_s", "decode_time_s", "ttft_s", "itl_s",
            "inference_time_s", "output_tokens", "total_chunks"]
METRICS = ["e2e_latency_s", "upload_time_s", "decode_time_s", "ttft_s", "itl_s",
           "inference_time_s", "output_tokens", "total_chunks"]

TOKENIZER: Tokenizer | None = None


# ---------- input ----------

def _ffprobe_info(path: Path) -> dict:
    """Duration and format of an audio file (format falls back to the extension without ffprobe)."""
    info = {"duration_s": None, "format": path.suffix.lstrip(".").lower() or None, "codec": None,
            "sample_rate_hz": None, "channels": None, "bit_rate_kbps": None}
    if not shutil.which("ffprobe"):
        return info
    try:
        out = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "format=format_name,duration,bit_rate:stream=codec_name,sample_rate,channels",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout)
    except (subprocess.SubprocessError, ValueError):
        return info
    fmt = out.get("format") or {}
    stream = (out.get("streams") or [{}])[0]

    def num(v, cast=float):
        try:
            return cast(v)
        except (TypeError, ValueError):
            return None

    duration, bit_rate = num(fmt.get("duration")), num(fmt.get("bit_rate"))
    info.update({
        "duration_s": round(duration, 3) if duration is not None else None,
        "format": fmt.get("format_name") or info["format"],
        "codec": stream.get("codec_name"),
        "sample_rate_hz": num(stream.get("sample_rate"), int),
        "channels": num(stream.get("channels"), int),
        "bit_rate_kbps": round(bit_rate / 1000, 1) if bit_rate is not None else None,
    })
    return info


def load_audio_files() -> list[dict]:
    files = sorted(f for f in DATA_DIR.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXT) \
        if DATA_DIR.is_dir() else []
    if not files:
        sys.exit(f"No audio files ({', '.join(sorted(AUDIO_EXT))}) found in {DATA_DIR}")
    return [{"name": f.name, "bytes": f.read_bytes(),
             "mime": mimetypes.guess_type(f.name)[0] or "application/octet-stream",
             **_ffprobe_info(f)} for f in files]


# ---------- server info / tokenizer ----------

async def fetch_server_info(base_url: str) -> dict[str, Any]:
    """Fetch the ASR runtime settings from the running Audio Analyzer."""
    url = f"{base_url.rstrip('/')}/v1/model-info"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            info = await response.json()
    fields = {"asr_provider": "provider", "asr_model": "model",
              "asr_device": "device", "asr_weight_format": "weight_format"}
    if not isinstance(info, dict) or any(src not in info for src in fields.values()):
        raise ValueError(f"Unexpected runtime metadata from {url}: {info}")
    return {"service": "audio-analyzer", **{k: info[src] for k, src in fields.items()}}


def _container_for(base_url: str) -> str | None:
    port = urlparse(base_url).port
    if not port or not shutil.which("docker"):
        return None
    try:
        names = subprocess.run(["docker", "ps", "--filter", f"publish={port}", "--format", "{{.Names}}"],
                               capture_output=True, text=True, timeout=15, check=True).stdout.split()
    except subprocess.SubprocessError:
        return None
    return names[0] if names else None


def _tokenizer_from_container(container: str, model: str) -> tuple[Tokenizer, str] | None:
    """Load the tokenizer.json shipped with the model served inside the container."""
    pattern = f"*/{model}*/tokenizer.json"
    try:
        # Model dirs (models_base_path) resolve under the container workdir; scan "/" only as a fallback.
        for root in (".", "/"):
            found = subprocess.run(
                ["docker", "exec", container, "find", root, "(", "-path", "/proc", "-o", "-path", "/sys", ")",
                 "-prune", "-o", "-name", "tokenizer.json", "-path", pattern, "-print"],
                capture_output=True, text=True, timeout=120,
            ).stdout.split()
            if found:
                break
        else:
            return None
        path = sorted(found, key=len)[0]
        blob = subprocess.run(["docker", "exec", container, "cat", path],
                              capture_output=True, text=True, timeout=30, check=True).stdout
        return Tokenizer.from_str(blob), f"container:{container}:{path}"
    except Exception:  # noqa: BLE001 - fall back to the next source
        return None


def load_tokenizer(override: str | None, model: str, base_url: str) -> tuple[Tokenizer, str]:
    if override:
        p = Path(override).expanduser()
        if p.is_dir():
            p = p / "tokenizer.json"
        if p.is_file():
            return Tokenizer.from_file(str(p)), f"file:{p}"
        return Tokenizer.from_pretrained(override), f"hf:{override}"

    container = _container_for(base_url)
    if container:
        res = _tokenizer_from_container(container, model)
        if res:
            return res
    if model.startswith("whisper"):
        hub_id = f"openai/{model}"
        try:
            return Tokenizer.from_pretrained(hub_id), f"hf:{hub_id}"
        except Exception as e:  # noqa: BLE001
            sys.exit(f"Could not load tokenizer for '{model}' from container or {hub_id} ({e}); "
                     "pass --tokenizer PATH_OR_HF_ID")
    sys.exit(f"Could not locate a tokenizer for served model '{model}'; pass --tokenizer PATH_OR_HF_ID")


def count_tokens(text: str) -> int:
    return len(TOKENIZER.encode(text, add_special_tokens=False).ids) if text else 0


# ---------- request execution ----------

@dataclass
class Rec:
    req_id: int
    audio_file: str
    status: int = 0
    ok: bool = False
    error: str = ""
    e2e_latency: float = NAN
    upload_time: float = NAN
    ttft: float = NAN
    output_tokens: int = 0
    total_chunks: int = 0
    text: str = ""
    itls: list = field(default_factory=list)

    @property
    def decode_time(self):
        return self.ttft - self.upload_time

    @property
    def inference_time(self):
        return self.e2e_latency - self.ttft

    @property
    def itl(self):
        return sum(self.itls) / len(self.itls) if self.itls else NAN

    def metrics(self) -> dict:
        return {"e2e_latency_s": self.e2e_latency, "upload_time_s": self.upload_time,
                "decode_time_s": self.decode_time, "ttft_s": self.ttft, "itl_s": self.itl,
                "inference_time_s": self.inference_time,
                "output_tokens": self.output_tokens, "total_chunks": self.total_chunks}

    def row(self, conc):
        m = self.metrics() if self.ok else {}
        return [conc, self.req_id, self.audio_file, self.status, self.error,
                *(_f(m.get(k, NAN)) for k in METRICS)]


def _f(x):
    if isinstance(x, int):
        return x
    return "" if x != x else f"{x:.6f}"


class _TimedMultipartPayload(aiohttp.payload.Payload):
    """Wraps the multipart body to record when the upload has been fully written."""

    def __init__(self, payload: aiohttp.payload.Payload, rec: Rec, t0: float):
        super().__init__(payload, headers=payload.headers)
        self._size = payload.size
        self.payload = payload
        self.rec = rec
        self.t0 = t0

    def decode(self, encoding: str = "utf-8", errors: str = "strict") -> str:
        return self.payload.decode(encoding, errors)

    async def write(self, writer: aiohttp.abc.AbstractStreamWriter) -> None:
        await self.payload.write(writer)
        # Includes the closing multipart boundary; not a server receive acknowledgement.
        self.rec.upload_time = time.perf_counter() - self.t0


def _form(audio: dict) -> aiohttp.FormData:
    fd = aiohttp.FormData()
    fd.add_field("file", audio["bytes"], filename=audio["name"], content_type=audio["mime"])
    fd.add_field("model", MODEL_ALIAS)
    fd.add_field("language", LANGUAGE)
    fd.add_field("response_format", "json")
    fd.add_field("stream", "true")
    return fd


async def _stream(session, url, audio, rec, t0):
    data = _TimedMultipartPayload(_form(audio)(), rec, t0)
    async with session.post(url, data=data) as resp:
        rec.status = resp.status
        if resp.status >= 400:
            body = await resp.content.read(300)
            rec.error = f"HTTP {resp.status}: {body.decode('utf-8', 'replace')}"
            return
        last, pieces, final_text = None, [], None
        async for raw in resp.content:
            line = raw.strip()
            if not line.startswith(b"data:"):
                continue
            line = line[5:].strip()
            if line == b"[DONE]":
                break
            evt = json.loads(line)
            typ = evt.get("type")
            if typ == "transcript.text.delta" and evt.get("delta"):
                now = time.perf_counter()
                if last is None:
                    rec.ttft = now - t0
                else:
                    rec.itls.append(now - last)
                last = now
                rec.total_chunks += 1
                pieces.append(evt["delta"])
            elif typ == "transcript.text.done":
                final_text = evt.get("text")
        rec.text = final_text if final_text is not None else " ".join(pieces)
        rec.output_tokens = count_tokens(rec.text)
        rec.ok = rec.total_chunks > 0
        if not rec.ok:
            rec.error = "empty stream"
        elif rec.ttft < rec.upload_time:
            rec.ok, rec.error = False, "first transcript observed before upload completion"


async def execute(session, audio, rec, timeout):
    url = BASE_URL.rstrip("/") + ENDPOINT
    t0 = time.perf_counter()
    try:
        await asyncio.wait_for(_stream(session, url, audio, rec, t0), timeout)
    except asyncio.TimeoutError:
        rec.ok, rec.error = False, "timeout"
    except Exception as e:  # noqa: BLE001 - any failure is recorded, the run continues
        rec.ok, rec.error = False, f"{type(e).__name__}: {e}"
    rec.e2e_latency = time.perf_counter() - t0


# ---------- statistics ----------

def _pct(s, q):
    k = (len(s) - 1) * q / 100
    lo = math.floor(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def dist(a):
    a = [x for x in a if x == x]
    if not a:
        return None
    s = sorted(a)
    mean = sum(s) / len(s)
    out = {"mean": mean, "min": s[0], "max": s[-1]}
    for q in (50, 90, 99):
        out[f"p{q}"] = _pct(s, q)
    return {k: round(v, 6) for k, v in out.items()}


class Stats:
    def __init__(self):
        self.n = self.ok = 0
        self.errors = Counter()
        self.values = {k: [] for k in METRICS}

    def add(self, r: Rec):
        self.n += 1
        if not r.ok:
            self.errors[r.error[:120]] += 1
            return
        self.ok += 1
        for k, v in r.metrics().items():
            if k == "itl_s":
                self.values[k].extend(r.itls)  # all inter-chunk gaps, not per-request means
            else:
                self.values[k].append(v)

    def summary(self, wall):
        return {"requests": self.n, "success": self.ok, "errors": self.n - self.ok,
                "top_errors": self.errors.most_common(5), "wall_time_s": round(wall, 3),
                **{k: dist(v) for k, v in self.values.items()}}


# ---------- load generation ----------

def _write_transcript(fh, conc, rec: Rec):
    status = "ok" if rec.ok else f"error: {rec.error}"
    fh.write(f"===== concurrency={conc} req_id={rec.req_id} audio_file={rec.audio_file} "
             f"status={rec.status} ({status}) =====\n{rec.text}\n\n")
    fh.flush()


class Runner:
    def __init__(self, session, audios, timeout, stats=None, writer=None, conc=0, text_fh=None):
        self.session, self.timeout = session, timeout
        self.it = itertools.cycle(audios)
        self.stats, self.writer, self.conc, self.text_fh = stats, writer, conc, text_fh

    async def one(self, i):
        audio = next(self.it)
        rec = Rec(i, audio["name"])
        await execute(self.session, audio, rec, self.timeout)
        if self.stats is not None:
            self.stats.add(rec)
            self.writer.writerow(rec.row(self.conc))
        if self.text_fh is not None:
            _write_transcript(self.text_fh, self.conc, rec)


async def closed_loop(runner, conc, n_req):
    ctr = itertools.count()

    async def worker():
        while (i := next(ctr)) < n_req:
            await runner.one(i)

    await asyncio.gather(*(worker() for _ in range(conc)))


def _session():
    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0), read_bufsize=2 ** 20,
                                 timeout=aiohttp.ClientTimeout(total=None))


async def warmup(audios, args):
    """Warm the service; never recorded and runs before resource monitoring starts."""
    async with _session() as session:
        await closed_loop(Runner(session, audios, args.timeout), min(args.concurrency[0], args.warmup),
                          args.warmup)


COLS = [("conc", 6, lambda d: d["concurrency"]), ("n", 5, lambda d: d["requests"]),
        ("err", 5, lambda d: d["errors"])] + [
    (f"{name}_p50", w, (lambda k: lambda d: (d.get(k) or {}).get("p50"))(key))
    for name, key, w in [("e2e", "e2e_latency_s", 10), ("upload", "upload_time_s", 11),
                         ("decode", "decode_time_s", 11), ("ttft", "ttft_s", 10), ("itl", "itl_s", 10),
                         ("infer", "inference_time_s", 10),
                         ("tokens", "output_tokens", 11), ("chunks", "total_chunks", 11)]]


def _cell(v, w):
    s = "-" if v is None else f"{v:.4f}" if isinstance(v, float) else str(v)
    return s.ljust(w)


def _write_summary(out_dir, summary):
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")


async def measure(audios, args, summary, out_dir):
    print(" ".join(_cell(t, w) for t, w, _ in COLS))
    async with _session() as session:
        with (out_dir / "raw_transcribe_sse.csv").open("w", newline="", encoding="utf-8") as fh, \
                (out_dir / "transcripts.txt").open("w", encoding="utf-8") as text_fh:
            writer = csv.writer(fh)
            writer.writerow(CSV_COLS)
            for conc in args.concurrency:
                stats = Stats()
                runner = Runner(session, audios, args.timeout, stats, writer, conc, text_fh)
                start_epoch, t0 = time.time(), time.perf_counter()
                await closed_loop(runner, conc, args.num_requests)
                res = {"concurrency": conc, "start_epoch": round(start_epoch, 3),
                       "end_epoch": round(time.time(), 3), **stats.summary(time.perf_counter() - t0)}
                summary["points"].append(res)
                fh.flush()
                print(" ".join(_cell(g(res), w) for _, w, g in COLS))
                _write_summary(out_dir, summary)


def _int_list(text):
    try:
        vals = [int(v) for v in str(text).split(",") if v.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected comma-separated integers, got '{text}'")
    if not vals or min(vals) < 1:
        raise argparse.ArgumentTypeError("values must be >= 1")
    return vals


def main():
    global BASE_URL, TOKENIZER
    ap = argparse.ArgumentParser(description=f"Benchmark: {TARGET_NAME}")
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--concurrency", type=_int_list, default=[1],
                    help="comma-separated concurrency sweep, e.g. 1,2,4 (default: 1)")
    ap.add_argument("--num-requests", type=int, default=1, help="measured requests per concurrency point")
    ap.add_argument("--warmup", type=int, default=1, help="unrecorded warmup requests before measurement")
    ap.add_argument("--timeout", type=float, default=1200.0, help="per-request timeout in seconds")
    ap.add_argument("--tokenizer", help="override tokenizer (tokenizer.json path/dir or HF id); "
                                        "default: tokenizer of the model served by the container")
    ap.add_argument("--out-dir", default=str(HERE / "results"))
    ap.add_argument("--resource-util", action=argparse.BooleanOptionalAction, default=True,
                    help="collect CPU/GPU/NPU/memory/temperature during measured runs (resource_utilization.py)")
    ap.add_argument("--metrics-image", default=None,
                    help="Metrics Manager image (default: resource_utilization.py default)")
    args = ap.parse_args()
    BASE_URL = args.base_url

    audios = load_audio_files()
    server_info = asyncio.run(fetch_server_info(BASE_URL))
    TOKENIZER, tok_src = load_tokenizer(args.tokenizer, server_info["asr_model"], BASE_URL)
    print(f"Served model: {server_info['asr_model']} ({server_info['asr_provider']}/{server_info['asr_device']})")
    print(f"Tokenizer: {tok_src}")
    print("Inputs: " + ", ".join(f"{a['name']} ({a['format']}, {a['duration_s']} s)" for a in audios))

    ru = None
    if args.resource_util:
        try:
            import resource_utilization as ru
        except ImportError as e:
            sys.exit(f"Resource utilization unavailable ({e}). Keep resource_utilization.py next to this script, "
                     "pip install requests matplotlib, or pass --no-resource-util")

    run_id = time.strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": run_id, "target_name": TARGET_NAME, "endpoint": f"POST {ENDPOINT} (stream=true, SSE)",
        "base_url": BASE_URL, "server_info": server_info, "tokenizer": tok_src,
        "inputs": [{"audio_file": a["name"], "duration_s": a["duration_s"], "size_kb": round(len(a["bytes"]) / 1024, 1),
                    "format": a["format"], "codec": a["codec"], "sample_rate_hz": a["sample_rate_hz"],
                    "channels": a["channels"], "bit_rate_kbps": a["bit_rate_kbps"]}
                   for a in audios],
        "run_args": {k: v for k, v in vars(args).items() if k not in ("out_dir", "base_url")},
        "points": [],
    }

    if args.warmup:
        print("Running warmup...")
        asyncio.run(warmup(audios, args))
        print("Warmup completed.")

    # Monitoring window covers only measured runs: starts after warmup, stops after the last point.
    log_dir = container = None
    if ru is not None:
        log_dir, container = ru.start_perf_tool(args.metrics_image, str(out_dir))
        summary["resource_utilization"] = {"log_dir": log_dir, "start_epoch": round(time.time(), 3)}
    try:
        print("Starting benchmark...")
        asyncio.run(measure(audios, args, summary, out_dir))
        print("Benchmark completed.")
    finally:
        if ru is not None:
            summary["resource_utilization"]["end_epoch"] = round(time.time(), 3)
            ru.stop_perf_tool(container, log_dir)
            ru.plot_graphs(log_dir)
            _write_summary(out_dir, summary)
    print(f"\nResults: {out_dir}")


if __name__ == "__main__":
    main()
