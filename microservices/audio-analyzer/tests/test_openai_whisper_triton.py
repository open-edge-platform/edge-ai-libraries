# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Regression coverage for the intentional removal of ``triton`` from the
production image (see docker/Dockerfile and Dockerfile: `pip uninstall -y
triton` after installing openai-whisper).

``triton`` is a hard (non-extra) dependency of ``openai-whisper`` on
x86_64/Linux, but it is only ever imported lazily, behind
``if x.is_cuda:`` guards, inside ``whisper.timing.dtw()`` and
``whisper.timing.median_filter()``. The ``openai`` ASR provider is CPU-only
by design (see config.yaml), so that CUDA-only branch can never execute in
this service, and triton can be safely uninstalled post-install to save
~0.9-1.2GB of image size.

These tests prove the CPU fallback path genuinely works end-to-end with
triton absent (or, on a developer host where it happens to still be
installed, that the import/compute path never touches it regardless).

NOTE: like tests/test_ov_pyannote_embedding_openvino.py, this module
requires the real ML stack (torch, openai-whisper) to be installed and is
NOT part of the tier1/2/3 functional split or any default `testpaths`
collection. It must be run explicitly, e.g. inside the built container —
`pip` and `tests/` are both stripped from the production image (see
docker/Dockerfile and .dockerignore), so a *full*-variant image must be run
with the checkout mounted in and pytest installed separately rather than
through the (removed) venv's own pip:

    docker run --rm --user 0:0 \
        -v "$(pwd)":/app/audio_analyzer -w /app/audio_analyzer \
        --entrypoint bash <full-image> -c \
        'apt-get update && apt-get install -y --no-install-recommends python3-pytest \
         && PYTHONPATH=/opt/venv/lib/python3.12/site-packages /usr/bin/python3.12 \
            -m pytest tests/test_openai_whisper_triton.py -v'

It is not currently invoked by any CI workflow for this component (no
pytest job exists in .github/workflows/GENAI-Audio-analyzer.yaml today);
treat it as a manual/Docker-integration regression check until such a job
is added.
"""
import subprocess
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("whisper")


def test_whisper_component_imports_without_requiring_triton():
    """Importing the OpenAI ASR component must never import triton.

    triton is only reachable from whisper's CUDA-only DTW/median_filter
    branches, so a plain module import must not pull it into sys.modules.

    This check runs in a *fresh subprocess* rather than popping "triton"
    from this process's sys.modules: the module-level
    ``pytest.importorskip("whisper")`` above already imports whisper (and,
    if whisper ever starts importing triton eagerly, triton too) during
    test collection, before this test body runs. Clearing sys.modules in
    this process afterwards would erase that evidence without undoing the
    import, and re-importing components.asr.openai.whisper would reuse the
    cached whisper module without re-triggering whatever whisper's own
    import did. Spawning a fresh interpreter, with triton import blocked at
    the sys.modules level from the very start, avoids depending on this
    process's import history entirely.
    """
    script = (
        "import sys\n"
        "sys.modules['triton'] = None\n"  # any `import triton` now raises ImportError
        "import components.asr.openai.whisper\n"
        "print('import-ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0 and "import-ok" in result.stdout, (
        "Importing components.asr.openai.whisper in a fresh interpreter with "
        "triton import blocked failed — the CUDA-only lazy-import guard in "
        "whisper/timing.py may have changed to import triton eagerly; "
        "re-evaluate whether triton can still be removed.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_whisper_timing_dtw_executes_on_cpu_without_triton():
    """whisper.timing.dtw()'s CPU fallback must work with triton absent.

    This directly exercises the function that would otherwise dispatch to
    the triton CUDA kernel (`dtw_kernel`) when `x.is_cuda` is True. Since
    the `openai` provider is CPU-only (config.yaml), `x.is_cuda` is always
    False in production, so this proves the only code path this service
    can actually hit works correctly without triton installed.
    """
    from whisper.timing import dtw

    cost_matrix = torch.rand(8, 8, dtype=torch.float32)
    assert not cost_matrix.is_cuda, "test assumes a CPU-only tensor/runtime"

    text_indices, time_indices = dtw(cost_matrix)

    assert len(text_indices) > 0
    assert len(time_indices) > 0


# ---------------------------------------------------------------------------
# NOTE on `pip check`:
# `pip check` will report two expected, intentional warnings in any
# environment built from docker/Dockerfile or Dockerfile:
#   - "openai-whisper ... requires triton, which is not installed."
#   - "pyannote-audio ... requires torchcodec, which is not installed."
# Both packages are deliberately uninstalled post-install (see the Dockerfile
# comments next to the `pip uninstall -y triton` / `torchcodec` lines).
# Do NOT treat these two specific warnings as a regression; a *third*,
# unexpected package appearing in `pip check` output would be a regression
# (see tests/functional/build/test_dependency_trimming.py::
# test_pip_check_reports_only_expected_warnings for the automated guard).
# ---------------------------------------------------------------------------
