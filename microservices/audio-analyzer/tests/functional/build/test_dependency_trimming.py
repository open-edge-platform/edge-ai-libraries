# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 3 — Dependency-Trimming Regression Tests (triton / torchcodec removal)
=============================================================================
Builds the real production image (docker/Dockerfile, the Dockerfile
referenced by docker-compose.yml and CI) and verifies that the
intentional post-install removal of `triton` and `torchcodec` actually
took effect, and that `pip check` does not drift to report any *other*
broken dependency over time.

Background: `triton` (~0.9-1.2GB) is a hard dependency of `openai-whisper`
but is only reachable via a CUDA-only lazy-import guard that the CPU-only
`openai` ASR provider can never trigger. `torchcodec` is a hard dependency
of `pyannote.audio` but the diarizer reads audio via `soundfile` and hands
pyannote an in-memory waveform instead of a file path, so torchcodec's
decoder is never invoked (see tests/test_pyannote_diarizer.py::
test_diarize_reads_waveform_without_torchaudio_decoder). Both packages are
uninstalled post-install in docker/Dockerfile / Dockerfile to save space.

Run:
    pytest tests/functional/build/test_dependency_trimming.py -m tier3 -v -s

Prerequisites:
  - Docker installed and daemon running
  - Run from the audio-analyzer repo root
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = "docker/Dockerfile"
IMAGE_TAG = "audio-analyzer:test-dependency-trimming"
BUILD_TIMEOUT_SEC = 900  # 15 min — covers base image pull + pip install

# Packages intentionally uninstalled post-install for image-size reduction.
# `pip check` will always report these as "required but not installed"
# — that is expected and intentional, not a regression. See docker/Dockerfile
# comments next to the `pip uninstall -y triton` / `torchcodec` lines and the
# `rm -rf .../pip* setuptools* wheel*` step, and tests/test_openai_whisper_triton.py
# for the runtime-behavior proof that removing triton/torchcodec is safe.
# `setuptools` is declared as a runtime requirement by `torch`'s metadata
# (distutils-replacement shim), but is never imported by this service and is
# deliberately stripped from the final image alongside `pip`/`wheel`.
EXPECTED_PIP_CHECK_MISSING = {"triton", "torchcodec", "setuptools"}


def _docker_available() -> tuple[bool, str]:
    if shutil.which("docker") is None:
        return False, "docker binary not found on PATH"
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return False, f"Docker daemon not reachable: {exc}"
    if result.returncode != 0:
        return False, f"Docker daemon not reachable: {result.stderr.strip()[:200]}"
    return True, ""


@pytest.fixture(scope="module")
def built_image():
    """Build docker/Dockerfile once for this module; remove it afterwards."""
    ok, reason = _docker_available()
    if not ok:
        pytest.skip(f"Docker not available — {reason}")

    build = subprocess.run(
        ["docker", "build", "-f", DOCKERFILE, "-t", IMAGE_TAG, "."],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=BUILD_TIMEOUT_SEC,
    )
    if build.returncode != 0:
        print("\n── docker build STDOUT ──\n", build.stdout[-4000:])
        print("── docker build STDERR ──\n", build.stderr[-4000:])
    assert build.returncode == 0, (
        f"`docker build -f {DOCKERFILE}` failed (exit {build.returncode}).\n"
        f"Last stderr:\n{build.stderr.strip()[-1000:]}"
    )

    yield IMAGE_TAG

    subprocess.run(["docker", "rmi", "-f", IMAGE_TAG], capture_output=True, text=True)


def _run_in_image(image_tag: str, shell_cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "bash", image_tag, "-c", shell_cmd],
        capture_output=True,
        text=True,
        timeout=120,
    )


# Query installed distributions via the runtime python3.12 interpreter's
# stdlib importlib.metadata, NOT `pip` — `pip` and its console script are
# deliberately removed from the production image (see docker/Dockerfile),
# so `pip list`/`pip check` fail with "command not found" there. Combined
# with `|| true`, that previously made these tests pass without actually
# inspecting the image.
_LIST_DISTRIBUTIONS_SCRIPT = (
    "import importlib.metadata as m; "
    "print('\\n'.join(sorted(d.metadata['Name'].lower() for d in m.distributions() "
    "if d.metadata.get('Name'))))"
)


