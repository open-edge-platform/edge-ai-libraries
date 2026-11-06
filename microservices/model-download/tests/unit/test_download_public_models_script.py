# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for scripts/download_public_models.sh.

The script runs inside a throwaway virtualenv that does not contain the
service dependencies (fastapi, structlog). ``extract_zip_safely`` must
therefore work with the standard library only.
"""

import re
import subprocess
import textwrap
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "download_public_models.sh"


def _extract_function() -> str:
    text = SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(r"^extract_zip_safely\(\) \{\n.*?^\}\n", text, re.S | re.M)
    assert match, "extract_zip_safely not found in download_public_models.sh"
    return match.group(0).replace("${BASH_SOURCE[0]}", str(SCRIPT))


@pytest.fixture
def stdlib_only_python_env(tmp_path):
    """Environment in which importing fastapi or structlog fails."""
    blocker = tmp_path / "blocker"
    blocker.mkdir()
    (blocker / "sitecustomize.py").write_text(
        "import sys\nsys.modules['fastapi'] = None\nsys.modules['structlog'] = None\n"
    )
    return {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(blocker)}


def _run_extract(tmp_path, env, members):
    archive = tmp_path / "model.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for name in members:
            zf.writestr(name, "x")
    dest = tmp_path / "out"
    script = textwrap.dedent(
        f"""
        set -u
        {_extract_function()}
        extract_zip_safely "{archive}" "{dest}"
        """
    )
    result = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=False
    )
    return result, dest


def test_extract_zip_safely_without_service_dependencies(tmp_path, stdlib_only_python_env):
    result, dest = _run_extract(
        tmp_path,
        stdlib_only_python_env,
        ["deployment/model/model.xml", "deployment/model/model.bin"],
    )
    assert result.returncode == 0, result.stderr
    assert (dest / "deployment/model/model.xml").is_file()


def test_extract_zip_safely_rejects_zip_slip(tmp_path, stdlib_only_python_env):
    result, dest = _run_extract(
        tmp_path,
        stdlib_only_python_env,
        ["../evil.xml", "model.bin"],
    )
    assert result.returncode != 0
    assert "resolves outside target directory" in result.stderr
    assert not (tmp_path / "evil.xml").exists()

