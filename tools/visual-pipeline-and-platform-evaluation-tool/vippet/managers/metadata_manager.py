"""metadata_manager.py

Thread-safe singleton that tails gvametapublish output files and exposes
their content via an SSE generator; snapshots are read directly from disk.
"""

import asyncio
from collections import deque
import json
import logging
import os
import threading
import time
from typing import AsyncIterator, Optional

from utils import slugify_text

# Seconds to wait for the metadata file to be created by gvametapublish
FILE_CREATION_TIMEOUT = 30

# Default directory for metadata files
_METADATA_DIR = "/metadata"

# Read METADATA_DIR from environment variable, fallback to default if not set
METADATA_DIR: str = os.path.normpath(os.getenv("METADATA_DIR", _METADATA_DIR))


class MetadataManager:
    """
    Thread-safe singleton that tracks gvametapublish output files per job.

    Implements singleton pattern using __new__ with double-checked locking.
    Create instances with MetadataManager() to get the shared singleton instance.

    Responsibilities:

    * tail each metadata file in a background thread
    * forward new records to active SSE subscribers as they arrive
    * serve snapshots by reading the file from disk on demand
    """

    _instance: Optional["MetadataManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "MetadataManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._jobs: dict[str, _MetadataJob] = {}
        self._jobs_lock = threading.Lock()
        self.logger = logging.getLogger("MetadataManager")

    def register_job(
        self, job_id: str, file_paths_by_pipeline: dict[str, list[str]]
    ) -> None:
        """
        Register a job and start tailing the given metadata file paths.

        Args:
            job_id: Unique job identifier.
            file_paths_by_pipeline: Mapping of pipeline_id to the list of
                absolute paths of gvametapublish output files for that pipeline.
        """
        all_file_paths = [p for paths in file_paths_by_pipeline.values() for p in paths]
        if not all_file_paths:
            return
        pipeline_map: dict[str, list[int]] = {}
        global_i = 0
        for pipeline_id, paths in file_paths_by_pipeline.items():
            pipeline_map[slugify_text(pipeline_id)] = list(
                range(global_i, global_i + len(paths))
            )
            global_i += len(paths)
        with self._jobs_lock:
            if job_id in self._jobs:
                return
            job = _MetadataJob(job_id, all_file_paths, pipeline_map)
            self._jobs[job_id] = job
        job.start()
        self.logger.debug(
            "Registered metadata job %s with files: %s", job_id, all_file_paths
        )

    def stop_tailing(self, job_id: str) -> None:
        """
        Stop tailing files for this job.

        Snapshots can still be read from disk after this call.

        Args:
            job_id: Unique job identifier.
        """
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if job:
            job.stop()
            self.logger.debug("Stopped tailing for metadata job %s", job_id)

    def job_exists(self, job_id: str) -> bool:
        """Return True if a job with the given id has been registered."""
        with self._jobs_lock:
            return job_id in self._jobs

    def get_snapshot(
        self, job_id: str, file_index: int, limit: int = 100
    ) -> list[dict]:
        """
        Return the most recent records for a specific file in the job, read directly from disk.

        Args:
            job_id: Unique job identifier.
            file_index: Global (flat) index of the metadata file to query.
            limit: Maximum number of records to return (most recent first).

        Returns:
            List of parsed JSON objects. Empty list if job or file_index is unknown.
        """
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if not job or not (0 <= file_index < len(job.files)):
            self.logger.debug("job '%s' or file_index %d not found", job_id, file_index)
            return []
        records = job.get_records(file_index, limit)
        self.logger.debug(
            "returning %d record(s) for job '%s' file_index %d",
            len(records),
            job_id,
            file_index,
        )
        return records

    def resolve_file_index(
        self, job_id: str, pipeline_id: str, local_index: int
    ) -> int | None:
        """
        Resolve a per-pipeline local file index to the flat global file index.

        Args:
            job_id: Unique job identifier.
            pipeline_id: Pipeline identifier (key in ``metadata_stream_urls``).
            local_index: Zero-based index within that pipeline's file list.

        Returns:
            Global file index into the flat ``_MetadataJob.files`` list,
            or ``None`` when the job, pipeline, or index is unknown.
        """
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if not job:
            self.logger.debug("job '%s' not found", job_id)
            return None
        indices = job.pipeline_map.get(pipeline_id)
        if not indices or not (0 <= local_index < len(indices)):
            self.logger.debug(
                "pipeline '%s' or local_index %d not found for job '%s'",
                pipeline_id,
                local_index,
                job_id,
            )
            return None
        global_index = indices[local_index]
        self.logger.debug(
            "job '%s' pipeline '%s' local_index %d -> global_index %d",
            job_id,
            pipeline_id,
            local_index,
            global_index,
        )
        return global_index

    async def stream_events(self, job_id: str, file_index: int) -> AsyncIterator[str]:
        """
        Async generator that yields raw JSON lines for a single file as they arrive.

        Each yielded string is a single serialised JSON record (without newline).
        Yields SSE keepalive comments (``": keepalive\\n\\n"``) every 30 s when
        no new data arrives so that proxies and browsers do not time out.

        The generator terminates when ``stop_tailing()`` is called for the job
        (typically when the pipeline finishes).

        Args:
            job_id: Unique job identifier.
            file_index: Zero-based index of the file to stream.
        """
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if not job:
            self.logger.debug("job '%s' not found", job_id)
            return
        if not (0 <= file_index < len(job.files)):
            self.logger.debug(
                "file_index %d out of range for job '%s'", file_index, job_id
            )
            return
        self.logger.debug(
            "starting SSE stream for job '%s' file_index %d", job_id, file_index
        )
        async for line in job.stream(file_index):
            yield line
        self.logger.debug(
            "SSE stream ended for job '%s' file_index %d", job_id, file_index
        )


def _tail_lines(path: str, n: int) -> list[str]:
    """
    Return up to the last *n* non-empty lines from *path*.

    Reads the file once and keeps only the last *n* non-empty lines.
    """
    if n <= 0:
        return []

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return list(
                deque((line.rstrip("\n") for line in f if line.strip()), maxlen=n)
            )
    except OSError:
        return []


class _MetadataFile:
    """Per-file state: SSE subscriber list."""

    def __init__(self, path: str) -> None:
        self.path = path
        # List of (asyncio.Queue, event_loop) tuples for active SSE connections
        self._subscribers: list[tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = []
        self._subscribers_lock = threading.Lock()
        self.logger = logging.getLogger(f"MetadataManager.file[{path}]")

    def get_records(self, limit: int) -> list[dict]:
        """Read the last ``limit`` records directly from the file on disk."""
        records = []
        for line in _tail_lines(self.path, limit):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return records

    async def stream(self) -> AsyncIterator[str]:
        """Async generator bridging the tailing thread to SSE subscribers."""
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        loop = asyncio.get_running_loop()
        subscriber = (q, loop)
        with self._subscribers_lock:
            self._subscribers.append(subscriber)
            count = len(self._subscribers)
        self.logger.debug(
            "SSE subscriber connected for %s (active: %d)", self.path, count
        )
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=30.0)
                    if item is None:  # sentinel: pipeline stopped
                        break
                    yield item
                except asyncio.TimeoutError:
                    # SSE keepalive comment – prevents proxy / browser timeouts
                    yield ": keepalive\n\n"
        finally:
            with self._subscribers_lock:
                try:
                    self._subscribers.remove(subscriber)
                except ValueError:
                    pass
                count = len(self._subscribers)
            self.logger.debug(
                "SSE subscriber disconnected for %s (remaining: %d)", self.path, count
            )

    def process_line(self, line: str) -> None:
        """Validate a JSON line and notify all SSE subscribers.

        Delivery to SSE clients is best-effort: if a subscriber's queue is
        full (i.e. the client is too slow to consume events), the record is
        silently dropped for that subscriber.  Snapshots read via
        ``get_records()`` are always complete because they read from disk.
        """
        if not line:
            return
        try:
            json.loads(line)
        except json.JSONDecodeError:
            self.logger.debug(
                "Skipping malformed JSON line in %s: %.120r", self.path, line
            )
            return  # skip malformed lines
        with self._subscribers_lock:
            for q, loop in self._subscribers:
                # put_nowait runs *inside* the event loop via call_soon_threadsafe,
                # so QueueFull must be caught inside the scheduled callback, not here.
                def _put(
                    q: asyncio.Queue = q,
                    item: str = line,
                    log=self.logger,
                ) -> None:
                    if not q.full():
                        q.put_nowait(item)
                    else:
                        # Subscriber is too slow; record dropped (best-effort delivery)
                        log.debug(
                            "SSE subscriber queue full for %s; record dropped",
                            self.path,
                        )

                loop.call_soon_threadsafe(_put)

    def stop(self) -> None:
        """Send sentinel to all subscribers to terminate their SSE streams."""
        with self._subscribers_lock:
            count = len(self._subscribers)
            for q, loop in self._subscribers:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, None)
                except Exception:
                    pass
        self.logger.debug(
            "Sent stop sentinel to %d subscriber(s) for %s", count, self.path
        )