def _installed_distribution_names(image_tag: str) -> set[str]:
    """Lowercased distribution names installed in the image's venv."""
    result = _run_in_image(image_tag, f'python3.12 -c "{_LIST_DISTRIBUTIONS_SCRIPT}"')
    assert result.returncode == 0, (
        f"Failed to query installed distributions inside {image_tag} "
        f"(exit {result.returncode}).\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


class TestDependencyTrimming:

    @pytest.mark.tier3
    def test_triton_absent_from_built_image(self, built_image):
        """`triton` must not be present in the built production image."""
        installed = _installed_distribution_names(built_image)
        assert "triton" not in installed, (
            f"Expected triton to be absent from the image, but it is installed "
            f"(queried via importlib.metadata, not pip)."
        )

    @pytest.mark.tier3
    def test_torchcodec_absent_from_built_image(self, built_image):
        """`torchcodec` must not be present in the built production image."""
        installed = _installed_distribution_names(built_image)
        assert "torchcodec" not in installed, (
            f"Expected torchcodec to be absent from the image, but it is installed "
            f"(queried via importlib.metadata, not pip)."
        )

    @pytest.mark.tier3
    def test_pip_check_reports_only_expected_warnings(self, built_image):
        """
        Dependency-graph equivalent of `pip check`, but implemented with the
        runtime interpreter's own importlib.metadata + packaging (both
        present in the image; `pip` is not) so it genuinely inspects the
        final environment instead of silently no-opping when `pip` is
        missing. Only the two known, intentional removals (triton via
        openai-whisper, torchcodec via pyannote-audio) are expected to be
        reported as missing requirements. If a *different* package starts
        appearing here, a dependency has broken unexpectedly and this test
        must fail to flag the regression.
        """
        script = r"""
import importlib.metadata as m
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

installed = {canonicalize_name(d.metadata["Name"]): d for d in m.distributions() if d.metadata.get("Name")}
missing = {}
for name, dist in installed.items():
    for raw_req in dist.requires or []:
        try:
            req = Requirement(raw_req)
        except Exception:
            continue
        if req.marker is not None:
            try:
                if not req.marker.evaluate({"extra": ""}):
                    continue
            except Exception:
                pass
        base = canonicalize_name(req.name)
        if base not in installed:
            missing.setdefault(base, set()).add(name)
for pkg in sorted(missing):
    print(f"{pkg}::{','.join(sorted(missing[pkg]))}")
"""
        result = _run_in_image(built_image, f"python3.12 - <<'PYEOF'\n{script}\nPYEOF")
        assert result.returncode == 0, (
            f"Dependency-graph check failed to execute inside the image "
            f"(exit {result.returncode}).\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

        offending_packages = {
            line.split("::", 1)[0] for line in result.stdout.splitlines() if "::" in line
        }
        unexpected = offending_packages - EXPECTED_PIP_CHECK_MISSING
        assert not unexpected, (
            f"Dependency check reported unexpected broken dependencies: {unexpected}. "
            f"Only {EXPECTED_PIP_CHECK_MISSING} are expected (intentionally "
            f"removed). Full output:\n{result.stdout}\n{result.stderr}"
        )

    @pytest.mark.tier3
    def test_installed_versions_satisfy_requirement_specifiers(self, built_image):
        """
        `test_pip_check_reports_only_expected_warnings` only checks that each
        required package is *present*; it does not check that the installed
        *version* actually satisfies the requiring package's version
        specifier (e.g. `foo>=2.0,<3.0`). A present-but-wrong-version package
        would silently pass that test. This test closes that gap by
        re-walking the same dependency graph and asserting every declared
        specifier is satisfied by what is actually installed.
        """
        script = r"""
import importlib.metadata as m
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

installed = {canonicalize_name(d.metadata["Name"]): d for d in m.distributions() if d.metadata.get("Name")}
mismatched = {}
for name, dist in installed.items():
    for raw_req in dist.requires or []:
        try:
            req = Requirement(raw_req)
        except Exception:
            continue
        if req.marker is not None:
            try:
                if not req.marker.evaluate({"extra": ""}):
                    continue
            except Exception:
                pass
        base = canonicalize_name(req.name)
        target = installed.get(base)
        if target is None:
            continue  # absence is covered by test_pip_check_reports_only_expected_warnings
        installed_version = target.metadata["Version"]
        if req.specifier and not req.specifier.contains(installed_version, prereleases=True):
            mismatched.setdefault(base, set()).add(
                f"{name} requires {base}{req.specifier}, found {installed_version}"
            )
for pkg in sorted(mismatched):
    for detail in sorted(mismatched[pkg]):
        print(f"{pkg}::{detail}")
"""
        result = _run_in_image(built_image, f"python3.12 - <<'PYEOF'\n{script}\nPYEOF")
        assert result.returncode == 0, (
            f"Dependency version-specifier check failed to execute inside the image "
            f"(exit {result.returncode}).\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

        assert not result.stdout.strip(), (
            f"Installed package versions do not satisfy their requirers' version "
            f"specifiers:\n{result.stdout}\n{result.stderr}"
        )
