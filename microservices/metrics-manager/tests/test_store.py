# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the MetricsStore."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.store as store_module
from app.models import Metric
from app.store import MetricsStore, get_metrics_store, reset_metrics_store


@pytest.fixture
async def store(tmp_path):
    instance = MetricsStore(metrics_dir=str(tmp_path), debounce_ms=0)
    try:
        yield instance
    finally:
        await instance.close()


class TestMetricsStore:
    """Tests for MetricsStore class."""

    @pytest.mark.asyncio
    async def test_add_single_metric(self, store):
        """Test adding a single metric."""
        metric = Metric(name="test_metric", fields={"value": 42.0})
        await store.add_metric(metric)

        metrics = await store.get_metrics("test_metric")
        assert len(metrics) == 1
        assert metrics[0].name == "test_metric"
        assert metrics[0].fields["value"] == 42.0

    @pytest.mark.asyncio
    async def test_add_multiple_metrics(self, store):
        """Test adding multiple metrics."""
        metrics = [
            Metric(name="cpu", fields={"usage": 45.0}),
            Metric(name="memory", fields={"used": 8192}),
            Metric(name="cpu", fields={"usage": 46.0}),
        ]
        count = await store.add_metrics(metrics)
        assert count == 3

        all_metrics = await store.get_metrics()
        assert len(all_metrics) == 3

        cpu_metrics = await store.get_metrics("cpu")
        assert len(cpu_metrics) == 2

    @pytest.mark.asyncio
    async def test_get_latest_metrics(self, store):
        """Test getting latest metric for each name."""
        # Add multiple metrics with same name
        for i in range(3):
            metric = Metric(
                name="test",
                fields={"value": i},
                timestamp=int((1704067200 + i) * 1e9),
            )
            await store.add_metric(metric)

        latest = await store.get_latest_metrics()
        assert "test" in latest
        assert latest["test"].fields["value"] == 2  # Last one

    @pytest.mark.asyncio
    async def test_get_latest_metrics_keeps_series_with_distinct_tags(self, store):
        """Series sharing a name but differing in tags must not overwrite each other."""
        for tile, value in (("gt0", 800), ("gt1", 100)):
            await store.add_metric(
                Metric(
                    name="gpu_frequency",
                    tags={"tile": tile, "gpu_id": "0"},
                    fields={"value": value},
                    timestamp=int(1704067200 * 1e9),
                )
            )

        latest = await store.get_latest_metrics()

        assert latest["gpu_frequency{gpu_id=0,tile=gt0}"].fields["value"] == 800
        assert latest["gpu_frequency{gpu_id=0,tile=gt1}"].fields["value"] == 100

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "first,second",
        [
            ({"x": "a,y=b"}, {"x": "a", "y": "b"}),
            ({"x=y": "z"}, {"x": "y=z"}),
            ({"x": r"a\,y=b"}, {"x": "a\\", "y": "b"}),
        ],
    )
    async def test_get_latest_metrics_preserves_label_separators(self, store, first, second):
        await store.add_metrics(
            [
                Metric(name="fps", fields={"value": 10}, tags=first),
                Metric(name="fps", fields={"value": 20}, tags=second),
            ]
        )
        latest = await store.get_latest_metrics()
        assert len(latest) == 2
        assert {metric.fields["value"] for metric in latest.values()} == {10, 20}

    @pytest.mark.asyncio
    async def test_get_latest_metrics_picks_newest_within_a_series(self, store):
        """Within one series the most recent sample still wins."""
        for i in range(3):
            await store.add_metric(
                Metric(
                    name="gpu_frequency",
                    tags={"tile": "gt0"},
                    fields={"value": i},
                    timestamp=int((1704067200 + i) * 1e9),
                )
            )

        latest = await store.get_latest_metrics()

        assert len(latest) == 1
        assert latest["gpu_frequency{tile=gt0}"].fields["value"] == 2

    @pytest.mark.asyncio
    async def test_get_metric_names(self, store):
        """Test getting list of metric names."""
        await store.add_metric(Metric(name="cpu", fields={"v": 1}))
        await store.add_metric(Metric(name="memory", fields={"v": 2}))
        await store.add_metric(Metric(name="disk", fields={"v": 3}))

        names = await store.get_metric_names()
        assert set(names) == {"cpu", "memory", "disk"}

    @pytest.mark.asyncio
    async def test_clear_all_metrics(self, store):
        """Test clearing all metrics."""
        await store.add_metric(Metric(name="cpu", fields={"v": 1}))
        await store.add_metric(Metric(name="memory", fields={"v": 2}))

        count = await store.clear_metrics()
        assert count == 2

        metrics = await store.get_metrics()
        assert len(metrics) == 0

    @pytest.mark.asyncio
    async def test_clear_specific_metric(self, store):
        """Test clearing a specific metric."""
        await store.add_metric(Metric(name="cpu", fields={"v": 1}))
        await store.add_metric(Metric(name="memory", fields={"v": 2}))

        count = await store.clear_metrics("cpu")
        assert count == 1

        metrics = await store.get_metrics()
        assert len(metrics) == 1
        assert metrics[0].name == "memory"

    @pytest.mark.asyncio
    async def test_get_stats(self, store):
        """Test getting storage statistics."""
        await store.add_metric(Metric(name="cpu", fields={"v": 1}))
        await store.add_metric(Metric(name="cpu", fields={"v": 2}))
        await store.add_metric(Metric(name="memory", fields={"v": 3}))

        stats = await store.get_stats()
        assert stats["total_metrics"] == 3
        assert "cpu" in stats["metric_names"]
        assert "memory" in stats["metric_names"]
        assert stats["metric_counts"]["cpu"] == 2
        assert stats["metric_counts"]["memory"] == 1

    @pytest.mark.asyncio
    async def test_telegraf_push(self, store, mocker):
        """Test metrics are pushed to Telegraf via HTTP after add_metric."""

        async def _noop(*_):
            pass

        mock_push = mocker.patch.object(store, "_push_to_telegraf", side_effect=_noop)

        await store.add_metric(Metric(name="test", fields={"value": 42}))

        # With debounce=0, push is scheduled immediately as a fire-and-forget task
        await asyncio.sleep(0.05)

        mock_push.assert_called_once()
        influx_content, count = mock_push.call_args.args
        assert "test" in influx_content
        assert "value" in influx_content
        assert count == 1

    @pytest.mark.asyncio
    async def test_empty_metrics_returns_empty_list(self, store):
        """Test getting metrics from empty store."""
        metrics = await store.get_metrics()
        assert metrics == []

        metrics = await store.get_metrics("nonexistent")
        assert metrics == []

    @pytest.mark.asyncio
    async def test_eviction_removes_oldest_when_limit_reached(self, store):
        """When max_metrics is reached, the oldest metric by timestamp is evicted."""
        store._max_metrics = 3

        for i in range(3):
            m = Metric(
                name="cpu",
                fields={"value": float(i)},
                timestamp=int((1704067200 + i) * 1e9),
            )
            await store.add_metric(m)

        # Adding a 4th metric should evict the oldest (timestamp 1704067200 * 1e9)
        newest = Metric(
            name="cpu",
            fields={"value": 99.0},
            timestamp=int(1704067210 * 1e9),
        )
        await store.add_metric(newest)

        metrics = await store.get_metrics("cpu")
        assert len(metrics) == 3
        timestamps = [m.timestamp for m in metrics]
        assert int(1704067200 * 1e9) not in timestamps
        assert int(1704067210 * 1e9) in timestamps

    @pytest.mark.asyncio
    async def test_expired_metrics_not_returned(self, store):
        """Metrics older than retention_seconds are excluded from query results."""
        import time
        from unittest.mock import patch

        await store.add_metric(Metric(name="old_metric", fields={"value": 1.0}))

        # Advance time past retention window (default 300s)
        future_time = time.time() + 400
        with patch("app.store.time.time", return_value=future_time):
            metrics = await store.get_metrics("old_metric")
            assert metrics == []

    @pytest.mark.asyncio
    async def test_expired_metrics_not_in_latest(self, store):
        """Expired metrics are excluded from get_latest_metrics."""
        import time
        from unittest.mock import patch

        await store.add_metric(Metric(name="fps", fields={"value": 30.0}))

        future_time = time.time() + 400
        with patch("app.store.time.time", return_value=future_time):
            latest = await store.get_latest_metrics()
            assert "fps" not in latest

    @pytest.mark.asyncio
    async def test_eviction_across_different_metric_names(self, store):
        """Eviction picks the globally oldest metric regardless of name."""
        store._max_metrics = 2

        old = Metric(name="cpu", fields={"v": 1.0}, timestamp=int(1704067200 * 1e9))
        recent = Metric(name="mem", fields={"v": 2.0}, timestamp=int(1704067300 * 1e9))
        await store.add_metric(old)
        await store.add_metric(recent)

        # Third metric triggers eviction of `old` (cpu)
        await store.add_metric(
            Metric(name="fps", fields={"v": 30.0}, timestamp=int(1704067400 * 1e9))
        )

        names = await store.get_metric_names()
        assert "cpu" not in names
        assert "mem" in names
        assert "fps" in names


