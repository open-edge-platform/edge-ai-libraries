"""metadata_manager_test.py

Unit tests for MetadataManager, _MetadataFile, _MetadataJob, and _tail_lines.
"""

import asyncio
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from managers.metadata_manager import (
    FILE_CREATION_TIMEOUT,
    METADATA_DIR,
    MetadataManager,
    _MetadataFile,
    _MetadataJob,
    _tail_lines,
)


def _make_job(
    paths: list[str] | None = None,
    pipeline_map: dict[str, list[int]] | None = None,
    job_id: str = "test-job",
) -> _MetadataJob:
    """Return a _MetadataJob without starting its threads."""
    if paths is None:
        paths = ["/tmp/fake.json"]
    if pipeline_map is None:
        pipeline_map = {"pipe-1": [0]}
    return _MetadataJob(job_id, paths, pipeline_map)


class TestTailLines(unittest.TestCase):
    """Unit tests for the _tail_lines module-level helper."""

    def test_returns_empty_list_for_zero_n(self):
        """_tail_lines with n=0 should return an empty list without touching the filesystem."""
        self.assertEqual(_tail_lines("/any/path", 0), [])

    def test_returns_empty_list_for_negative_n(self):
        """_tail_lines with negative n should return an empty list."""
        self.assertEqual(_tail_lines("/any/path", -5), [])

    def test_returns_empty_list_on_missing_file(self):
        """_tail_lines on a non-existent path should return [] (OSError is swallowed)."""
        self.assertEqual(_tail_lines("/non/existent/path.txt", 10), [])

    def test_returns_all_lines_when_fewer_than_n(self):
        """_tail_lines should return every line when the file has fewer lines than n."""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write('{"a": 1}\n{"b": 2}\n')
            path = f.name
        try:
            result = _tail_lines(path, 10)
            self.assertEqual(result, ['{"a": 1}', '{"b": 2}'])
        finally:
            os.unlink(path)

    def test_returns_last_n_lines(self):
        """_tail_lines should return only the last n lines when the file has more."""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            for i in range(10):
                f.write(f'{{"i": {i}}}\n')
            path = f.name
        try:
            result = _tail_lines(path, 3)
            self.assertEqual(result, ['{"i": 7}', '{"i": 8}', '{"i": 9}'])
        finally:
            os.unlink(path)

    def test_skips_blank_lines(self):
        """_tail_lines should not include empty or whitespace-only lines in the result."""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write('{"a": 1}\n\n{"b": 2}\n\n')
            path = f.name
        try:
            result = _tail_lines(path, 10)
            self.assertEqual(result, ['{"a": 1}', '{"b": 2}'])
        finally:
            os.unlink(path)

    def test_strips_trailing_newline_from_lines(self):
        """Returned lines should not have a trailing newline character."""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write('{"x": 1}\n')
            path = f.name
        try:
            result = _tail_lines(path, 5)
            self.assertEqual(result, ['{"x": 1}'])
        finally:
            os.unlink(path)


