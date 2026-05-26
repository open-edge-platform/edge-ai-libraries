# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Helpers for locating and activating per-plugin virtual environments.

entrypoint.sh creates /opt/.venv-<plugin> for each activated plugin and records
the paths in /opt/plugin_venvs.env.  These utilities let plugin code find the
right Python executable and build an activation environment dict suitable for
passing to subprocess.Popen / subprocess.run.
"""

import os
import shlex
from functools import lru_cache
from pathlib import Path

_PLUGIN_VENVS_FILE = "/opt/plugin_venvs.env"


@lru_cache(maxsize=None)
def _read_venv_file() -> dict[str, str]:
    """Parse /opt/plugin_venvs.env and return a {PLUGIN_NAME_UPPER: path} dict."""
    result: dict[str, str] = {}
    if not os.path.exists(_PLUGIN_VENVS_FILE):
        return result
    with open(_PLUGIN_VENVS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
    return result


def get_plugin_venv_path(plugin_name: str) -> str | None:
    """Return the root path of the plugin's dedicated venv, or None."""
    env_key = f"PLUGIN_VENV_{plugin_name.upper()}"
    # Prefer an explicit environment variable (useful in tests / override scenarios)
    venv_path = os.getenv(env_key)
    if not venv_path:
        venv_path = _read_venv_file().get(env_key)
    return venv_path or None


def get_plugin_venv_python(plugin_name: str) -> str:
    """Return the Python executable for a plugin's venv.

    Falls back to ``python3`` if no dedicated venv was created (e.g. running
    outside Docker or when the plugin has no Python extras).
    """
    venv_path = get_plugin_venv_path(plugin_name)
    if venv_path:
        python = Path(venv_path) / "bin" / "python"
        if python.exists():
            return str(python)
    return "python3"


def get_plugin_venv_env(plugin_name: str, base_env: dict | None = None) -> dict:
    """Return an environment dict with the plugin's venv activated.

    Sets ``VIRTUAL_ENV`` and prepends the venv's ``bin/`` directory to
    ``PATH``, matching what ``source venv/bin/activate`` does in a shell.
    Any ``PYTHONHOME`` is removed to avoid interpreter conflicts.

    Args:
        plugin_name: The plugin identifier (e.g. ``"openvino"``).
        base_env: Starting environment dict.  Defaults to ``os.environ.copy()``.

    Returns:
        A new dict suitable for passing as ``env=`` to subprocess calls.
    """
    env = dict(base_env) if base_env is not None else os.environ.copy()

    venv_path = get_plugin_venv_path(plugin_name)
    if not venv_path:
        return env

    venv_bin = str(Path(venv_path) / "bin")
    env["VIRTUAL_ENV"] = venv_path
    env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
    env.pop("PYTHONHOME", None)
    return env


def build_venv_command(plugin_name: str, command: list[str]) -> list[str]:
    """Wrap a command list to run inside the plugin venv via ``bash source activate``.

    Using ``source activate`` ensures Python's ``sys.path`` is fully set up
    from the venv (including all transitively installed packages), which is
    more reliable than relying solely on the venv interpreter path when a
    ``PYTHONPATH`` override is present in the environment.

    Falls back to the original command unchanged if no venv path is found.

    Args:
        plugin_name: The plugin identifier (e.g. ``"openvino"``).
        command: The command + arguments list to wrap.

    Returns:
        A ``["bash", "-c", "source <activate> && <command>"]`` list, or the
        original ``command`` list when no dedicated venv exists.
    """
    venv_path = get_plugin_venv_path(plugin_name)
    if not venv_path:
        return command

    activate = str(Path(venv_path) / "bin" / "activate")
    cmd = list(command)
    # Replace an explicit venv-python path with plain "python" so the
    # activated PATH resolves to the correct interpreter.
    venv_python = str(Path(venv_path) / "bin" / "python")
    if cmd and cmd[0] == venv_python:
        cmd[0] = "python"

    return ["bash", "-c", f"source {shlex.quote(activate)} && {shlex.join(cmd)}"]
