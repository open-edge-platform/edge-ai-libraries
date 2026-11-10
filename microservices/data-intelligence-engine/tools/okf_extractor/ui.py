# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import itertools
import sys
import threading
import time

_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class UI:
    def __init__(self, stream=None, enabled: bool | None = None):
        self.stream = stream or sys.stderr
        # auto-detect: animate only on a real tty (unless forced)
        self.tty = self.stream.isatty() if hasattr(self.stream, "isatty") else False
        self.enabled = self.tty if enabled is None else enabled
        self._t0 = time.monotonic()
        self._spinner: _Spinner | None = None

    def stage(self, text: str) -> None:
        self._line(f"\n\033[1m▌ {text}\033[0m" if self.tty else f"\n== {text}")

    def session(self, text: str) -> None:
        self._line(f"\033[36m◆ {text}\033[0m" if self.tty else f"-- {text}")

    def info(self, text: str) -> None:
        self._line(f"  {text}")

    def warn(self, text: str) -> None:
        self._line(f"\033[33m  ! {text}\033[0m" if self.tty else f"  ! {text}")

    def tool(self, name: str, detail: str = "", result: str = "") -> None:
        arrow = "\033[32m→\033[0m" if self.tty else "->"
        head = f"  {arrow} \033[1m{name}\033[0m" if self.tty else f"  -> {name}"
        parts = [head]
        if detail:
            parts.append(detail)
        if result:
            parts.append(f"\033[2m{result}\033[0m" if self.tty else f"({result})")
        self._line(" ".join(parts))

    def spinner(self, label: str) -> "_Spinner":
        return _Spinner(self, label)

    def ask(self, finding_type: str, message: str, options: list[str] | None = None) -> str:
        """Block for a human answer on the terminal; returns the chosen option or the free-text line."""
        if self._spinner and self._spinner.alive:
            self._spinner._clear()
        bar = "\033[35m" if self.tty else ""
        end = "\033[0m" if self.tty else ""
        print(f"\n{bar}◇ agent asks [{finding_type}]{end}", file=self.stream, flush=True)
        for line in message.splitlines():
            print(f"  {line}", file=self.stream, flush=True)
        if options:
            for i, opt in enumerate(options, 1):
                print(f"    {i}) {opt}", file=self.stream, flush=True)
            print("  (enter a number, or type free text)", file=self.stream, flush=True)
        try:
            raw = input("  > ").strip()
        except EOFError:
            raw = ""
        if options and raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        return raw

    def _line(self, text: str) -> None:
        # if a spinner is live, clear its line before printing a permanent line
        if self._spinner and self._spinner.alive:
            self._spinner._clear()
        print(text, file=self.stream, flush=True)


class _Spinner:
    """Context manager animating `label … (Ns)` on a tty; prints one start line otherwise."""

    def __init__(self, ui: UI, label: str):
        self.ui = ui
        self.label = label
        self.alive = False
        self._stop = threading.Event()
        self._th: threading.Thread | None = None

    def __enter__(self) -> "_Spinner":
        if self.ui.enabled and self.ui.tty:
            self.alive = True
            self.ui._spinner = self
            self._th = threading.Thread(target=self._run, daemon=True)
            self._th.start()
        else:
            print(f"  … {self.label}", file=self.ui.stream, flush=True)
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._th:
            self._th.join(timeout=1.0)
        if self.alive:
            self._clear()
        self.alive = False
        self.ui._spinner = None

    def _run(self) -> None:
        t0 = time.monotonic()
        for ch in itertools.cycle(_SPIN):
            if self._stop.is_set():
                break
            dt = time.monotonic() - t0
            msg = f"\r\033[36m{ch}\033[0m {self.label} \033[2m({dt:.0f}s)\033[0m"
            self.ui.stream.write(msg)
            self.ui.stream.flush()
            time.sleep(0.1)

    def _clear(self) -> None:
        self.ui.stream.write("\r\033[2K")   # CR + clear whole line
        self.ui.stream.flush()
