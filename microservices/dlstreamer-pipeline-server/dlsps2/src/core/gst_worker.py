#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Multi-pipeline GStreamer worker for DLSPS 2.0.

A long-lived process that can host multiple concurrent GStreamer
pipelines, each identified by an ``instance_id``, within a single OS
process. ``pipeline_manager.py`` launches exactly one instance of this
worker (shared by every pipeline instance); a pipeline is validated first
by :mod:`core.gst_validator` before ever being submitted here.

Protocol
--------
Control commands are read from stdin, one JSON object per line::

    {"cmd": "start", "instance_id": "<id>", "pipeline": "<gst-launch string>"}
    {"cmd": "stop", "instance_id": "<id>"}
    {"cmd": "shutdown"}

Status events are written to stdout, one JSON object per line::

    {"instance_id": "<id>", "event": "started"}
    {"instance_id": "<id>", "event": "fps", "avg_fps": 30.0, "last_fps": 29.4}
    {"instance_id": "<id>", "event": "eos"}
    {"instance_id": "<id>", "event": "error", "reason": "..."}
    {"instance_id": "<id>", "event": "stopped"}
"""

import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

# When launched directly as a subprocess, sys.path[0] is the "core"
# directory rather than "src". Add the parent "src" directory so that the
# "core.publishers" package can be imported for sink-element registration.
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import gi  # pyright: ignore[reportMissingImports]

gi.require_version("Gst", "1.0")
gi.require_version("GObject", "2.0")
from gi.repository import Gst, GLib  # noqa: E402 # pyright: ignore[reportMissingImports]

logger = logging.getLogger("gst_worker")

# How often (seconds) each hosted pipeline's own frame counter is turned
# into an fps event, and the size of the "last_fps" window.
_FPS_POLL_INTERVAL_SECONDS = 1


def _emit(payload: dict) -> None:
    """Write one JSON status line to stdout and flush immediately."""
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


class _JsonLogFormatter(logging.Formatter):
    """Format each log record as a single JSON line on stderr.

    ``pipeline_manager.py`` reads this worker's stderr and needs to know
    each record's actual severity so it can re-log it at the same level in
    the parent process (an INFO line must not be surfaced as an ERROR).
    Encoding as JSON (rather than a "name - LEVEL - message" text format)
    keeps this robust even for messages that contain embedded newlines.
    """

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        })


@dataclass
class _Instance:
    """State tracked for a single pipeline hosted by this worker."""

    instance_id: str
    pipeline: Gst.Pipeline
    bus: Optional[Gst.Bus] = field(default=None, repr=False)
    bus_handler_id: int = 0
    fps_source: Optional[GLib.Source] = field(default=None, repr=False)
    # Self-computed FPS state. frame_count is incremented from the
    # GStreamer streaming thread (inside the pad probe callback) and read
    # from the shared main loop thread (inside the poll timer), hence the
    # lock. frame_count resets every poll (drives the windowed "last_fps");
    # total_frame_count never resets (drives the cumulative "avg_fps").
    frame_count: int = 0
    total_frame_count: int = 0
    frame_count_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    start_time: float = field(default_factory=time.monotonic)
    last_poll_time: float = field(default_factory=time.monotonic)


class GstWorker:
    """Hosts and manages multiple concurrent GStreamer pipelines in one process."""

    def __init__(self) -> None:
        self._instances: Dict[str, _Instance] = {}
        self._lock = threading.RLock()
        # One main loop, shared by every hosted pipeline, running for the
        # lifetime of the worker process.
        self._loop: Optional[GLib.MainLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # GStreamer / logging setup
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Initialize GStreamer once for the lifetime of this worker process."""
        Gst.init(None)
        version = Gst.version()
        logger.info(
            "GStreamer initialized — version: %d.%d.%d",
            version.major,
            version.minor,
            version.micro,
        )
        try:
            from core.publishers import register_all  # noqa: PLC0415

            register_all()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Publisher element registration failed: %s", exc)

        Gst.debug_remove_log_function(None)
        Gst.debug_add_log_function(self._gst_log_bridge, None)

        self._loop = GLib.MainLoop.new(None, False)
        self._loop_thread = threading.Thread(
            target=self._run_loop, name="glib-mainloop", daemon=True
        )
        self._loop_thread.start()

    def _run_loop(self) -> None:
        """Thread body: run the single main loop shared by every pipeline."""
        try:
            self._loop.run()
        except Exception:  # pylint: disable=broad-except
            logger.exception("Shared GLib main loop terminated unexpectedly")

    def _gst_log_bridge(self, category, level, file, function, line, obj, message, user_data) -> None:
        """GStreamer log callback: plain passthrough to the worker's own logger.

        Checks the target Python log level *before* touching ``message``:
        ``message.get()`` does GStreamer's own printf-style formatting in C,
        which isn't free, and this callback fires for every log message
        across every hosted pipeline. No point paying for that when the
        result would just be filtered out by the logger anyway.
        """
        if level <= Gst.DebugLevel.ERROR:
            py_level = logging.ERROR
        elif level <= Gst.DebugLevel.WARNING:
            py_level = logging.WARNING
        elif level <= Gst.DebugLevel.INFO:
            py_level = logging.INFO
        else:
            py_level = logging.DEBUG

        if not logger.isEnabledFor(py_level):
            return

        text = message.get()
        text = text.replace("\r", " ").replace("\n", " ")
        logger.log(py_level, "%s", text)

    @staticmethod
    def _attach_fps_probes(pipeline: Gst.Pipeline, inst: "_Instance") -> int:
        """Attach a buffer-counting probe that counts exactly one frame per
        buffer flowing through the pipeline.

        Uses ``iterate_sinks()`` (elements with no linked src pad, i.e. the
        actual terminal element(s) of the pipeline) but only attaches the
        probe to the FIRST such sink pad found, not every one.

        Normally there is only one terminal sink anyway. However,
        ``config.compat.apply_destination()`` fans a single stream out to
        multiple destinations via a ``tee`` when more than one destination is
        requested -- each branch ends in its own terminal sink, and since a
        ``tee`` duplicates every buffer to all of its branches, each branch
        receives the exact same frames at the exact same rate. Counting on
        every terminal sink would therefore count the same logical frame once
        per destination (e.g. 3 destinations would report 3x the real fps);
        counting on just the first one still counts every frame exactly once
        regardless of how many destinations it's duplicated to.

        Returns the number of probes attached (0 or 1).
        """
        sinks_iter = pipeline.iterate_sinks()
        while True:
            result, elem = sinks_iter.next()
            if result != Gst.IteratorResult.OK:
                break
            pads_iter = elem.iterate_sink_pads()
            while True:
                pad_result, pad = pads_iter.next()
                if pad_result != Gst.IteratorResult.OK:
                    break
                pad.add_probe(Gst.PadProbeType.BUFFER, GstWorker._on_buffer_probe, inst)
                return 1
        return 0

    @staticmethod
    def _on_buffer_probe(pad, info, inst: "_Instance"):
        """Pad probe callback: count one frame. Runs on a streaming thread."""
        with inst.frame_count_lock:
            inst.frame_count += 1
            inst.total_frame_count += 1
        return Gst.PadProbeReturn.OK

    def _poll_fps(self, inst: "_Instance") -> bool:
        """GLib timeout callback: emit this instance's own avg/last FPS.

        ``last_fps`` covers just the window since the previous poll (about
        _FPS_POLL_INTERVAL_SECONDS); ``avg_fps`` covers the pipeline's whole
        lifetime so far. Returns GLib.SOURCE_CONTINUE to keep firing every
        _FPS_POLL_INTERVAL_SECONDS until the pipeline's main loop exits.
        """
        now = time.monotonic()
        with inst.frame_count_lock:
            window_count = inst.frame_count
            inst.frame_count = 0
            total_count = inst.total_frame_count
        window_elapsed = now - inst.last_poll_time
        inst.last_poll_time = now
        total_elapsed = now - inst.start_time
        if window_elapsed > 0 and total_elapsed > 0:
            _emit({
                "instance_id": inst.instance_id,
                "event": "fps",
                "avg_fps": total_count / total_elapsed,
                "last_fps": window_count / window_elapsed,
            })
        return GLib.SOURCE_CONTINUE

    # ------------------------------------------------------------------
    # Pipeline lifecycle
    # ------------------------------------------------------------------

    def start(self, instance_id: str, pipeline_description: str) -> None:
        """Parse and start a new pipeline hosted by this worker.

        Bus watches and the FPS-poll timer are attached to the shared
        default ``GLib.MainContext`` (serviced by the one long-lived main
        loop thread started in :meth:`initialize`) rather than a private
        context/loop pair, so starting a pipeline never spawns a new
        long-lived thread.
        """
        with self._lock:
            if instance_id in self._instances:
                _emit({"instance_id": instance_id, "event": "error", "reason": "duplicate instance_id"})
                return

        try:
            pipeline = Gst.parse_launch(pipeline_description)
        except Exception as exc:  # noqa: BLE001
            _emit({"instance_id": instance_id, "event": "error", "reason": f"parse failed: {exc!r}"})
            return

        if not isinstance(pipeline, Gst.Pipeline):
            _emit({
                "instance_id": instance_id,
                "event": "error",
                "reason": "pipeline description did not produce a Gst.Pipeline",
            })
            return

        try:
            pipeline.set_property("name", instance_id)
        except Exception as exc:  # noqa: BLE001
            _emit({"instance_id": instance_id, "event": "error", "reason": f"invalid instance_id as Gst name: {exc!r}"})
            return

        inst = _Instance(instance_id=instance_id, pipeline=pipeline)

        with self._lock:
            self._instances[instance_id] = inst

        bus = pipeline.get_bus()
        bus.add_signal_watch()
        inst.bus = bus

        def _on_message(_bus, message):
            mtype = message.type
            if mtype == Gst.MessageType.ERROR:
                err, _debug = message.parse_error()
                _emit({"instance_id": instance_id, "event": "error", "reason": err.message})
                self._teardown_async(instance_id)
            elif mtype == Gst.MessageType.EOS:
                _emit({"instance_id": instance_id, "event": "eos"})
                self._teardown_async(instance_id)
            return True

        inst.bus_handler_id = bus.connect("message", _on_message)

        # Count frames ourselves via pad probes on this pipeline's own
        # sink element(s), then turn that into avg/last FPS values on a
        # timer attached to the shared default context. Frame counting is
        # still fully isolated per instance — no shared/native aggregation.
        self._attach_fps_probes(pipeline, inst)
        inst.start_time = time.monotonic()
        inst.last_poll_time = inst.start_time
        fps_source = GLib.timeout_source_new_seconds(_FPS_POLL_INTERVAL_SECONDS)
        fps_source.set_callback(self._poll_fps, inst)
        fps_source.attach(None)
        inst.fps_source = fps_source

        pipeline.set_state(Gst.State.PLAYING)
        _emit({"instance_id": instance_id, "event": "started"})

    def stop(self, instance_id: str) -> None:
        """Request a graceful stop of one hosted pipeline (does not affect others)."""
        with self._lock:
            known = instance_id in self._instances
        if not known:
            _emit({"instance_id": instance_id, "event": "error", "reason": "unknown instance_id"})
            return
        self._teardown_async(instance_id)

    def _teardown_async(self, instance_id: str) -> None:
        """Tear down one instance on a short-lived, dedicated thread.

        ``Gst.State.NULL`` transitions can block for a noticeable amount of
        time, so teardown must never run inline on the shared main loop
        thread — doing so would stall bus/timer dispatch for every *other*
        hosted pipeline. A stop request and a racing EOS/ERROR bus message
        can both try to tear down the same instance; popping it from
        ``self._instances`` under the lock makes only one of them win.
        """
        threading.Thread(
            target=self._teardown,
            args=(instance_id,),
            name=f"teardown-{instance_id[:8]}",
            daemon=True,
        ).start()

    def _teardown(self, instance_id: str) -> None:
        with self._lock:
            inst = self._instances.pop(instance_id, None)
        if inst is None:
            return  # already torn down by a racing stop/EOS/error

        if inst.fps_source is not None:
            inst.fps_source.destroy()
        if inst.bus is not None:
            try:
                inst.bus.disconnect(inst.bus_handler_id)
            except Exception:  # noqa: BLE001
                pass
            inst.bus.remove_signal_watch()
        inst.pipeline.set_state(Gst.State.NULL)

        del inst.pipeline
        _emit({"instance_id": instance_id, "event": "stopped"})

    def shutdown(self) -> None:
        """Stop every hosted pipeline, then stop the shared main loop."""
        with self._lock:
            instance_ids = list(self._instances.keys())

        threads = [
            threading.Thread(target=self._teardown, args=(instance_id,), daemon=True)
            for instance_id in instance_ids
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        if self._loop is not None:
            self._loop.quit()
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Control loop (reads commands from stdin)
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Initialize GStreamer, then process control commands until shutdown."""
        self.initialize()
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                command = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.error("Invalid control command (not JSON): %s (%r)", line, exc)
                continue

            cmd = command.get("cmd")
            if cmd == "start":
                self.start(command["instance_id"], command["pipeline"])
            elif cmd == "stop":
                self.stop(command["instance_id"])
            elif cmd == "shutdown":
                break
            else:
                logger.error("Unknown command: %s", command)

        self.shutdown()
        return 0


def main() -> int:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonLogFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    worker = GstWorker()
    return worker.run()


if __name__ == "__main__":
    sys.exit(main())