class TestMetadataFile(unittest.TestCase):
    """
    Unit tests for _MetadataFile.

    The tests focus on:
      * get_records – reading and parsing records from disk,
      * process_line – JSON validation and subscriber notification,
      * stop – sentinel delivery to SSE subscribers.
    """

    def test_get_records_parses_valid_json_lines(self):
        """get_records should return a list of parsed dicts for each valid JSON line."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write('{"frame": 1}\n{"frame": 2}\n')
            path = f.name
        try:
            mf = _MetadataFile(path)
            records = mf.get_records(10)
            self.assertEqual(records, [{"frame": 1}, {"frame": 2}])
        finally:
            os.unlink(path)

    def test_get_records_skips_malformed_json(self):
        """get_records should silently ignore lines that are not valid JSON."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write('{"frame": 1}\nnot-json\n{"frame": 3}\n')
            path = f.name
        try:
            mf = _MetadataFile(path)
            records = mf.get_records(10)
            self.assertEqual(records, [{"frame": 1}, {"frame": 3}])
        finally:
            os.unlink(path)

    def test_get_records_returns_empty_for_missing_file(self):
        """get_records should return [] when the backing file does not exist."""
        mf = _MetadataFile("/does/not/exist.json")
        self.assertEqual(mf.get_records(10), [])

    def test_get_records_respects_limit(self):
        """get_records should return at most ``limit`` records (the most recent ones)."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            for i in range(10):
                f.write(f'{{"i": {i}}}\n')
            path = f.name
        try:
            mf = _MetadataFile(path)
            records = mf.get_records(3)
            self.assertEqual(len(records), 3)
            self.assertEqual(records[-1], {"i": 9})
        finally:
            os.unlink(path)

    def test_process_line_skips_empty_string(self):
        """process_line should not notify subscribers when the line is empty."""
        mf = _MetadataFile("/tmp/test.json")
        mock_loop = MagicMock()
        mf._subscribers = [(MagicMock(), mock_loop)]
        mf.process_line("")
        mock_loop.call_soon_threadsafe.assert_not_called()

    def test_process_line_skips_malformed_json(self):
        """process_line should ignore lines that fail JSON decoding."""
        mf = _MetadataFile("/tmp/test.json")
        mock_loop = MagicMock()
        mf._subscribers = [(MagicMock(), mock_loop)]
        mf.process_line("this is not json")
        mock_loop.call_soon_threadsafe.assert_not_called()

    def test_process_line_notifies_single_subscriber(self):
        """process_line with valid JSON should schedule a queue put on the subscriber loop."""
        mf = _MetadataFile("/tmp/test.json")
        mock_loop = MagicMock()
        mf._subscribers = [(MagicMock(), mock_loop)]
        mf.process_line('{"frame": 42}')
        mock_loop.call_soon_threadsafe.assert_called_once()

    def test_process_line_notifies_all_subscribers(self):
        """process_line should notify every active subscriber, not just the first."""
        mf = _MetadataFile("/tmp/test.json")
        loops = [MagicMock(), MagicMock(), MagicMock()]
        mf._subscribers = [(MagicMock(), loop) for loop in loops]
        mf.process_line('{"x": 1}')
        for loop in loops:
            loop.call_soon_threadsafe.assert_called_once()

    def test_process_line_with_no_subscribers_does_not_raise(self):
        """process_line should not raise when there are no subscribers."""
        mf = _MetadataFile("/tmp/test.json")
        mf._subscribers = []
        mf.process_line('{"ok": true}')  # should not raise

    def test_stop_sends_none_sentinel_to_all_subscribers(self):
        """stop() should schedule None into every subscriber's queue."""
        mf = _MetadataFile("/tmp/test.json")
        loops = [MagicMock(), MagicMock()]
        queues = [MagicMock(), MagicMock()]
        mf._subscribers = list(zip(queues, loops))
        mf.stop()
        for loop, q in zip(loops, queues):
            loop.call_soon_threadsafe.assert_called_once_with(q.put_nowait, None)

    def test_stop_with_no_subscribers_does_not_raise(self):
        """stop() on a file with no subscribers should not raise."""
        mf = _MetadataFile("/tmp/test.json")
        mf._subscribers = []
        mf.stop()  # should not raise


