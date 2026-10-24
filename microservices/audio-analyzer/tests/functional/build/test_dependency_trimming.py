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
# `pip check` will always report these two as "required but not installed"
# — that is expected and intentional, not a regression. See docker/Dockerfile
# comments next to the `pip uninstall -y triton` / `torchcodec` lines, and
# tests/test_openai_whisper_triton.py for the runtime-behavior proof that
# removing them is safe.
EXPECTED_PIP_CHECK_MISSING = {"triton", "torchcodec"}


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


class TestDependencyTrimming:

    @pytest.mark.tier3
    def test_triton_absent_from_built_image(self, built_image):
        """`triton` must not be present in the built production image."""
        result = _run_in_image(built_image, "pip list --format=freeze | grep -i '^triton' || true")
        assert result.stdout.strip() == "", (
            f"Expected triton to be absent from the image, found: {result.stdout.strip()!r}"
        )

    @pytest.mark.tier3
    def test_torchcodec_absent_from_built_image(self, built_image):
        """`torchcodec` must not be present in the built production image."""
        result = _run_in_image(built_image, "pip list --format=freeze | grep -i '^torchcodec' || true")
        assert result.stdout.strip() == "", (
            f"Expected torchcodec to be absent from the image, found: {result.stdout.strip()!r}"
        )

    @pytest.mark.tier3
    def test_pip_check_reports_only_expected_warnings(self, built_image):
        """
        `pip check` is expected to fail with exactly the two known,
        intentional warnings (triton via openai-whisper, torchcodec via
        pyannote-audio). If a *different* package starts appearing here, a
        dependency has broken unexpectedly and this test must fail to flag
        the regression.
        """
        result = _run_in_image(built_image, "pip check")

        if result.returncode == 0:
            # Nothing broken at all — stricter than required, not a failure.
            return

        offending_packages = set()
        for line in result.stdout.splitlines() + result.stderr.splitlines():
            line = line.strip()
            if not line or "requires" not in line:
                continue
            # Typical line: "openai-whisper 20250625 requires triton, which is not installed."
            missing = line.split("requires", 1)[1].split(",", 1)[0].strip()
            offending_packages.add(missing.lower())

        unexpected = offending_packages - EXPECTED_PIP_CHECK_MISSING
        assert not unexpected, (
            f"`pip check` reported unexpected broken dependencies: {unexpected}. "
            f"Only {EXPECTED_PIP_CHECK_MISSING} are expected (intentionally "
            f"removed). Output:\n{result.stdout}\n{result.stderr}"
        )
