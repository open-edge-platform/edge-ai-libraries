# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""pipeline_events.py

Live pipeline events (proximity triggers and VLM answers) of pipelines that
run on DLSPS 2.0.

The pipelines run in the DLSPS 2.0 container, so their GStreamer bus is out of
ViPPET's reach. Elements that produce events write them as JSON Lines files
into the metadata folder both containers mount, and ViPPET reads them back:

* ``gvaproximitytrigger_py`` writes one record per trigger to the file named by
  its ``events-file`` property.
* Each ``gvagenai`` gets a ``gvametapublish`` right after it. With no
  ``gvametaconvert`` in between, it writes only the frames that carry a JSON
  meta, so one record per VLM answer: ``gvagenai``'s own JSON with ``result``,
  ``timestamp_seconds`` and, with ``metrics=true``, the ``metrics`` block.
  No element before ``gvagenai`` may add a JSON meta, or that one is written
  instead.

:class:`EventCapture` rewrites the launch strings of one run to add these
outputs, under a folder of its own in ``EVENTS_DIR``, reads the files while
the run lasts and deletes the folder afterwards.
"""

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from managers.metadata_manager import METADATA_DIR
from pipeline_runner import PipelineEvent

logger = logging.getLogger("pipeline_events")

# Private to ViPPET: never listed as job metadata.
EVENTS_DIR: str = os.path.join(METADATA_DIR, ".events")

# How often the event files are read while a run lasts, seconds.
EVENTS_POLL_INTERVAL_S: float = float(os.environ.get("EVENTS_POLL_INTERVAL_S", "0.5"))

# One element of a launch string: the text between "!" separators that are not
# inside double quotes (prompts may contain "!").
LAUNCH_ELEMENT = re.compile(r'(?:[^!"]|"[^"]*")+')

TRIGGER_ELEMENT = "gvaproximitytrigger_py"
TRIGGER_EVENTS_PROPERTY = "events-file"
GENAI_ELEMENT = "gvagenai"

_NAME = re.compile(r'(?:^|\s)name=(?:"([^"]*)"|(\S+))')
_PROMPT = re.compile(r'(?:^|\s)prompt=(?:"([^"]*)"|(\S+))')
_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9_.-]")

# gvagenai's cumulative means in its JSON metadata, and the field each becomes.
GENAI_METRIC_FIELDS = {
    "ttft_ms": "ttft_mean",
    "tpot_ms": "tpot_mean",
    "generate_duration_ms": "generate_duration_mean",
}


@dataclass(frozen=True)
class EventSource:
    """The element that writes one event file.

    Attributes:
        kind: ``"trigger"`` for ``gvaproximitytrigger_py``, ``"vlm"`` for
            ``gvagenai``.
        element: The element's ``name``, when the launch string sets it.
        prompt: The ``gvagenai`` prompt, when the launch string sets it.
        stream_id: The stream whose launch string holds the element.
    """

    kind: str
    element: str | None = None
    prompt: str | None = None
    stream_id: str | None = None


def _property(pattern: re.Pattern, element: str) -> str | None:
    match = pattern.search(element)
    if match is None:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def _safe(text: str) -> str:
    return _UNSAFE_PATH_CHARS.sub("_", text) or "_"


def add_event_outputs(
    command: str, directory: str, stream_id: str
) -> tuple[str, dict[str, EventSource]]:
    """Add the event file outputs to one launch string.

    Every ``gvaproximitytrigger_py`` without an ``events-file`` gets one, and
    every ``gvagenai`` is followed by a ``gvametapublish`` writing JSON Lines.
    Each file is named after the stream and the element's position.

    Returns:
        The new launch string, and the source of each file by path. The
        launch string is unchanged when the mapping is empty.
    """
    sources: dict[str, EventSource] = {}

    def _rewrite(match: re.Match) -> str:
        element = match.group(0)
        tokens = element.split()
        if not tokens or tokens[0] not in (TRIGGER_ELEMENT, GENAI_ELEMENT):
            return element
        if tokens[0] == TRIGGER_ELEMENT and f"{TRIGGER_EVENTS_PROPERTY}=" in element:
            return element
        stripped = element.rstrip()
        trailing = element[len(stripped) :]
        path = os.path.join(directory, f"{_safe(stream_id)}-{len(sources)}.jsonl")
        name = _property(_NAME, element)
        if tokens[0] == TRIGGER_ELEMENT:
            sources[path] = EventSource("trigger", name, stream_id=stream_id)
            return f"{stripped} {TRIGGER_EVENTS_PROPERTY}={path}{trailing}"
        sources[path] = EventSource("vlm", name, _property(_PROMPT, element), stream_id)
        return (
            f"{stripped} ! gvametapublish file-format=json-lines "
            f"file-path={path}{trailing}"
        )

    rewritten = LAUNCH_ELEMENT.sub(_rewrite, command)
    return (rewritten if sources else command), sources


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_record(
    record: dict, source: EventSource
) -> tuple[PipelineEvent | None, dict[str, float] | None]:
    """Turn one event file record into a job event and VLM metric fields.

    Returns:
        The event, or ``None`` for a record without text (for example a
        frame record of a ``gvametaconvert`` before the publisher). The VLM
        fields (``ttft_ms``, ``tpot_ms``, ``generate_duration_ms``) from the
        record's ``metrics`` block, or ``None`` without a complete one.
    """
    now_ms = int(time.time() * 1000)
    if source.kind == "trigger":
        text = record.get("text")
        if not isinstance(text, str) or not text.strip():
            return None, None
        origin = record.get("source")
        element = record.get("element")
        return (
            PipelineEvent(
                timestamp_ms=now_ms,
                source=origin if isinstance(origin, str) else "pipeline",
                text=text.strip(),
                element=element if isinstance(element, str) else source.element,
                pts_seconds=_number(record.get("pts-seconds")),
            ),
            None,
        )

    event = None
    result = record.get("result")
    if isinstance(result, str) and result.strip():
        event = PipelineEvent(
            timestamp_ms=now_ms,
            source="vlm",
            text=result.strip(),
            element=source.element,
            pts_seconds=_number(record.get("timestamp_seconds")),
            prompt=source.prompt,
        )
    fields = None
    metrics = record.get("metrics")
    if isinstance(metrics, dict):
        values = {
            dst: _number(metrics.get(src)) for dst, src in GENAI_METRIC_FIELDS.items()
        }
        if all(v is not None for v in values.values()):
            fields = {k: v for k, v in values.items() if v is not None}
    return event, fields


class EventFileReader:
    """Reads event files as they grow and hands each record on.

    A file is read from where the last read stopped. Bytes after the last
    newline wait for the next read, so a record is never handled half
    written. Blank and malformed records are skipped, as are files that do
    not exist yet.
    """

    def __init__(
        self,
        sources: dict[str, EventSource],
        on_event: Callable[[PipelineEvent], None],
        on_vlm_metrics: Callable[[dict[str, float], str | None], None] | None = None,
        poll_interval: float = EVENTS_POLL_INTERVAL_S,
    ):
        self.sources = sources
        self.on_event = on_event
        self.on_vlm_metrics = on_vlm_metrics
        self.poll_interval = poll_interval
        self._offsets = dict.fromkeys(sources, 0)
        self._partial = dict.fromkeys(sources, b"")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._read_lock = threading.Lock()

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, name="pipeline-events", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop reading, after one last read of everything written so far."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self.read_once()

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_interval):
            self.read_once()

    def read_once(self) -> None:
        with self._read_lock:
            for path, source in self.sources.items():
                try:
                    with open(path, "rb") as stream:
                        stream.seek(self._offsets[path])
                        data = stream.read()
                except OSError:
                    continue
                if not data:
                    continue
                self._offsets[path] += len(data)
                *lines, self._partial[path] = (self._partial[path] + data).split(b"\n")
                for line in lines:
                    self._handle(line, source)

    def _handle(self, line: bytes, source: EventSource) -> None:
        if not line.strip():
            return
        try:
            record = json.loads(line)
        except ValueError:
            logger.debug("Skipping a malformed event record: %r", line[:200])
            return
        if not isinstance(record, dict):
            return
        event, fields = parse_record(record, source)
        try:
            if event is not None:
                self.on_event(event)
            if fields is not None and self.on_vlm_metrics is not None:
                # Tagged like the server's export: the element, else the stream.
                self.on_vlm_metrics(fields, source.element or source.stream_id)
        except Exception:  # noqa: BLE001 - a consumer error must not stop reading
            logger.exception("Pipeline event handler failed")


class EventCapture:
    """The event files of one run: launch strings, folder and reader.

    Create it with :meth:`create`, run the rewritten :attr:`commands`, call
    :meth:`start` once the instances are started and :meth:`close` once they
    stopped. Validation runs use launch strings without event outputs.
    """

    def __init__(
        self,
        directory: str,
        commands: dict[str, str],
        sources: dict[str, EventSource],
        reader: EventFileReader,
    ):
        self.directory = directory
        self.commands = commands
        self.sources = sources
        self.reader = reader
        self._started = False

    @classmethod
    def create(
        cls,
        stream_commands: dict[str, str],
        job_id: str | None,
        on_event: Callable[[PipelineEvent], None],
        on_vlm_metrics: Callable[[dict[str, float], str | None], None] | None = None,
    ) -> "EventCapture | None":
        """Rewrite the launch strings of a run, or ``None`` if nothing writes events.

        The folder is created only when some element writes events. DLSPS 2.0
        runs as the same user as ``vippet`` (uid 1000), so it can write there
        with the default permissions. If the folder cannot be created, the run
        goes ahead without events and a warning is logged.
        """
        directory = os.path.join(
            EVENTS_DIR, _safe(job_id or "run"), uuid.uuid4().hex[:12]
        )
        commands: dict[str, str] = {}
        sources: dict[str, EventSource] = {}
        for stream_id, command in stream_commands.items():
            commands[stream_id], stream_sources = add_event_outputs(
                command, directory, stream_id
            )
            sources.update(stream_sources)
        if not sources:
            return None
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "Cannot create %s; live pipeline events are not collected: %s",
                directory,
                exc,
            )
            return None
        reader = EventFileReader(sources, on_event, on_vlm_metrics)
        return cls(directory, commands, sources, reader)

    def start(self) -> None:
        self.reader.start()
        self._started = True

    def close(self) -> None:
        """Read what is left and delete the folder."""
        if self._started:
            self.reader.stop()
            self._started = False
        shutil.rmtree(self.directory, ignore_errors=True)
        try:
            os.rmdir(os.path.dirname(self.directory))
        except OSError:
            pass


def remove_event_folders() -> None:
    """Delete every run folder under ``EVENTS_DIR``.

    Called when ``vippet`` starts and stops: no run is active then, and a
    ``vippet`` process that ended mid-run leaves its folders behind.
    """
    shutil.rmtree(EVENTS_DIR, ignore_errors=True)
