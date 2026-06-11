"""Shared fixtures for VIPPET functional tests."""

import io
import logging
import tarfile
import urllib.request
import uuid
import zipfile
from collections.abc import Generator
from typing import Any

import cv2
import numpy as np
import pytest
import requests
import yaml

from helpers.config import DEFAULT_RECORDINGS_YAML, PROJECT_ROOT, SUPPORTED_MODELS_YAML

logger = logging.getLogger(__name__)

# Session-wide accumulator: (HTTP_METHOD, full_url_without_query_string)
_recorded_api_calls: set[tuple[str, str]] = set()


# Pipelines with externally pre-downloaded models (path template uses lowercase
# device ``family``, rooted at PROJECT_ROOT); variants skipped if path missing.
_EXTERNAL_MODEL_PATH_TEMPLATES: dict[str, str] = {
    "Video Summarization VLM": (
        "shared/models/output/openvino_models/{family}/int4/google/gemma-3-4b-it"
    ),
}


# Pipelines with no video encoder/muxer branch; ``output_mode=file`` returns
# an empty ``video_output_paths`` list, so the file-output test is skipped.
_NO_FILE_VIDEO_OUTPUT_PIPELINES: frozenset[str] = frozenset(
    {
        "Video Summarization VLM",
    }
)


# API call recording – used by test_z_api_coverage.py to verify that all
# API endpoints have been exercised at least once during the full test run.
class _RecordingSession(requests.Session):
    """Thin requests.Session subclass that records every outgoing request."""

    def request(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, method: str | bytes, url: str | bytes, **kwargs: Any
    ) -> requests.Response:
        clean_url = str(url).split("?")[0].split("#")[0]
        _recorded_api_calls.add((str(method).upper(), clean_url))
        return super().request(str(method), url, **kwargs)


@pytest.fixture(scope="session")
def http_client() -> Generator[requests.Session, None, None]:
    """Reusable HTTP session shared across all functional tests."""
    session = _RecordingSession()
    session.headers.update({"Accept": "application/json"})
    yield session
    session.close()


@pytest.fixture(scope="session")
def recorded_api_calls() -> set[tuple[str, str]]:
    """Return the set of (METHOD, URL) pairs recorded during this test session.

    Populated automatically by the shared ``http_client`` fixture.  Consumed by
    ``test_z_api_coverage.py`` to check that every API route has been called at
    least once.
    """
    return _recorded_api_calls


@pytest.fixture(scope="session")
def supported_models_config() -> list[dict[str, Any]]:
    """Load supported_models.yaml as the source-of-truth for model tests."""
    with SUPPORTED_MODELS_YAML.open() as f:
        data = yaml.safe_load(f)
    assert isinstance(data, list), "supported_models.yaml must be a list"
    return data


@pytest.fixture(scope="session")
def default_recordings_config() -> list[dict[str, Any]]:
    """Load default_recordings.yaml as the source-of-truth for video tests."""
    with DEFAULT_RECORDINGS_YAML.open() as f:
        data = yaml.safe_load(f)
    assert isinstance(data, list), "default_recordings.yaml must be a list"
    return data


@pytest.fixture(autouse=True)
def _skip_when_external_model_missing(request: pytest.FixtureRequest) -> None:
    """Skip parametrized pipeline cases whose pre-downloaded model is absent.

    Applies to pipelines listed in ``_EXTERNAL_MODEL_PATH_TEMPLATES`` (e.g. the
    VLM Video Summarization pipeline, which hard-codes its model path instead
    of going through ``supported_models.yaml``).
    """
    case = getattr(request.node, "callspec", None)
    case_value = case.params.get("case") if case is not None else None
    pipeline_name = getattr(case_value, "pipeline_name", None)
    if pipeline_name not in _EXTERNAL_MODEL_PATH_TEMPLATES:
        return

    family = getattr(case_value, "device_family", "").lower()
    model_path = PROJECT_ROOT / _EXTERNAL_MODEL_PATH_TEMPLATES[pipeline_name].format(
        family=family
    )
    if not model_path.is_dir():
        pytest.skip(
            f"Pre-downloaded model for pipeline '{pipeline_name}' "
            f"({getattr(case_value, 'device_family', '')}) not found at {model_path}. "
            "Download the model before running this test."
        )


@pytest.fixture(autouse=True)
def _skip_file_output_for_pipelines_without_video_sink(
    request: pytest.FixtureRequest,
) -> None:
    """Skip ``output_mode=file`` tests for pipelines listed in
    ``_NO_FILE_VIDEO_OUTPUT_PIPELINES`` (no encoder branch -> empty
    ``video_output_paths``).
    """
    if "file_output" not in request.node.name:
        return
    case = getattr(request.node, "callspec", None)
    case_value = case.params.get("case") if case is not None else None
    pipeline_name = getattr(case_value, "pipeline_name", None)
    if pipeline_name in _NO_FILE_VIDEO_OUTPUT_PIPELINES:
        pytest.skip(
            f"Pipeline '{pipeline_name}' has no video encoder branch; "
            "file-output mode produces no recorded video files."
        )


