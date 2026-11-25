#!/usr/bin/env python3
"""Audio Analyzer realtime (WebSocket) transcription benchmark.

Benchmarks ``WS /v1/realtime?intent=transcription``: a single socket acts as a live
speaker, streaming PCM16 frames (``input_audio_buffer.append``) at a fixed pace, while the
server's energy VAD cuts the stream into utterances and transcribes each one
(``input_audio_buffer.committed`` -> ``conversation.item.input_audio_transcription.completed``).
Each provided input file is streamed once, sequentially.

The server VAD is deterministic, so the client replays it on the same audio and knows, for
every server commit, where the speech ended on the audio timeline. Per committed utterance:

    speech end ── VAD silence wait ──> committed ── ASR (+ queue) ──> completed
    |<─────────── vad_delay_s ───────>|<──────── asr_s ────────────>|
    |<───────────────────────── eos_to_final_s ────────────────────>|

    eos_to_final_s  send time of the frame holding the last speech sample -> completed received
                    (the latency a live user feels after they stop talking)
    vad_delay_s     same start -> committed received (~silence_duration_ms + backlog)
    asr_s           committed -> completed (ASR + any wait for the shared model)
    rtf             asr_s / committed audio duration

The service returns the accumulated session transcript in every ``completed`` event; the
utterance text is taken as the suffix beyond the previous snapshot. Servers that return per-utterance text are detected and joined instead.

Input: any user-provided audio/video file(s) via ``--input``, or every audio file in
``data/realtime/`` (default sample: ``1272-141231.wav``). Each input is converted once, before
timing, to the ``/v1/realtime`` wire format: raw PCM16 little-endian, mono, 16 kHz (ffmpeg
decodes any format/sample rate/channel layout; an input already in that format is read as-is).
The PCM is split into ``--frame-ms`` frames and base64-encoded into ``input_audio_buffer.append``
events.

Examples:
  python3 bench_realtime.py --no-resource-util
  python3 bench_realtime.py --input ~/calls/customer.mp3 --save-converted
  python3 bench_realtime.py --speed 0          # burst: max throughput, no pacing

Run sequence: warmup -> start resource monitor -> measured run -> stop monitor -> plot graphs.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json
import math
import re
import shutil
import subprocess
import sys
import time
import wave
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode, urlparse

try:
    import aiohttp
except ImportError:
    sys.exit("Missing dependency: pip install 'aiohttp>=3.8'")

try:
    import numpy as np
except ImportError:
    sys.exit("Missing dependency: pip install numpy")

from bench_audio_analyzer import AUDIO_EXT, _cell, _ffprobe_info, _write_summary, dist, fetch_server_info

TARGET_NAME = "Audio Analyzer - realtime transcription (WebSocket)"
BASE_URL = "http://localhost:8010"
ENDPOINT = "/v1/realtime"

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data" / "realtime"
NAN = math.nan

# Must mirror the server (api/realtime_endpoints.py, utils/pcm_audio.py) for an exact VAD replay.
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
BYTES_PER_SEC = SAMPLE_RATE * BYTES_PER_SAMPLE
VAD_FRAME_MS = 30
MIN_UTTERANCE_SECONDS = 0.20
MAX_UTTERANCE_SECONDS = 120.0

UTT_COLS = ["stream_id", "audio_file", "utt_index", "reason", "audio_start_s", "audio_end_s",
            "audio_dur_s", "eos_to_final_s", "vad_delay_s", "asr_s", "rtf", "words", "transcript"]
UTT_METRICS = ["eos_to_final_s", "vad_delay_s", "asr_s", "rtf"]
STREAM_COLS = ["stream_id", "audio_file", "session_id", "ok", "error", "audio_s", "wall_s",
               "drain_s", "predicted_commits", "server_commits", "completed", "empty", "commit_mismatch",
               "hyp_words"]
STREAM_METRICS = ["wall_s", "drain_s"]


# ---------- input ----------

def to_realtime_pcm(path: Path) -> tuple[bytes, str]:
    """Convert any audio/video file to the /v1/realtime wire format: PCM16 LE, mono, 16 kHz.

    The service does not resample on the socket, so the conversion must happen on the client.
    Returns (pcm, how) where ``how`` is ``native`` (already 16 kHz mono PCM16 WAV) or ``ffmpeg``.
    """
    try:
        with wave.open(str(path), "rb") as wf:
            if (wf.getframerate(), wf.getnchannels(), wf.getsampwidth(), wf.getcomptype()) == \
                    (SAMPLE_RATE, 1, BYTES_PER_SAMPLE, "NONE"):
                return wf.readframes(wf.getnframes()), "native"
    except (wave.Error, EOFError):
        pass
    if not shutil.which("ffmpeg"):
        sys.exit(f"{path.name} is not 16 kHz mono PCM16 WAV and ffmpeg is not on PATH to convert it")
    proc = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0", "-vn",
                           "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"],
                          capture_output=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg could not decode {path}: {proc.stderr.decode(errors='replace').strip()[:300]}")
    return proc.stdout, "ffmpeg"


def _resolve_input_files(inputs: list[str] | None, data_dir: Path) -> list[Path]:
    paths = [Path(p).expanduser() for p in inputs] if inputs else [data_dir]
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXT)
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"Input not found: {p}")
    if not files:
        sys.exit(f"No audio files ({', '.join(sorted(AUDIO_EXT))}) found in {', '.join(map(str, paths))}; "
                 "pass --input FILE")
    return files


def load_inputs(inputs: list[str] | None, data_dir: Path, save_dir: Path | None = None) -> list[dict]:
    loaded = []
    for f in _resolve_input_files(inputs, data_dir):
        pcm, how = to_realtime_pcm(f)
        pcm = pcm[:len(pcm) - len(pcm) % BYTES_PER_SAMPLE]
        if not pcm:
            sys.exit(f"{f} contains no audio")
        if save_dir is not None:
            save_dir.mkdir(parents=True, exist_ok=True)
            with wave.open(str(save_dir / f"{f.stem}.realtime.wav"), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(BYTES_PER_SAMPLE)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm)
        loaded.append({"name": f.name, "path": str(f), "pcm": pcm, "conversion": how,
                       "source_info": _ffprobe_info(f)})
    return loaded


# ---------- server VAD replay ----------

def _frame_rms(pcm: bytes) -> np.ndarray:
    frame_bytes = int(SAMPLE_RATE * VAD_FRAME_MS / 1000) * BYTES_PER_SAMPLE
    n = len(pcm) // frame_bytes
    s = np.frombuffer(pcm[:n * frame_bytes], dtype="<i2").astype(np.float32).reshape(n, -1)
    return np.sqrt(np.mean(np.square(s), axis=1)) / 32768.0


def replay_server_vad(pcm: bytes, msg_bytes: int, threshold: float, silence_ms: int) -> list:
    """Predict the server's commits for ``pcm`` sent in ``msg_bytes`` appends.

    Mirrors EnergyVad.process + _handle_append + session.close: the VAD runs over 30 ms frames of
    the continuous stream; a stop commits the whole buffer up to the end of the append message that
    completed the stop frame; buffers shorter than MIN_UTTERANCE_SECONDS are discarded without a
    ``committed`` event; the remainder is committed on ``session.close``.

    Returns the list of predicted commits.
    """
    frame_bytes = int(SAMPLE_RATE * VAD_FRAME_MS / 1000) * BYTES_PER_SAMPLE
    rms = _frame_rms(pcm)
    n_msgs = math.ceil(len(pcm) / msg_bytes)
    stops_by_msg: dict[int, float] = {}
    active, silence, speech = False, 0.0, 0.0
    last_speech_end = None
    for j, r in enumerate(rms):
        end_byte = (j + 1) * frame_bytes
        msg = (end_byte - 1) // msg_bytes
        if r >= threshold:
            silence = 0.0
            speech += VAD_FRAME_MS
            last_speech_end = end_byte / BYTES_PER_SEC
            if not active and speech >= VAD_FRAME_MS:
                active = True
        elif active:
            silence += VAD_FRAME_MS
            if silence >= silence_ms:
                active, speech, silence = False, 0.0, 0.0
                stops_by_msg[msg] = last_speech_end
        else:
            speech = 0.0

    commits, buf_start, last_speech = [], 0, None
    rms_ends = [((j + 1) * frame_bytes / BYTES_PER_SEC, r >= threshold) for j, r in enumerate(rms)]
    for m in range(n_msgs):
        end = min((m + 1) * msg_bytes, len(pcm))
        reason = "server_vad" if m in stops_by_msg else (
            "max_duration" if (end - buf_start) / BYTES_PER_SEC >= MAX_UTTERANCE_SECONDS else None)
        if reason:
            if (end - buf_start) / BYTES_PER_SEC >= MIN_UTTERANCE_SECONDS:
                speech_end = stops_by_msg.get(m) or _last_speech_in(rms_ends, buf_start, end)
                commits.append({"reason": reason, "start": buf_start / BYTES_PER_SEC,
                                "end": end / BYTES_PER_SEC, "speech_end": speech_end})
            buf_start = end
    if (len(pcm) - buf_start) / BYTES_PER_SEC >= MIN_UTTERANCE_SECONDS:
        commits.append({"reason": "session_close", "start": buf_start / BYTES_PER_SEC,
                        "end": len(pcm) / BYTES_PER_SEC,
                        "speech_end": _last_speech_in(rms_ends, buf_start, len(pcm))})
    return commits


def _last_speech_in(rms_ends, start_byte, end_byte):
    lo, hi = start_byte / BYTES_PER_SEC, end_byte / BYTES_PER_SEC
    ends = [t for t, sp in rms_ends if sp and lo < t <= hi]
    return ends[-1] if ends else None


# ---------- text ----------

def _words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]+", " ", (text or "").lower().replace("-", " ")).split()


# ---------- one live stream ----------

@dataclass
class StreamRec:
    stream_id: int
    audio_file: str
    session_id: str = ""
    ok: bool = False
    error: str = ""
    audio_s: float = 0.0
    wall_s: float = NAN
    drain_s: float = NAN
    predicted: list = field(default_factory=list)
    utterances: list = field(default_factory=list)
    server_commits: int = 0
    completed: int = 0
    hyp_words: int = 0
    transcript: str = ""
    cumulative: bool = False

    def row(self):
        return [self.stream_id, self.audio_file, self.session_id, int(self.ok), self.error,
                _f(self.audio_s), _f(self.wall_s), _f(self.drain_s), len(self.predicted), self.server_commits,
                self.completed, self.server_commits - self.completed, abs(len(self.predicted) - self.server_commits),
                self.hyp_words]


def _f(x):
    if x is None:
        return ""
    if isinstance(x, (int, str)):
        return x
    return "" if x != x else f"{x:.6f}"


def _ws_url(base_url: str, language: str | None) -> str:
    u = urlparse(base_url)
    scheme = "wss" if u.scheme == "https" else "ws"
    query = {"intent": "transcription", **({"language": language} if language else {})}
    return f"{scheme}://{u.netloc}{ENDPOINT}?{urlencode(query)}"


async def fetch_server_vad(base_url: str, language: str | None) -> dict:
    """Read the realtime session's default VAD settings before overriding the session."""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None)) as session:
        async with session.ws_connect(_ws_url(base_url, language), max_msg_size=0,
                                     heartbeat=None, autoping=True) as ws:
            msg = await ws.receive(timeout=30)
            if msg.type != aiohttp.WSMsgType.TEXT:
                raise RuntimeError(f"expected realtime session event, got WebSocket message {msg.type}")
            try:
                event = json.loads(msg.data)
            except json.JSONDecodeError as exc:
                raise RuntimeError("server returned invalid JSON in transcription_session.created") from exc
            if not isinstance(event, dict) or event.get("type") != "transcription_session.created":
                raise RuntimeError(f"unexpected first realtime event while reading server VAD settings: {event}")
            server_session = event.get("session")
            turn_detection = server_session.get("turn_detection") if isinstance(server_session, dict) else None
            if not isinstance(turn_detection, dict) or turn_detection.get("type") != "server_vad":
                raise RuntimeError("server session does not report server_vad settings")
            try:
                return {
                    "vad_threshold": float(turn_detection["threshold"]),
                    "silence_ms": int(turn_detection["silence_duration_ms"]),
                    "prefix_padding_ms": int(turn_detection["prefix_padding_ms"]),
                }
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(f"server reported incomplete or invalid server_vad settings: {turn_detection}") from exc


