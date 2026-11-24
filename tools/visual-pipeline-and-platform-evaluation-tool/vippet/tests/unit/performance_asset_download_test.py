# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for perf_helpers.asset_download (shared download helpers)."""

import threading
import unittest

from tests.performance.perf_helpers import asset_download as ad


class TestDownloadAction(unittest.TestCase):
    def test_modes(self) -> None:
        self.assertEqual(ad.download_action("yes", False), "install")
        self.assertEqual(ad.download_action("yes", True), "install")
        self.assertEqual(ad.download_action("ask", True), "prompt")
        # Without a terminal "ask" must never block.
        self.assertEqual(ad.download_action("ask", False), "skip")
        self.assertEqual(ad.download_action("no", True), "skip")


class TestCleanText(unittest.TestCase):
    def test_escapes_and_controls_are_removed(self) -> None:
        self.assertEqual(ad.clean_text("a\x1b[31mb\x1b]0;t\x07c\n\td\x00"), "abc d")
        self.assertEqual(ad.clean_text(None), "")
        self.assertEqual(ad.clean_text("x" * 10, max_length=5), "xx...")

    def test_clean_link_accepts_http_only(self) -> None:
        self.assertEqual(ad.clean_link("https://a.b/c"), "https://a.b/c")
        self.assertEqual(ad.clean_link("javascript:alert(1)"), "")


class TestInterruptibleSleep(unittest.TestCase):
    def test_raises_once_stopped(self) -> None:
        stop = threading.Event()
        slept: list[float] = []
        wait = ad.interruptible_sleep(stop, slept.append)
        wait(1.0)
        self.assertEqual(slept, [1.0])
        stop.set()
        with self.assertRaises(KeyboardInterrupt):
            wait(1.0)
        self.assertEqual(slept, [1.0])

    def test_default_wait_ends_early_when_stopped(self) -> None:
        stop = threading.Event()
        wait = ad.interruptible_sleep(stop)
        threading.Timer(0.05, stop.set).start()
        with self.assertRaises(KeyboardInterrupt):
            wait(30)


class TestRunConcurrently(unittest.TestCase):
    def test_results_keep_task_order(self) -> None:
        stop = threading.Event()
        self.assertEqual(ad.run_concurrently([lambda: 1, lambda: 2], stop), [1, 2])
        self.assertEqual(ad.run_concurrently([lambda: 3], stop), [3])

    def test_tasks_run_at_the_same_time(self) -> None:
        started = threading.Barrier(2, timeout=5)

        def task() -> str:
            started.wait()  # Deadlocks (BrokenBarrierError) if run one by one.
            return "ok"

        self.assertEqual(
            ad.run_concurrently([task, task], threading.Event()), ["ok", "ok"]
        )

    def test_unexpected_task_error_is_raised(self) -> None:
        def boom() -> None:
            raise RuntimeError("boom")

        with self.assertRaisesRegex(RuntimeError, "boom"):
            ad.run_concurrently([lambda: None, boom], threading.Event())


class TestDecodeOutcomeEnv(unittest.TestCase):
    def test_error_names_the_variable(self) -> None:
        with self.assertRaisesRegex(ad.OutcomeEnvError, "MY_ENV"):
            ad.decode_outcome_env(
                "[1]", env_name="MY_ENV", keys=("name", "outcome"), outcomes={"ok"}
            )

    def test_valid_list(self) -> None:
        self.assertEqual(
            ad.decode_outcome_env(
                '[{"name": "a", "outcome": "ok"}]',
                env_name="X",
                keys=("name", "outcome"),
                outcomes={"ok"},
            ),
            [{"name": "a", "outcome": "ok"}],
        )


if __name__ == "__main__":
    unittest.main()