class _MetadataJob:
    """Per-job state: one tailer thread and _MetadataFile instance per file."""

    def __init__(
        self, job_id: str, file_paths: list[str], pipeline_map: dict[str, list[int]]
    ) -> None:
        self.job_id = job_id
        self.files: list[_MetadataFile] = [_MetadataFile(path) for path in file_paths]
        self.pipeline_map = pipeline_map
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self.logger = logging.getLogger(f"MetadataManager.{job_id}")

    def start(self) -> None:
        """Start one background tailer thread per file."""
        self.logger.debug(
            "Starting %d tailer thread(s) for job '%s'", len(self.files), self.job_id
        )
        for i, meta_file in enumerate(self.files):
            t = threading.Thread(
                target=self._tail_file,
                args=(meta_file,),
                daemon=True,
                name=f"metadata-tail-{self.job_id}-{i}",
            )
            self._threads.append(t)
            t.start()

    def stop(self) -> None:
        """Signal tailer threads to stop and send sentinel to all SSE subscribers."""
        self.logger.debug("Stopping tailer threads for job '%s'", self.job_id)
        self._stop_event.set()
        for meta_file in self.files:
            meta_file.stop()

    def get_records(self, file_index: int, limit: int) -> list[dict]:
        """Return the last ``limit`` records for a specific file."""
        return self.files[file_index].get_records(limit)

    async def stream(self, file_index: int) -> AsyncIterator[str]:
        """Async generator for a specific file's SSE stream."""
        async for line in self.files[file_index].stream():
            yield line

    def _tail_file(self, meta_file: _MetadataFile) -> None:
        """
        Block-read a single file line by line, waiting up to FILE_CREATION_TIMEOUT
        seconds for the file to be created by gvametapublish.
        """
        path = meta_file.path
        waited = 0.0
        while not os.path.exists(path) and not self._stop_event.is_set():
            if waited >= FILE_CREATION_TIMEOUT:
                self.logger.warning(
                    "Metadata file not created within %ds: %s",
                    FILE_CREATION_TIMEOUT,
                    path,
                )
                return
            time.sleep(0.5)
            waited += 0.5

        if self._stop_event.is_set():
            return

        self.logger.debug("Started tailing %s", path)
        try:
            with open(path, "r") as f:
                while not self._stop_event.is_set():
                    line = f.readline()
                    if line:
                        meta_file.process_line(line.rstrip("\n"))
                    else:
                        time.sleep(0.1)
        except Exception as e:
            self.logger.error("Error tailing metadata file %s: %s", path, e)
        self.logger.debug("Stopped tailing %s", path)