class TestMetadataJob(unittest.TestCase):
    """
    Unit tests for _MetadataJob.

    The tests focus on:
      * object construction and initial state,
      * get_records delegation,
      * stop / start lifecycle.
    """

    def test_files_list_created_from_paths(self):
        """_MetadataJob should create one _MetadataFile per provided path."""
        job = _make_job(paths=["/a.json", "/b.json"], pipeline_map={"p": [0, 1]})
        self.assertEqual(len(job.files), 2)
        self.assertEqual(job.files[0].path, "/a.json")
        self.assertEqual(job.files[1].path, "/b.json")

    def test_pipeline_map_stored_correctly(self):
        """_MetadataJob.pipeline_map should match the dict passed to the constructor."""
        pm = {"pipe-a": [0], "pipe-b": [1]}
        job = _make_job(paths=["/a.json", "/b.json"], pipeline_map=pm)
        self.assertEqual(job.pipeline_map, pm)

    def test_stop_event_is_not_set_initially(self):
        """The stop event should not be set when the job is first created."""
        job = _make_job()
        self.assertFalse(job._stop_event.is_set())

    def test_get_records_delegates_to_correct_file(self):
        """_MetadataJob.get_records should forward the call to the right _MetadataFile."""
        job = _make_job()
        job.files[0].get_records = MagicMock(return_value=[{"ok": True}])
        result = job.get_records(0, 5)
        job.files[0].get_records.assert_called_once_with(5)
        self.assertEqual(result, [{"ok": True}])

    def test_stop_sets_stop_event_and_stops_all_files(self):
        """_MetadataJob.stop() should set the internal event and call stop() on every file."""
        job = _make_job(paths=["/a.json", "/b.json"], pipeline_map={"p": [0, 1]})
        stop_mocks = []
        for mf in job.files:
            mock_stop = MagicMock()
            mf.stop = mock_stop  # type: ignore[method-assign]
            stop_mocks.append(mock_stop)
        job.stop()
        self.assertTrue(job._stop_event.is_set())
        for mock_stop in stop_mocks:
            mock_stop.assert_called_once_with()

    @patch("threading.Thread")
    def test_start_spawns_one_daemon_thread_per_file(self, mock_thread_cls):
        """_MetadataJob.start() should create and start one daemon thread per file."""
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread
        job = _make_job(paths=["/a.json", "/b.json"], pipeline_map={"p": [0, 1]})
        job.start()
        self.assertEqual(mock_thread_cls.call_count, 2)
        self.assertEqual(mock_thread.start.call_count, 2)
        # Verify threads are created as daemon threads
        for call_kwargs in mock_thread_cls.call_args_list:
            self.assertTrue(call_kwargs.kwargs.get("daemon", False))