class TestAddMetricsEvictionInLoop:
    @pytest.mark.asyncio
    async def test_eviction_triggered_inside_add_metrics_loop(self, store):
        """Line 111: _evict_oldest() called per-item when limit reached in add_metrics."""
        store._max_metrics = 2

        await store.add_metrics(
            [
                Metric(name="a", fields={"v": 1.0}, timestamp=int(1e18)),
                Metric(name="b", fields={"v": 2.0}, timestamp=int(2e18)),
            ]
        )

        added = await store.add_metrics(
            [
                Metric(name="c", fields={"v": 3.0}, timestamp=int(3e18)),
                Metric(name="d", fields={"v": 4.0}, timestamp=int(4e18)),
            ]
        )

        assert added == 2
        assert store._total_metrics_count <= 2


class TestDelayedPersist:
    @pytest.mark.asyncio
    async def test_delayed_persist_fires_after_debounce(self, mocker):
        """Lines 255-259: _delayed_persist body executed after debounce window."""
        pushed: list = []

        async def _capture(*args):
            pushed.append(args[0])

        store = MetricsStore(debounce_ms=50)
        mocker.patch.object(store, "_push_to_telegraf", side_effect=_capture)

        # First add: _last_persist_time=0 → immediate push, sets _last_persist_time
        await store.add_metric(Metric(name="m1", fields={"v": 1}))
        initial_count = len(pushed)

        # Second add immediately after: debounce window not yet elapsed → delayed task
        await store.add_metric(Metric(name="m2", fields={"v": 2}))

        # Wait for the debounce task to fire
        await asyncio.sleep(0.15)

        assert len(pushed) > initial_count