# --------------------------------------------------------------------------- #
# Upload fixtures - real video + image archives produced from a small,
# publicly available mp4. Generated lazily, cached for the whole pytest
# session so multiple tests share the same on-disk artifacts.
# --------------------------------------------------------------------------- #

# Public sample used as the source for the upload fixtures. It is already
# listed in ``shared/videos/default_recordings.yaml`` so it is a well-known,
# stable URL.
_SAMPLE_VIDEO_URL: str = (
    "https://storage.openvinotoolkit.org/repositories/openvino_notebooks/"
    "data/data/video/people.mp4"
)


@pytest.fixture(scope="session")
def sample_video_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    """Download a small public mp4 once per session and return its bytes.

    The result is cached under the pytest session ``tmp_path`` so a re-run
    of the suite within the same session does not re-download. Network
    failures are surfaced as ``pytest.skip`` because the upload tests are
    not meaningful without a real video payload.
    """
    cache_dir = tmp_path_factory.mktemp("vippet-upload-fixtures")
    cached = cache_dir / "people.mp4"
    if cached.is_file():
        return cached.read_bytes()

    logger.info("Downloading sample video from %s", _SAMPLE_VIDEO_URL)
    try:
        request = urllib.request.Request(
            _SAMPLE_VIDEO_URL,
            headers={"User-Agent": "Mozilla/5.0 vippet-tests"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            if response.status != 200:
                pytest.skip(f"Could not download sample video: HTTP {response.status}")
            payload = response.read()
    except Exception as exc:  # noqa: BLE001 - propagate as skip below.
        pytest.skip(f"Could not download sample video: {exc}")

    cached.write_bytes(payload)
    logger.info(
        "Cached sample video at %s (%.2f MB)", cached, len(payload) / (1024 * 1024)
    )
    return payload


@pytest.fixture(scope="session")
def sample_frame_bgr(
    sample_video_bytes: bytes, tmp_path_factory: pytest.TempPathFactory
) -> "np.ndarray[Any, Any]":
    """Decode one frame (around frame 10) from the sample mp4 with OpenCV.

    Returned as a BGR ``numpy`` array suitable for ``cv2.imencode``. The
    intermediate file is dropped once decoding succeeds.
    """
    cache_dir = tmp_path_factory.mktemp("vippet-sample-frame")
    mp4_path = cache_dir / "people.mp4"
    mp4_path.write_bytes(sample_video_bytes)

    cap = cv2.VideoCapture(str(mp4_path))
    if not cap.isOpened():
        cap.release()
        pytest.skip("OpenCV cannot open the downloaded sample video")
    ok: bool = False
    frame: Any = None
    try:
        # Seek a few frames in so we never grab a black opening frame.
        for _ in range(10):
            ok, frame = cap.read()
            if not ok:
                break
        if not ok or frame is None:
            pytest.skip("Sample video has fewer than 10 decodable frames")
    finally:
        cap.release()
    return frame


def _encode_frame(frame: "np.ndarray[Any, Any]", suffix: str) -> bytes:
    """Encode a BGR frame to bytes using ``cv2.imencode``. ``suffix`` must
    start with a dot, e.g. ``.png``."""
    ok, buf = cv2.imencode(suffix, frame)
    if not ok:
        pytest.skip(f"cv2.imencode failed for suffix={suffix!r}")
    return buf.tobytes()


def _build_zip(entries: dict[str, bytes]) -> bytes:
    """Pack ``{arcname: payload}`` into a flat zip archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, payload in entries.items():
            zf.writestr(arcname, payload)
    return buf.getvalue()


def _build_tar(entries: dict[str, bytes], *, gz: bool = False) -> bytes:
    """Pack ``{arcname: payload}`` into a flat tar (optionally gzipped)."""
    buf = io.BytesIO()
    mode = "w:gz" if gz else "w"
    with tarfile.open(fileobj=buf, mode=mode) as tf:
        for arcname, payload in entries.items():
            info = tarfile.TarInfo(name=arcname)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


@pytest.fixture(scope="session")
def upload_run_id() -> str:
    """Return a short unique identifier for the current test run.

    Used by upload tests to namespace their artifacts (image set names,
    video filenames) so a re-run inside the same shared volume does not
    collide with leftovers from a previous run. A separate CI job is
    expected to wipe the shared volume between runs - the tests
    themselves do not delete what they upload because the API does not
    expose a DELETE endpoint for either resource.
    """
    return uuid.uuid4().hex[:8]


@pytest.fixture
def make_zip_archive(sample_frame_bgr: "np.ndarray[Any, Any]"):
    """Factory returning ``(bytes, archive_filename)`` for a zip archive.

    The caller controls the image extension (``"png"``/``"jpg"``/``"bmp"``)
    and the number of frames. Every frame is the same decoded sample so
    the resolution check inside ``ImagesManager`` always passes.
    """

    def _make(
        *,
        ext: str = "png",
        count: int = 3,
        archive_name: str | None = None,
    ) -> tuple[bytes, str]:
        encoded = _encode_frame(sample_frame_bgr, f".{ext}")
        # Pad the index so alphabetical sort matches numeric order.
        entries = {f"img_{i:04d}.{ext}": encoded for i in range(1, count + 1)}
        return _build_zip(entries), archive_name or f"set_{ext}_{count}.zip"

    return _make


@pytest.fixture
def make_tar_archive(sample_frame_bgr: "np.ndarray[Any, Any]"):
    """Factory returning ``(bytes, archive_filename)`` for a tar archive.

    ``gz=True`` produces a ``.tar.gz`` archive instead of an uncompressed
    ``.tar`` one. Same single-frame trick as ``make_zip_archive``.
    """

    def _make(
        *,
        ext: str = "png",
        count: int = 3,
        gz: bool = False,
        archive_name: str | None = None,
    ) -> tuple[bytes, str]:
        encoded = _encode_frame(sample_frame_bgr, f".{ext}")
        entries = {f"img_{i:04d}.{ext}": encoded for i in range(1, count + 1)}
        payload = _build_tar(entries, gz=gz)
        suffix = "tar.gz" if gz else "tar"
        return payload, archive_name or f"set_{ext}_{count}.{suffix}"

    return _make


# --------------------------------------------------------------------------- #
# Uploaded-model fixtures.
#
# The functional test suite assumes the underlying source models
# (``face-detection-retail-0004`` and ``age-gender-recognition-retail-0013``)
# are present on disk under ``shared/models/output/omz/.../FP16/``. The
# download-side test (``test_models_download.py``) is responsible for
# ensuring that, but - to keep these fixtures usable in isolation - we
# skip whenever the FP16 artefacts are absent rather than fail.
#
# The upload itself is session-scoped: the API does not expose a DELETE
# for models, so we deliberately leak the uploaded copies into the
# shared volume (CI is expected to wipe the volume between runs). The
# unique ``upload_run_id`` keeps re-runs from colliding with stale
# entries left over from previous sessions.
# --------------------------------------------------------------------------- #


_UPLOAD_MODEL_SOURCES: dict[str, dict[str, str]] = {
    "face-detection-retail-0004": {
        "category": "detection",
        "fp16_dir": "shared/models/output/omz/face-detection-retail-0004/FP16",
    },
    "age-gender-recognition-retail-0013": {
        "category": "classification",
        "fp16_dir": "shared/models/output/omz/age-gender-recognition-retail-0013/FP16",
    },
}


def _build_model_zip(fp16_dir) -> bytes:
    """Pack ``model.xml`` + ``model.bin`` into a flat zip.

    The ``model-download`` microservice expects a flat archive
    containing the OpenVINO IR pair. We deliberately do not include
    a model-proc JSON: uploaded models never carry one (that is the
    invariant ``graph.py`` and ``ModelManager`` rely on).
    """
    xml_files = sorted(fp16_dir.glob("*.xml"))
    bin_files = sorted(fp16_dir.glob("*.bin"))
    assert xml_files and bin_files, f"FP16 directory {fp16_dir} missing xml/bin pair"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(xml_files[0].name, xml_files[0].read_bytes())
        zf.writestr(bin_files[0].name, bin_files[0].read_bytes())
    return buf.getvalue()


@pytest.fixture(scope="session")
def uploaded_model_names(
    http_client: requests.Session, upload_run_id: str
) -> dict[str, str]:
    """Upload custom copies of the two reference OMZ models.

    Returns a mapping ``{source_model_name: uploaded_model_name}``. The
    uploaded names carry the session ``upload_run_id`` so concurrent or
    repeated runs do not collide.

    Skips the entire test module if either FP16 source is missing on
    disk - the upload tests only make sense when the donor models are
    physically present.

    .. note::
        These uploads are deliberately **not** cleaned up at the end of
        the test session: the files under
        ``shared/models/output/custom_uploaded_models/`` are created by
        the ``model-download`` microservice and the test runner does
        not have permission to delete them from the host. A dedicated
        DELETE endpoint / janitor task is tracked separately.
    """
    # Imported here to keep the helpers/api_helpers import cost out of
    # the always-loaded conftest header.
    from helpers.api_helpers import upload_model_file

    uploaded: dict[str, str] = {}
    for source_name, info in _UPLOAD_MODEL_SOURCES.items():
        fp16_dir = PROJECT_ROOT / info["fp16_dir"]
        if not fp16_dir.is_dir():
            pytest.skip(
                f"FP16 source directory {fp16_dir} not found - upload tests "
                "require the donor OMZ models to be installed on disk."
            )
        payload = _build_model_zip(fp16_dir)
        uploaded_name = f"{source_name}-uploaded-{upload_run_id}"
        response = upload_model_file(
            http_client,
            model_name=uploaded_name,
            category=info["category"],
            payload=payload,
        )
        assert response.status_code == 201, (
            f"Upload of {uploaded_name} failed: {response.status_code}: {response.text}"
        )
        uploaded[source_name] = uploaded_name
        logger.info(
            "Uploaded model %s as %s (category=%s)",
            source_name,
            uploaded_name,
            info["category"],
        )
    return uploaded