class TestMetadataManager(unittest.TestCase):
    """
    Unit tests for MetadataManager.

    The tests focus on:
      * singleton pattern,
      * register_job / job_exists,
      * stop_tailing,
      * get_snapshot,
      * resolve_file_index,
      * stream_events async generator.
    """

    def setUp(self):
        """Reset singleton state before each test."""
        MetadataManager._instance = None

    def tearDown(self):
        """Reset singleton state after each test."""
        MetadataManager._instance = None

    def _patch_job_start(self):
        """Context manager that prevents _MetadataJob.start from spawning threads."""
        return patch("managers.metadata_manager._MetadataJob.start", return_value=None)

    def _register(
        self,
        manager: MetadataManager,
        job_id: str = "job-1",
        file_paths_by_pipeline: dict[str, list[str]] | None = None,
    ) -> None:
        """Helper: register a job without starting tailer threads."""
        if file_paths_by_pipeline is None:
            file_paths_by_pipeline = {"pipe-a": ["/tmp/a.json"]}
        with self._patch_job_start():
            manager.register_job(job_id, file_paths_by_pipeline)

    def test_singleton_returns_same_instance(self):
        """MetadataManager() must return the identical object on every call."""
        a = MetadataManager()
        b = MetadataManager()
        self.assertIs(a, b)

    def test_singleton_is_initialized_once(self):
        """_initialized flag should be set and __init__ should not re-run."""
        manager = MetadataManager()
        # Mutate state; a second call should not overwrite it
        manager._jobs["sentinel"] = None  # type: ignore[assignment]
        manager2 = MetadataManager()
        self.assertIn("sentinel", manager2._jobs)

    def test_job_exists_returns_false_for_unknown_job(self):
        """job_exists should return False when no job has been registered."""
        manager = MetadataManager()
        self.assertFalse(manager.job_exists("non-existent"))

    def test_job_exists_returns_true_after_register(self):
        """job_exists should return True immediately after register_job."""
        manager = MetadataManager()
        self._register(manager, "job-1")
        self.assertTrue(manager.job_exists("job-1"))

    def test_register_job_ignores_empty_file_paths(self):
        """register_job with no file paths should not create a job entry."""
        manager = MetadataManager()
        manager.register_job("empty-job", {})
        self.assertFalse(manager.job_exists("empty-job"))

    def test_register_job_is_idempotent(self):
        """Calling register_job twice with the same id should only register once."""
        manager = MetadataManager()
        with self._patch_job_start():
            manager.register_job("job-1", {"pipe-a": ["/tmp/a.json"]})
            manager.register_job("job-1", {"pipe-a": ["/tmp/b.json"]})
        with manager._jobs_lock:
            self.assertEqual(len(manager._jobs), 1)

    def test_register_job_creates_correct_pipeline_map(self):
        """register_job should map each pipeline_id to the correct global file indices."""
        manager = MetadataManager()
        self._register(
            manager,
            "job-1",
            {
                "pipe-a": ["/tmp/a.json", "/tmp/b.json"],
                "pipe-b": ["/tmp/c.json"],
            },
        )
        with manager._jobs_lock:
            job = manager._jobs["job-1"]
        self.assertEqual(job.pipeline_map["pipe-a"], [0, 1])
        self.assertEqual(job.pipeline_map["pipe-b"], [2])

    def test_register_job_flattens_paths_across_pipelines(self):
        """The flat file list on the job should contain all paths in order."""
        manager = MetadataManager()
        self._register(
            manager,
            "job-1",
            {"pipe-a": ["/tmp/a.json"], "pipe-b": ["/tmp/b.json"]},
        )
        with manager._jobs_lock:
            job = manager._jobs["job-1"]
        paths = [mf.path for mf in job.files]
        self.assertEqual(paths, ["/tmp/a.json", "/tmp/b.json"])

    def test_stop_tailing_calls_stop_on_job(self):
        """stop_tailing should invoke stop() on the registered _MetadataJob."""
        manager = MetadataManager()
        self._register(manager, "job-1")
        with manager._jobs_lock:
            job = manager._jobs["job-1"]
        job.stop = MagicMock()
        manager.stop_tailing("job-1")
        job.stop.assert_called_once()

    def test_stop_tailing_unknown_job_does_not_raise(self):
        """stop_tailing with an unregistered job_id should not raise any exception."""
        manager = MetadataManager()
        manager.stop_tailing("unknown-job")  # should not raise

    def test_get_snapshot_returns_empty_for_unknown_job(self):
        """get_snapshot for an unregistered job should return []."""
        manager = MetadataManager()
        self.assertEqual(manager.get_snapshot("no-such-job", 0), [])

    def test_get_snapshot_returns_empty_for_out_of_range_index(self):
        """get_snapshot with a file_index beyond the job's files should return []."""
        manager = MetadataManager()
        self._register(manager, "job-1", {"p": ["/tmp/a.json"]})
        self.assertEqual(manager.get_snapshot("job-1", 99), [])

    def test_get_snapshot_returns_empty_for_negative_index(self):
        """get_snapshot with a negative file_index should return []."""
        manager = MetadataManager()
        self._register(manager, "job-1", {"p": ["/tmp/a.json"]})
        self.assertEqual(manager.get_snapshot("job-1", -1), [])

    def test_get_snapshot_delegates_to_job_get_records(self):
        """get_snapshot should call get_records on the underlying job and forward the result."""
        manager = MetadataManager()
        self._register(manager, "job-1", {"p": ["/tmp/a.json"]})
        with manager._jobs_lock:
            job = manager._jobs["job-1"]
        job.get_records = MagicMock(return_value=[{"frame": 1}])
        result = manager.get_snapshot("job-1", 0, limit=50)
        job.get_records.assert_called_once_with(0, 50)
        self.assertEqual(result, [{"frame": 1}])

    def test_get_snapshot_uses_default_limit(self):
        """get_snapshot without an explicit limit should use the default value of 100."""
        manager = MetadataManager()
        self._register(manager, "job-1", {"p": ["/tmp/a.json"]})
        with manager._jobs_lock:
            job = manager._jobs["job-1"]
        job.get_records = MagicMock(return_value=[])
        manager.get_snapshot("job-1", 0)
        job.get_records.assert_called_once_with(0, 100)

    def test_resolve_file_index_returns_none_for_unknown_job(self):
        """resolve_file_index should return None when the job_id is not registered."""
        manager = MetadataManager()
        self.assertIsNone(manager.resolve_file_index("no-job", "pipe", 0))

    def test_resolve_file_index_returns_none_for_unknown_pipeline(self):
        """resolve_file_index should return None when the pipeline_id is absent."""
        manager = MetadataManager()
        self._register(manager, "job-1", {"pipe-a": ["/tmp/a.json"]})
        self.assertIsNone(manager.resolve_file_index("job-1", "no-pipe", 0))

    def test_resolve_file_index_returns_none_for_out_of_range_local_index(self):
        """resolve_file_index should return None when local_index exceeds the pipeline's files."""
        manager = MetadataManager()
        self._register(manager, "job-1", {"pipe-a": ["/tmp/a.json"]})
        self.assertIsNone(manager.resolve_file_index("job-1", "pipe-a", 5))

    def test_resolve_file_index_single_pipeline_single_file(self):
        """resolve_file_index should return 0 for the only file of the only pipeline."""
        manager = MetadataManager()
        self._register(manager, "job-1", {"pipe-a": ["/tmp/a.json"]})
        self.assertEqual(manager.resolve_file_index("job-1", "pipe-a", 0), 0)

    def test_resolve_file_index_multiple_pipelines(self):
        """resolve_file_index should return the correct global index across pipelines."""
        manager = MetadataManager()
        self._register(
            manager,
            "job-1",
            {
                "pipe-a": ["/tmp/a.json", "/tmp/b.json"],
                "pipe-b": ["/tmp/c.json"],
            },
        )
        self.assertEqual(manager.resolve_file_index("job-1", "pipe-a", 0), 0)
        self.assertEqual(manager.resolve_file_index("job-1", "pipe-a", 1), 1)
        self.assertEqual(manager.resolve_file_index("job-1", "pipe-b", 0), 2)

    def test_stream_events_yields_nothing_for_unknown_job(self):
        """stream_events for an unregistered job should yield no items."""
        manager = MetadataManager()

        async def collect() -> list:
            items = []
            async for item in manager.stream_events("no-job", 0):
                items.append(item)
            return items

        self.assertEqual(asyncio.run(collect()), [])

    def test_stream_events_yields_nothing_for_out_of_range_file_index(self):
        """stream_events with an out-of-range file_index should yield no items."""
        manager = MetadataManager()
        self._register(manager, "job-1", {"p": ["/tmp/a.json"]})

        async def collect() -> list:
            items = []
            async for item in manager.stream_events("job-1", 99):
                items.append(item)
            return items

        self.assertEqual(asyncio.run(collect()), [])

    def test_stream_events_yields_line_and_terminates_on_stop(self):
        """stream_events should yield a delivered line then stop when the sentinel is sent."""
        manager = MetadataManager()
        self._register(manager, "job-1", {"p": ["/tmp/a.json"]})
        line = '{"frame": 7}'

        async def run() -> list:
            gen = manager.stream_events("job-1", 0)

            async def _collect_one():
                collected = []
                async for item in gen:
                    collected.append(item)
                    break  # stop after the first item
                return collected

            task = asyncio.create_task(_collect_one())
            # Allow the subscriber to register inside the event loop
            await asyncio.sleep(0.05)
            with manager._jobs_lock:
                job = manager._jobs["job-1"]
            job.files[0].process_line(line)
            job.files[0].stop()
            return await asyncio.wait_for(task, timeout=2.0)

        result = asyncio.run(run())
        self.assertEqual(result, [line])

    def test_stream_events_terminates_immediately_on_stop_with_no_lines(self):
        """stream_events should stop cleanly when stop() is called with no data."""
        manager = MetadataManager()
        self._register(manager, "job-1", {"p": ["/tmp/a.json"]})

        async def run() -> list:
            gen = manager.stream_events("job-1", 0)

            async def _collect():
                items = []
                async for item in gen:
                    items.append(item)
                return items

            task = asyncio.create_task(_collect())
            await asyncio.sleep(0.05)
            with manager._jobs_lock:
                job = manager._jobs["job-1"]
            job.files[0].stop()
            return await asyncio.wait_for(task, timeout=2.0)

        result = asyncio.run(run())
        self.assertEqual(result, [])