class TestHandlePushTaskResult:
    def test_cancelled_task_returns_early(self):
        """Line 311: cancelled task does not inspect exception."""
        mock_task = MagicMock()
        mock_task.cancelled.return_value = True
        MetricsStore._handle_push_task_result(mock_task)
        mock_task.exception.assert_not_called()

    def test_task_with_exception_logs_error(self):
        """Line 314: task exception is logged."""
        mock_task = MagicMock()
        mock_task.cancelled.return_value = False
        mock_task.exception.return_value = RuntimeError("push failed")
        # Should not raise
        MetricsStore._handle_push_task_result(mock_task)

    def test_task_with_no_exception_is_silent(self):
        mock_task = MagicMock()
        mock_task.cancelled.return_value = False
        mock_task.exception.return_value = None
        MetricsStore._handle_push_task_result(mock_task)


class TestPersistToFilesException:
    @pytest.mark.asyncio
    async def test_persist_logs_error_on_snapshot_failure(self, mocker):
        """Lines 301-302: outer except catches snapshot failure."""
        store = MetricsStore(debounce_ms=0)
        mocker.patch.object(
            store, "_persist_to_files_async", side_effect=RuntimeError("snapshot error")
        )
        # Should not propagate the exception
        await store.add_metric(Metric(name="test", fields={"value": 1}))


class TestClose:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("start_push", [False, True])
    async def test_close_cancels_queued_and_active_pushes(self, mocker, start_push):
        started = asyncio.Event()
        session = MagicMock()
        session.closed = False
        session.close = AsyncMock(side_effect=lambda: setattr(session, "closed", True))

        async def pending_response():
            started.set()
            await asyncio.Event().wait()

        response = MagicMock()
        response.__aenter__ = AsyncMock(side_effect=pending_response)
        response.__aexit__ = AsyncMock(return_value=False)
        session.post.return_value = response
        factory = mocker.patch.object(store_module.aiohttp, "ClientSession", return_value=session)
        store = MetricsStore(debounce_ms=0)
        await store.add_metric(Metric(name="test", fields={"value": 1}))
        tasks = tuple(store._push_tasks)
        assert len(tasks) == 1
        if start_push:
            await asyncio.wait_for(started.wait(), timeout=1)
        await store.close()
        await asyncio.sleep(0)
        assert all(task.done() for task in tasks)
        assert not store._push_tasks
        assert store._http_session is None
        if start_push:
            session.close.assert_awaited_once()
        else:
            factory.assert_not_called()
        for operation in (
            store.add_metric(Metric(name="late", fields={"value": 1})),
            store.add_metrics([Metric(name="late", fields={"value": 1})]),
        ):
            with pytest.raises(RuntimeError, match="closed"):
                await operation
        await store.close()

    @pytest.mark.asyncio
    async def test_close_cancels_debounce_before_session_creation(self, mocker):
        factory = mocker.patch.object(store_module.aiohttp, "ClientSession")
        store = MetricsStore(debounce_ms=1000)
        store._last_persist_time = store_module.time.monotonic() * 1000
        await store.add_metric(Metric(name="test", fields={"value": 1}))
        task = store._persist_task
        assert task is not None
        await store.close()
        assert task.cancelled()
        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_with_open_session_closes_and_clears(self):
        """Lines 323-325: close() cleans up an open aiohttp session."""
        store = MetricsStore(debounce_ms=0)
        mock_session = AsyncMock()
        mock_session.closed = False
        store._http_session = mock_session

        await store.close()

        mock_session.close.assert_awaited_once()
        assert store._http_session is None

    @pytest.mark.asyncio
    async def test_close_with_no_session_is_noop(self):
        store = MetricsStore(debounce_ms=0)
        assert store._http_session is None
        await store.close()  # Should not raise