async def run_stream(session, audio, rec: StreamRec, args, measure=True):
    msg_bytes = int(SAMPLE_RATE * args.frame_ms / 1000) * BYTES_PER_SAMPLE
    pcm = audio["pcm"] + b"\x00\x00" * int(SAMPLE_RATE * args.tail_silence_ms / 1000)
    if not measure:
        pcm = audio["pcm"][:int(args.warmup_sec * BYTES_PER_SEC)] + b"\x00\x00" * int(SAMPLE_RATE * 1.0)
    rec.audio_s = len(pcm) / BYTES_PER_SEC
    rec.predicted = replay_server_vad(pcm, msg_bytes, args.vad_threshold, args.silence_ms)
    frames = [base64.b64encode(pcm[i:i + msg_bytes]).decode() for i in range(0, len(pcm), msg_bytes)]
    speed = args.speed if measure else 0.0
    frame_s = args.frame_ms / 1000

    committed, completed, errors = [], {}, []
    send_t: list[float] = []

    async with session.ws_connect(_ws_url(args.base_url, args.language), max_msg_size=0,
                                  heartbeat=None, autoping=True) as ws:
        created = json.loads((await ws.receive(timeout=30)).data)
        if created.get("type") != "transcription_session.created":
            raise RuntimeError(f"unexpected first event: {created}")
        rec.session_id = created.get("session", {}).get("id", "")

        patch = {"sample_rate": SAMPLE_RATE, "input_audio_format": "pcm16",
                 "turn_detection": {"type": "server_vad", "threshold": args.vad_threshold,
                                    "silence_duration_ms": args.silence_ms,
                                    "prefix_padding_ms": args.prefix_padding_ms}}
        if args.diarization is not None:
            patch["diarization"] = args.diarization == "on"
        await ws.send_str(json.dumps({"type": "session.update", "session": patch}))
        upd = json.loads((await ws.receive(timeout=30)).data)
        if upd.get("type") != "transcription_session.updated":
            raise RuntimeError(f"session.update rejected: {upd}")

        async def receiver():
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                now = time.perf_counter()
                evt = json.loads(msg.data)
                typ = evt.get("type", "")
                if typ == "input_audio_buffer.committed":
                    committed.append((now, evt.get("item_id"), evt.get("reason")))
                elif typ == "conversation.item.input_audio_transcription.completed":
                    completed[evt.get("item_id")] = (now, evt.get("transcript") or "")
                elif typ == "error":
                    errors.append((evt.get("error") or {}).get("message", "")[:200])

        recv_task = asyncio.create_task(receiver())
        t0 = time.perf_counter()
        for i, frame in enumerate(frames):
            if speed > 0:
                delay = t0 + (i + 1) * frame_s / speed - time.perf_counter()
                if delay > 0:
                    await asyncio.sleep(delay)
            await ws.send_str(json.dumps({"type": "input_audio_buffer.append", "audio": frame}))
            send_t.append(time.perf_counter())
        await ws.send_str(json.dumps({"type": "session.close"}))
        t_sent = time.perf_counter()
        await recv_task
        t_end = time.perf_counter()

    rec.wall_s = t_end - t0
    events = [t for t, _, _ in committed] + [t for t, _ in completed.values()]
    rec.drain_s = (max(events) if events else t_end) - t_sent
    rec.server_commits = len(committed)
    rec.completed = len(completed)

    def sent_at(audio_t):
        idx = min(len(send_t) - 1, max(0, math.ceil(audio_t * BYTES_PER_SEC / msg_bytes) - 1))
        return send_t[idx]

    # The service returns the accumulated session transcript in every `completed` event; the
    # utterance text is the suffix beyond the previous snapshot. Per-utterance servers are joined.
    texts, snapshot, cumulative = [], "", True
    for k, (t_commit, item_id, reason) in enumerate(committed):
        pred = rec.predicted[k] if k < len(rec.predicted) else None
        done = completed.get(item_id)
        new_text = ""
        if done:
            full = done[1].strip()
            if snapshot and full.startswith(snapshot):
                new_text = full[len(snapshot):].strip()
            else:
                cumulative = cumulative and not snapshot
                new_text = full
            snapshot = full
        u = {"utt_index": k, "reason": reason, "transcript": new_text,
             "audio_start_s": pred["start"] if pred else None, "audio_end_s": pred["end"] if pred else None,
             "audio_dur_s": (pred["end"] - pred["start"]) if pred else NAN,
             "eos_to_final_s": NAN, "vad_delay_s": NAN, "asr_s": NAN, "rtf": NAN}
        if done:
            texts.append(new_text)
            u["asr_s"] = done[0] - t_commit
            if u["audio_dur_s"] == u["audio_dur_s"] and u["audio_dur_s"] > 0:
                u["rtf"] = u["asr_s"] / u["audio_dur_s"]
        if pred and pred["speech_end"] is not None and pred["reason"] == reason:
            t_speech = sent_at(pred["speech_end"])
            u["vad_delay_s"] = t_commit - t_speech
            if done:
                u["eos_to_final_s"] = done[0] - t_speech
        u["words"] = len(_words(u["transcript"]))
        rec.utterances.append(u)

    rec.cumulative = cumulative and len(texts) > 1
    rec.transcript = snapshot if rec.cumulative else " ".join(t for t in texts if t)
    rec.hyp_words = len(_words(rec.transcript))

    if errors:
        rec.error = f"{len(errors)} error event(s): {errors[0]}"
    elif not completed:
        rec.error = "no transcripts"
    rec.ok = not rec.error