class TestModuleConstants(unittest.TestCase):
    """Tests for module-level configuration constants."""

    def test_file_creation_timeout_is_positive(self):
        """FILE_CREATION_TIMEOUT should be a positive number."""
        self.assertGreater(FILE_CREATION_TIMEOUT, 0)

    def test_metadata_dir_is_normalized_path(self):
        """METADATA_DIR should be a normalised absolute-style string (no trailing sep)."""
        self.assertFalse(METADATA_DIR.endswith(os.sep))

    def test_metadata_dir_falls_back_to_default(self):
        """When METADATA_DIR env var is absent the constant should contain 'metadata'."""
        env_without_var = {k: v for k, v in os.environ.items() if k != "METADATA_DIR"}
        with patch.dict(os.environ, env_without_var, clear=True):
            import importlib

            import managers.metadata_manager as mm

            importlib.reload(mm)
            self.assertIn("metadata", mm.METADATA_DIR)

    def test_metadata_dir_reads_from_environment(self):
        """When METADATA_DIR env var is set METADATA_DIR should mirror it (normalised)."""
        with patch.dict(os.environ, {"METADATA_DIR": "/custom/meta"}, clear=False):
            import importlib

            import managers.metadata_manager as mm

            importlib.reload(mm)
            self.assertEqual(mm.METADATA_DIR, "/custom/meta")


