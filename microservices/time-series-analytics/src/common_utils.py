# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared assertion and shell-free command helpers."""

import os
import subprocess  # nosec B404 # command helpers explicitly disable shell execution
from typing import Sequence


def assert_condition(condition, message=""):
    """Fail a test when condition is false."""
    if not condition:
        raise AssertionError(message)


def exec_command(
        command: Sequence[str],
        *,
        capture_output: bool = False,
        check: bool = False,
        text: bool = True,
        **kwargs) -> subprocess.CompletedProcess:
    """Execute a command safely without shell invocation."""
    command = list(command)
    if command and os.path.basename(str(command[0])) == "make" and "-e" not in command[1:]:
        command.insert(1, "-e")
    return subprocess.run(
        command,
        shell=False,
        capture_output=capture_output,
        check=check,
        text=text,
        **kwargs,
    )  # nosec B603