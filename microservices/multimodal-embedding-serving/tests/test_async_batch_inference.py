# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Concurrency regression tests for ``AsyncBatchInference``.

A single ``AsyncBatchInference`` instance is shared by every caller of the
handler that owns it. Before the instance lock was added, two concurrent
callers would race on ``AsyncInferQueue.set_callback``: the second caller
replaced the callback while the first caller's requests were still in flight,
so completions from the first call wrote into the second call's (differently
sized) output buffer. That surfaced as
``ValueError: could not broadcast input array from shape (16,512) into shape
(9,512)`` raised inside an OpenVINO C++ callback thread, which aborted the
whole worker process with SIGABRT.
"""

import sys
import threading
import types
import unittest
from unittest import mock

import numpy as np

# ``openvino`` is heavy and unnecessary here: stub it before importing the
# module under test so these tests stay fast and dependency-free.
if "openvino" not in sys.modules:
    openvino_stub = types.ModuleType("openvino")
    openvino_stub.CompiledModel = object
    openvino_stub.AsyncInferQueue = object
    openvino_stub.Core = object
    openvino_stub.save_model = lambda *a, **k: None
    openvino_stub.convert_model = lambda *a, **k: None
    sys.modules["openvino"] = openvino_stub

from src.models.utils.openvino_utils import AsyncBatchInference  # noqa: E402


class FakeRequest:
    """Stands in for an OpenVINO infer request holding one output tensor."""

    def __init__(self, data: np.ndarray):
        self.output_tensors = [types.SimpleNamespace(data=data)]


class FakeAsyncInferQueue:
    """Minimal ``AsyncInferQueue`` double.

    Completions are deferred until ``wait_all`` so that a competing caller has
    a window to overwrite the callback, which is exactly the production race.
    """

    def __init__(self, embedding_dim: int = 512):
        self.embedding_dim = embedding_dim
        self._callback = None
        self._pending = []
        self.started_at_callback_swap = []

    def set_callback(self, callback):
        self._callback = callback

    def is_ready(self):
        return True

    def start_async(self, inputs, userdata):
        batch = inputs[0]
        # The model always returns a full compiled batch worth of rows.
        out = np.ones((batch.shape[0], self.embedding_dim), dtype=np.float32)
        self._pending.append((FakeRequest(out), userdata))

    def wait_all(self):
        pending, self._pending = self._pending, []
        for request, userdata in pending:
            self._callback(request, userdata)


def _make_inference(batch_size: int, embedding_dim: int = 512) -> AsyncBatchInference:
    with mock.patch(
        "src.models.utils.openvino_utils.ov.AsyncInferQueue",
        lambda _model: FakeAsyncInferQueue(embedding_dim),
    ):
        return AsyncBatchInference(
            compiled_model=object(),
            embedding_dim=embedding_dim,
            preprocess_shape=(batch_size, 3, 224, 224),
        )


def _batches(counts, batch_size):
    for count in counts:
        yield np.zeros((count, 3, 224, 224), dtype=np.float32)


class TestAsyncBatchInferenceConcurrency(unittest.TestCase):
    def test_infer_stream_returns_expected_shape(self):
        inference = _make_inference(batch_size=16)

        result = inference.infer_stream(_batches([9], 16), total_images=9)

        self.assertEqual(result.shape, (9, 512))

    def test_concurrent_infer_stream_calls_do_not_corrupt_each_other(self):
        """Two callers with different totals must both get their own buffer.

        The interleaving is forced rather than left to chance: caller "a"
        submits its requests and then pauses before draining them, giving
        caller "b" a window to install its own callback. That is the exact
        shape pairing from the crash (16 images vs 9 images). With the
        instance lock, "b" is blocked at the entry to ``infer_stream``, so the
        window simply expires.
        """
        inference = _make_inference(batch_size=16)
        queue = inference.async_queue

        names = {}
        a_submitted = threading.Event()
        b_installed_callback = threading.Event()

        original_set_callback = queue.set_callback
        original_wait_all = queue.wait_all

        def set_callback(callback):
            original_set_callback(callback)
            if names.get(threading.get_ident()) == "b":
                b_installed_callback.set()

        def wait_all():
            if names.get(threading.get_ident()) == "a":
                a_submitted.set()
                b_installed_callback.wait(timeout=0.5)
            original_wait_all()

        queue.set_callback = set_callback
        queue.wait_all = wait_all

        results = {}
        errors = []

        def run(name, total):
            names[threading.get_ident()] = name
            try:
                results[name] = inference.infer_stream(
                    _batches([total], 16), total_images=total
                )
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        thread_a = threading.Thread(target=run, args=("a", 16))
        thread_b = threading.Thread(target=run, args=("b", 9))

        thread_a.start()
        self.assertTrue(a_submitted.wait(timeout=5), "caller 'a' never submitted")
        thread_b.start()

        for thread in (thread_a, thread_b):
            thread.join(timeout=10)

        self.assertEqual(errors, [], f"concurrent inference raised: {errors}")
        self.assertEqual(results["a"].shape, (16, 512))
        self.assertEqual(results["b"].shape, (9, 512))
        # Every row must come from this caller's own completions.
        self.assertTrue(np.all(results["a"] == 1.0))
        self.assertTrue(np.all(results["b"] == 1.0))

    def test_many_concurrent_callers_are_serialized(self):
        inference = _make_inference(batch_size=16)
        totals = [3, 16, 7, 12, 9, 1, 16, 5]
        results = [None] * len(totals)
        errors = []

        def run(index, total):
            try:
                results[index] = inference.infer_stream(
                    _batches([total], 16), total_images=total
                )
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [
            threading.Thread(target=run, args=(i, total))
            for i, total in enumerate(totals)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(errors, [])
        for total, result in zip(totals, results):
            self.assertEqual(result.shape, (total, 512))

    def test_callback_failure_is_raised_in_calling_thread(self):
        """A callback error must surface as a Python exception, not an abort."""
        inference = _make_inference(batch_size=16)

        def exploding_batches():
            yield np.zeros((4, 3, 224, 224), dtype=np.float32)

        original = inference.async_queue.start_async

        def start_async(inputs, userdata):
            # Force the callback to write more rows than the buffer holds.
            original(inputs, {"start": 0, "count": 99})

        inference.async_queue.start_async = start_async

        with self.assertRaises(ValueError):
            inference.infer_stream(exploding_batches(), total_images=4)

    def test_lock_is_released_after_a_failed_call(self):
        inference = _make_inference(batch_size=16)

        def failing_batches():
            raise RuntimeError("generator blew up")
            yield  # pragma: no cover

        with self.assertRaises(RuntimeError):
            inference.infer_stream(failing_batches(), total_images=4)

        # A subsequent caller must not deadlock on the instance lock.
        result = inference.infer_stream(_batches([5], 16), total_images=5)
        self.assertEqual(result.shape, (5, 512))


class TestAsyncBatchInferenceInfer(unittest.TestCase):
    def test_infer_returns_expected_shape(self):
        inference = _make_inference(batch_size=16)

        result = inference.infer(np.zeros((20, 3, 224, 224), dtype=np.float32))

        self.assertEqual(result.shape, (20, 512))

    def test_concurrent_infer_calls_do_not_corrupt_each_other(self):
        inference = _make_inference(batch_size=16)
        results = {}
        errors = []
        start = threading.Barrier(2)

        def run(name, total):
            try:
                start.wait(timeout=5)
                results[name] = inference.infer(
                    np.zeros((total, 3, 224, 224), dtype=np.float32)
                )
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [
            threading.Thread(target=run, args=("a", 16)),
            threading.Thread(target=run, args=("b", 9)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(errors, [], f"concurrent inference raised: {errors}")
        self.assertEqual(results["a"].shape, (16, 512))
        self.assertEqual(results["b"].shape, (9, 512))


if __name__ == "__main__":
    unittest.main()