class TestPushToTelegraf:
    @pytest.mark.asyncio
    async def test_push_204_success(self, mocker):
        """Lines 333-345: successful 204 response from Telegraf."""
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_cm)

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientTimeout.return_value = MagicMock()

        mocker.patch.object(store_module, "aiohttp", mock_aiohttp)

        store = MetricsStore(debounce_ms=0)
        store._http_session = mock_session

        await store._push_to_telegraf("test value=1.0\n", 1)
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_non_204_logs_warning(self, mocker):
        """Lines 347-350: non-204 status triggers warning log."""
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_cm)

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientTimeout.return_value = MagicMock()

        mocker.patch.object(store_module, "aiohttp", mock_aiohttp)

        store = MetricsStore(debounce_ms=0)
        store._http_session = mock_session

        await store._push_to_telegraf("test value=1.0\n", 1)
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_creates_new_session_when_none(self, mocker):
        """Line 336: new ClientSession created when _http_session is None."""
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=mock_cm)

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession.return_value = mock_session
        mock_aiohttp.ClientTimeout.return_value = MagicMock()

        mocker.patch.object(store_module, "aiohttp", mock_aiohttp)

        store = MetricsStore(debounce_ms=0)
        # _http_session is None → should create new one
        await store._push_to_telegraf("test value=1.0\n", 1)

        mock_aiohttp.ClientSession.assert_called_once()

    @pytest.mark.asyncio
    async def test_push_exception_is_caught(self, mocker):
        """Line 352: network exception is caught and logged."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=Exception("connection refused"))

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientTimeout.return_value = MagicMock()

        mocker.patch.object(store_module, "aiohttp", mock_aiohttp)

        store = MetricsStore(debounce_ms=0)
        store._http_session = mock_session

        # Should not raise
        await store._push_to_telegraf("test value=1.0\n", 1)


class TestEvictNEdgeCases:
    @pytest.mark.asyncio
    async def test_evict_n_with_zero_does_nothing(self, store):
        """Line 206: _evict_n(0) returns early without evicting."""
        await store.add_metric(Metric(name="test", fields={"v": 1}))
        initial_count = store._total_metrics_count

        await store._evict_n(0)

        assert store._total_metrics_count == initial_count

    @pytest.mark.asyncio
    async def test_evict_oldest_removes_one_metric(self, store):
        """Line 232: _evict_oldest() calls _evict_n(1)."""
        await store.add_metric(Metric(name="a", fields={"v": 1}, timestamp=int(1e18)))
        await store.add_metric(Metric(name="b", fields={"v": 2}, timestamp=int(2e18)))
        initial_count = store._total_metrics_count

        await store._evict_oldest()

        assert store._total_metrics_count == initial_count - 1


class TestPersistEmptyPending:
    @pytest.mark.asyncio
    async def test_persist_early_return_when_no_pending(self, mocker):
        """Line 272: _persist_to_files_async returns early if pending is empty."""
        store = MetricsStore(debounce_ms=0)
        mock_push = mocker.patch.object(store, "_push_to_telegraf")

        # Drain pending (empty the list)
        store._pending_for_push.clear()
        await store._persist_to_files_async()

        # Should not have called _push_to_telegraf
        mock_push.assert_not_called()


class TestAioHttpFallback:
    @pytest.mark.asyncio
    async def test_push_when_aiohttp_not_available(self, mocker):
        """Line 319-320: gracefully handle missing aiohttp."""
        store = MetricsStore(debounce_ms=0)
        mocker.patch.object(store_module, "aiohttp", None)

        # Should not raise, just log warning
        await store._push_to_telegraf("test value=1.0\n", 1)


class TestGetMetricsStore:
    """Tests for the global metrics store singleton."""

    def test_get_metrics_store_returns_same_instance(self):
        """Test that get_metrics_store returns singleton."""
        reset_metrics_store()
        store1 = get_metrics_store()
        store2 = get_metrics_store()
        assert store1 is store2

    def test_reset_metrics_store(self):
        """Test that reset creates new instance."""
        store1 = get_metrics_store()
        reset_metrics_store()
        store2 = get_metrics_store()
        assert store1 is not store2