async def execute(session, audio, rec, args, measure=True):
    try:
        await asyncio.wait_for(run_stream(session, audio, rec, args, measure), args.timeout)
    except asyncio.TimeoutError:
        rec.ok, rec.error = False, "timeout"
    except Exception as e:  # noqa: BLE001 - any failure is recorded, the run continues
        rec.ok, rec.error = False, f"{type(e).__name__}: {e}"


# ---------- statistics ----------

class Stats:
    def __init__(self):
        self.n = self.ok = 0
        self.errors = Counter()
        self.utt = {k: [] for k in UTT_METRICS}
        self.stream = {k: [] for k in STREAM_METRICS}
        self.counts = Counter()

    def add(self, r: StreamRec):
        self.n += 1
        self.counts["utterances"] += r.server_commits
        self.counts["empty_utterances"] += r.server_commits - r.completed
        self.counts["commit_mismatch_streams"] += int(len(r.predicted) != r.server_commits)
        if not r.ok:
            self.errors[r.error[:120]] += 1
            return
        self.ok += 1
        for u in r.utterances:
            for k in UTT_METRICS:
                self.utt[k].append(u[k])
        self.stream["wall_s"].append(r.wall_s)
        self.stream["drain_s"].append(r.drain_s)

    def summary(self, wall):
        return {"streams": self.n, "success": self.ok, "errors": self.n - self.ok,
                "top_errors": self.errors.most_common(5), "wall_time_s": round(wall, 3), **dict(self.counts),
                **{k: dist(v) for k, v in self.utt.items()},
                **{k: dist(v) for k, v in self.stream.items()}}