class TestMetadataJobTailIntegration(unittest.TestCase):
    """
    Integration-style tests that exercise _MetadataJob._tail_file end-to-end.

    These tests start real background threads and use real temporary files so
    that the tailer logic (file waiting, line reading) is exercised without
    mocking the OS.
    """

    def test_tail_file_processes_existing_lines(self):
        """Lines already present in the file should be delivered to process_line."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write('{"a": 1}\n')
            path = f.name
        try:
            job = _MetadataJob("tail-test", [path], {"p": [0]})
            processed: list[str] = []

            original_process = job.files[0].process_line

            def capture(line: str, orig=original_process) -> None:
                processed.append(line)
                orig(line)

            job.files[0].process_line = capture
            job.start()
            deadline = time.monotonic() + 3.0
            while not processed and time.monotonic() < deadline:
                time.sleep(0.05)
            job.stop()
            self.assertIn('{"a": 1}', processed)
        finally:
            os.unlink(path)

    def test_tail_file_processes_appended_lines(self):
        """Lines appended to the file after the tailer starts should also be delivered."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            path = f.name  # start with empty file

        try:
            job = _MetadataJob("tail-append", [path], {"p": [0]})
            processed: list[str] = []

            original_process = job.files[0].process_line

            def capture(line: str, orig=original_process) -> None:
                processed.append(line)
                orig(line)

            job.files[0].process_line = capture
            job.start()
            # Give the tailer thread time to open the file
            time.sleep(0.1)
            with open(path, "a") as f:
                f.write('{"appended": true}\n')
            deadline = time.monotonic() + 3.0
            while not processed and time.monotonic() < deadline:
                time.sleep(0.05)
            job.stop()
            self.assertIn('{"appended": true}', processed)
        finally:
            os.unlink(path)

    def test_tail_file_handles_missing_file_gracefully(self):
        """The tailer should log a warning and exit cleanly when the file never appears."""
        job = _MetadataJob(
            "missing-file", ["/tmp/vippet_does_not_exist_ever.json"], {"p": [0]}
        )
        with patch("managers.metadata_manager.FILE_CREATION_TIMEOUT", 0.2):
            job.start()
            # Allow enough time for the tailer to time out
            time.sleep(0.6)
            job.stop()
        # Reaching here without exception means the tailer exited gracefully


if __name__ == "__main__":
    unittest.main()