# ---------- load generation ----------

class Runner:
    def __init__(self, session, inputs, args, writers=None, text_fh=None):
        self.session, self.inputs, self.args = session, inputs, args
        self.stats = Stats()
        self.writers, self.text_fh = writers, text_fh
        self.records: list[StreamRec] = []

    async def one(self, i, measure=True):
        audio = self.inputs[i % len(self.inputs)]
        rec = StreamRec(i, audio["name"])
        await execute(self.session, audio, rec, self.args, measure)
        if not measure:
            return
        self.records.append(rec)
        self.stats.add(rec)
        utt_w, stream_w = self.writers
        for u in rec.utterances:
            utt_w.writerow([rec.stream_id, rec.audio_file, *(_f(u[k]) for k in UTT_COLS[2:])])
        stream_w.writerow(rec.row())
        status = "ok" if rec.ok else f"error: {rec.error}"
        self.text_fh.write(f"===== stream_id={rec.stream_id} audio_file={rec.audio_file} "
                           f"session={rec.session_id} ({status}) =====\n{rec.transcript}\n\n")
        self.text_fh.flush()


def _session():
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None))


async def warmup(inputs, args):
    """Short burst-mode streams that load the model; never recorded."""
    async with _session() as session:
        runner = Runner(session, inputs, args)
        for i in range(args.warmup):
            await runner.one(i, measure=False)


COLS = [("n", 4, lambda d: d["streams"]),
        ("err", 4, lambda d: d["errors"]), ("utts", 6, lambda d: d.get("utterances"))] + [
    (name, w, (lambda k, q: lambda d: (d.get(k) or {}).get(q))(key, q))
    for name, key, q, w in [("eos_p50", "eos_to_final_s", "p50", 9), ("eos_p90", "eos_to_final_s", "p90", 9),
                            ("asr_p50", "asr_s", "p50", 9), ("rtf_p50", "rtf", "p50", 9),
                            ("drain", "drain_s", "mean", 9)]]


async def measure(inputs, args, summary, out_dir):
    print(" ".join(_cell(t, w) for t, w, _ in COLS))
    async with _session() as session:
        with (out_dir / "raw_realtime_utterances.csv").open("w", newline="", encoding="utf-8") as ufh, \
                (out_dir / "raw_realtime_streams.csv").open("w", newline="", encoding="utf-8") as sfh, \
                (out_dir / "transcripts.txt").open("w", encoding="utf-8") as text_fh:
            utt_w, stream_w = csv.writer(ufh), csv.writer(sfh)
            utt_w.writerow(UTT_COLS)
            stream_w.writerow(STREAM_COLS)
            runner = Runner(session, inputs, args, (utt_w, stream_w), text_fh)
            start_epoch, t0 = time.time(), time.perf_counter()
            for i in range(len(inputs)):
                await runner.one(i)
            res = {"start_epoch": round(start_epoch, 3),
                   "end_epoch": round(time.time(), 3), **runner.stats.summary(time.perf_counter() - t0),
                   "cumulative_transcripts": any(r.cumulative for r in runner.records)}
            summary["points"].append(res)
            ufh.flush()
            sfh.flush()
            print(" ".join(_cell(g(res), w) for _, w, g in COLS))
            _write_summary(out_dir, summary)


def main():
    global BASE_URL
    ap = argparse.ArgumentParser(description=f"Benchmark: {TARGET_NAME}")
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--input", nargs="+", metavar="PATH",
                    help="audio/video file(s) or folder(s), any ffmpeg-readable format "
                         "(default: every audio file in --data-dir)")
    ap.add_argument("--data-dir", default=str(DATA_DIR),
                    help="default input folder when --input is not given (default: data/realtime/)")
    ap.add_argument("--save-converted", action="store_true",
                    help="also write each converted stream to <run>/converted/<name>.realtime.wav")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="pacing: 1.0 = real time (default), 2.0 = 2x faster, 0 = burst (no pacing)")
    ap.add_argument("--frame-ms", type=int, default=100, help="audio per input_audio_buffer.append (default: 100)")
    ap.add_argument("--tail-silence-ms", type=int, default=1000,
                    help="silence appended after the clip so the last utterance is VAD-committed (default: 1000)")
    ap.add_argument("--language", default="en", help="language query parameter ('' to auto-detect)")
    ap.add_argument("--diarization", choices=["on", "off"], default=None,
                    help="per-session diarization override (default: server config)")
    ap.add_argument("--warmup", type=int, default=1, help="unrecorded warmup streams (burst, truncated)")
    ap.add_argument("--warmup-sec", type=float, default=20.0, help="audio seconds per warmup stream")
    ap.add_argument("--timeout", type=float, default=1800.0, help="per-stream timeout in seconds")
    ap.add_argument("--out-dir", default=str(HERE / "results"))
    ap.add_argument("--resource-util", action=argparse.BooleanOptionalAction, default=True,
                    help="collect CPU/GPU/NPU/memory/temperature during measured runs (resource_utilization.py)")
    ap.add_argument("--metrics-image", default=None,
                    help="Metrics Manager image (default: resource_utilization.py default)")
    args = ap.parse_args()
    if args.speed < 0 or args.frame_ms < 10:
        ap.error("--speed must be >= 0 and --frame-ms >= 10")
    BASE_URL = args.base_url

    server_vad = asyncio.run(fetch_server_vad(BASE_URL, args.language))
    for name, value in server_vad.items():
        setattr(args, name, value)

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-realtime"
    out_dir = Path(args.out_dir) / run_id
    inputs = load_inputs(args.input, Path(args.data_dir), out_dir / "converted" if args.save_converted else None)
    server_info = asyncio.run(fetch_server_info(BASE_URL))
    msg_bytes = int(SAMPLE_RATE * args.frame_ms / 1000) * BYTES_PER_SAMPLE
    for a in inputs:
        pcm = a["pcm"] + b"\x00\x00" * int(SAMPLE_RATE * args.tail_silence_ms / 1000)
        a["predicted_commits"] = len(replay_server_vad(pcm, msg_bytes, args.vad_threshold, args.silence_ms))
        a["duration_s"] = round(len(a["pcm"]) / BYTES_PER_SEC, 3)
        if not a["predicted_commits"]:
            print(f"warning: {a['name']}: no speech above the server VAD threshold {args.vad_threshold}; "
                  "the server will never commit - lower the threshold")
    print(f"Served model: {server_info['asr_model']} ({server_info['asr_provider']}/{server_info['asr_device']})")
    print(f"Server VAD settings: threshold={args.vad_threshold}, silence={args.silence_ms} ms, "
          f"prefix_padding={args.prefix_padding_ms} ms")
    print("Inputs (converted to PCM16 mono 16 kHz): " + ", ".join(
        f"{a['name']} [{a['source_info']['format']}/{a['source_info']['codec']}, "
        f"{a['source_info']['sample_rate_hz']} Hz, {a['source_info']['channels']} ch -> {a['conversion']}] "
        f"{a['duration_s']} s, {a['predicted_commits']} predicted commits" for a in inputs))
    pacing = "burst" if args.speed == 0 else f"{args.speed:g}x real time"
    print(f"Pacing: {pacing}, {args.frame_ms} ms frames, VAD threshold={args.vad_threshold} "
          f"silence={args.silence_ms} ms")

    ru = None
    if args.resource_util:
        try:
            import resource_utilization as ru
        except ImportError as e:
            sys.exit(f"Resource utilization unavailable ({e}). Keep resource_utilization.py next to this script, "
                     "pip install requests matplotlib, or pass --no-resource-util")

    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": run_id, "target_name": TARGET_NAME, "endpoint": f"WS {ENDPOINT}?intent=transcription",
        "base_url": BASE_URL, "server_info": server_info,
        "inputs": [{"audio_file": a["name"], "path": a["path"], "source": a["source_info"],
                    "conversion": a["conversion"],
                    "sent_format": {"format": "pcm16", "sample_rate_hz": SAMPLE_RATE, "channels": 1,
                                    "frame_ms": args.frame_ms},
                    "duration_s": a["duration_s"], "predicted_commits": a["predicted_commits"]}
                   for a in inputs],
        "run_args": {k: v for k, v in vars(args).items() if k not in ("out_dir", "base_url")},
        "points": [],
    }

    if args.warmup:
        print("Running warmup...")
        asyncio.run(warmup(inputs, args))
        print("Warmup completed.")

    log_dir = container = None
    if ru is not None:
        log_dir, container = ru.start_perf_tool(args.metrics_image, str(out_dir))
        summary["resource_utilization"] = {"log_dir": log_dir, "start_epoch": round(time.time(), 3)}
    try:
        print("Starting benchmark...")
        asyncio.run(measure(inputs, args, summary, out_dir))
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
