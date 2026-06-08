# SPDX-License-Identifier: Apache-2.0
"""Functional tests for the image-set endpoints.

Covers every endpoint exposed by ``api.routes.images``:

- ``GET  /images``                       (listing of registered sets)
- ``GET  /images/check-image-set-exists`` (existence probe)
- ``GET  /images/{name}``                (per-set image listing)
- ``POST /images/upload``                (archive upload + validation)

The happy-path test uploads a real zip archive whose images are a frame
decoded from a publicly available mp4 (downloaded once per session by
the shared ``sample_video_bytes`` fixture). The negative tests drive
the upload endpoint through the structured ``ImageUploadError`` error
kinds it can return.

All tests are marked ``full`` so they only run as part of
``make test-full``.
"""

import io
import logging
import zipfile

import pytest
import requests

from helpers.api_helpers import (
    check_image_set_exists,
    fetch_image_sets,
    list_images_in_set,
    upload_image_archive,
)

logger = logging.getLogger(__name__)


def _archive_name(run_id: str, base: str, suffix: str) -> str:
    """Per-run unique archive filename so re-runs do not collide on
    the shared volume."""
    return f"upload_{run_id}_{base}.{suffix}"


def _trunk_for(run_id: str, base: str) -> str:
    """Compute the sanitised trunk the manager will derive from the
    uploaded archive filename. Mirrors ``ImagesManager.derive_trunk``."""
    return f"upload_{run_id}_{base}".lower()


# --------------------------------------------------------------------------- #
# Happy path: upload + listing + per-set view + existence probe.
# --------------------------------------------------------------------------- #


@pytest.mark.full
def test_upload_valid_zip_with_pngs_succeeds(
    http_client: requests.Session,
    make_zip_archive,
    upload_run_id: str,
) -> None:
    """A valid zip of PNGs returns 201 and the resulting set appears
    in the listing endpoints with the correct metadata."""
    archive_bytes, _ = make_zip_archive(ext="png", count=4)
    archive_filename = _archive_name(upload_run_id, "png_zip", "zip")
    trunk = _trunk_for(upload_run_id, "png_zip")

    response = upload_image_archive(
        http_client,
        archive_filename,
        archive_bytes,
        content_type="application/zip",
    )
    assert response.status_code == 201, (
        f"Expected 201 from valid upload, got {response.status_code}: {response.text}"
    )

    body = response.json()
    assert body["name"] == trunk
    assert body["source_archive"] == archive_filename
    assert body["image_count"] == 4
    assert body["extension"] == "png"
    assert body["width"] > 0
    assert body["height"] > 0
    assert body["uploaded_at"].endswith("Z")

    # GET /images returns the new set.
    sets = fetch_image_sets(http_client)
    assert any(s["name"] == trunk for s in sets), (
        f"Uploaded image set '{trunk}' not found in /images listing"
    )

    # GET /images/check-image-set-exists confirms it.
    probe = check_image_set_exists(http_client, trunk)
    assert probe == {"exists": True, "name": trunk}

    # GET /images/{name} lists every renamed image with the expected
    # ``<trunk>_<NN>.png`` shape; width matches len(str(count)) == 1.
    listing = list_images_in_set(http_client, trunk)
    assert listing.status_code == 200, listing.text
    images = listing.json()
    assert isinstance(images, list)
    assert len(images) == 4
    for index, image in enumerate(images, start=1):
        assert image["filename"] == f"{trunk}_{index}.png"
        assert image["extension"] == "png"
        assert image["width"] == body["width"]
        assert image["height"] == body["height"]
        assert image["size_bytes"] > 0


@pytest.mark.full
def test_upload_valid_tar_with_pngs_succeeds(
    http_client: requests.Session,
    make_tar_archive,
    upload_run_id: str,
) -> None:
    """A valid uncompressed ``.tar`` of PNGs is accepted."""
    archive_bytes, _ = make_tar_archive(ext="png", count=3, gz=False)
    archive_filename = _archive_name(upload_run_id, "png_tar", "tar")
    trunk = _trunk_for(upload_run_id, "png_tar")

    response = upload_image_archive(
        http_client,
        archive_filename,
        archive_bytes,
        content_type="application/x-tar",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == trunk
    assert body["extension"] == "png"
    assert body["image_count"] == 3


@pytest.mark.full
def test_upload_valid_tar_gz_with_bmps_succeeds(
    http_client: requests.Session,
    make_tar_archive,
    upload_run_id: str,
) -> None:
    """A valid ``.tar.gz`` of BMPs is accepted."""
    archive_bytes, _ = make_tar_archive(ext="bmp", count=2, gz=True)
    archive_filename = _archive_name(upload_run_id, "bmp_targz", "tar.gz")
    trunk = _trunk_for(upload_run_id, "bmp_targz")

    response = upload_image_archive(
        http_client,
        archive_filename,
        archive_bytes,
        content_type="application/gzip",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == trunk
    assert body["extension"] == "bmp"
    assert body["image_count"] == 2


@pytest.mark.full
def test_upload_valid_zip_with_jpgs_succeeds(
    http_client: requests.Session,
    make_zip_archive,
    upload_run_id: str,
) -> None:
    """A valid zip of JPGs is accepted with the canonical ``jpg`` extension."""
    archive_bytes, _ = make_zip_archive(ext="jpg", count=5)
    archive_filename = _archive_name(upload_run_id, "jpg_zip", "zip")
    trunk = _trunk_for(upload_run_id, "jpg_zip")

    response = upload_image_archive(
        http_client,
        archive_filename,
        archive_bytes,
        content_type="application/zip",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == trunk
    assert body["extension"] == "jpg"
    assert body["image_count"] == 5


# --------------------------------------------------------------------------- #
# /check-image-set-exists - falsy branch.
# --------------------------------------------------------------------------- #


@pytest.mark.full
def test_check_image_set_exists_returns_false_for_missing(
    http_client: requests.Session,
    upload_run_id: str,
) -> None:
    """A name that was never uploaded reports ``exists=false``."""
    name = f"no_such_set_{upload_run_id}"
    probe = check_image_set_exists(http_client, name)
    assert probe == {"exists": False, "name": name}


# --------------------------------------------------------------------------- #
# /images/{name} - 404 branch.
# --------------------------------------------------------------------------- #


@pytest.mark.full
def test_list_images_in_missing_set_returns_404(
    http_client: requests.Session,
    upload_run_id: str,
) -> None:
    """``GET /images/{name}`` returns 404 for a name that does not exist."""
    response = list_images_in_set(http_client, f"definitely_missing_{upload_run_id}")
    assert response.status_code == 404, response.text
    body = response.json()
    assert "not found" in body["message"].lower()


# --------------------------------------------------------------------------- #
# Upload validation rejections - one per structured error kind.
# --------------------------------------------------------------------------- #


@pytest.mark.full
def test_upload_unsupported_archive_format_rejected(
    http_client: requests.Session, upload_run_id: str
) -> None:
    """A filename without a supported archive extension is rejected
    with ``unsupported_archive_format``."""
    response = upload_image_archive(
        http_client,
        _archive_name(upload_run_id, "bad", "7z"),
        b"junk",
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "unsupported_archive_format"
    assert isinstance(body["allowed"], list)


@pytest.mark.full
def test_upload_invalid_archive_name_rejected(
    http_client: requests.Session,
) -> None:
    """A filename whose trunk sanitises to empty fails with
    ``invalid_archive_name``."""
    # The archive extension is valid but the trunk (``"!!!"``) sanitises
    # to an empty string. The ``upload_run_id`` is not used here on
    # purpose: prepending the run id would make the trunk non-empty.
    response = upload_image_archive(http_client, "!!!.zip", b"junk")
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "invalid_archive_name"


@pytest.mark.full
def test_upload_corrupted_archive_rejected(
    http_client: requests.Session, upload_run_id: str
) -> None:
    """Bytes that do not parse as a zip return ``archive_corrupted``."""
    response = upload_image_archive(
        http_client,
        _archive_name(upload_run_id, "corrupted", "zip"),
        b"not a real zip file",
        content_type="application/zip",
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "archive_corrupted"


@pytest.mark.full
def test_upload_archive_with_subdirectories_rejected(
    http_client: requests.Session,
    sample_frame_bgr,
    upload_run_id: str,
) -> None:
    """An archive with a nested directory layout is rejected."""
    # Build a zip with images under a sub-folder so the flat-layout
    # check inside the manager trips.
    import cv2  # local import - tests run inside venv that pulls cv2 in.

    ok, encoded = cv2.imencode(".png", sample_frame_bgr)
    assert ok
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("sub/a.png", encoded.tobytes())
        zf.writestr("sub/b.png", encoded.tobytes())

    response = upload_image_archive(
        http_client,
        _archive_name(upload_run_id, "nested", "zip"),
        buf.getvalue(),
        content_type="application/zip",
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "archive_contains_subdirectories"


@pytest.mark.full
def test_upload_archive_with_no_images_rejected(
    http_client: requests.Session,
    upload_run_id: str,
) -> None:
    """An empty zip is rejected with ``archive_contains_no_images``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        # Intentionally write zero entries so the manager extracts an
        # empty staging directory.
        pass

    response = upload_image_archive(
        http_client,
        _archive_name(upload_run_id, "empty", "zip"),
        buf.getvalue(),
        content_type="application/zip",
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "archive_contains_no_images"


@pytest.mark.full
def test_upload_archive_with_disallowed_extension_rejected(
    http_client: requests.Session,
    upload_run_id: str,
) -> None:
    """A zip containing a non-image file is rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", b"hello")

    response = upload_image_archive(
        http_client,
        _archive_name(upload_run_id, "txt", "zip"),
        buf.getvalue(),
        content_type="application/zip",
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "archive_disallowed_image_extension"


@pytest.mark.full
def test_upload_archive_with_mixed_extensions_rejected(
    http_client: requests.Session,
    sample_frame_bgr,
    upload_run_id: str,
) -> None:
    """A zip mixing png + jpg entries is rejected."""
    import cv2

    ok_png, png = cv2.imencode(".png", sample_frame_bgr)
    ok_jpg, jpg = cv2.imencode(".jpg", sample_frame_bgr)
    assert ok_png and ok_jpg
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.png", png.tobytes())
        zf.writestr("b.jpg", jpg.tobytes())

    response = upload_image_archive(
        http_client,
        _archive_name(upload_run_id, "mixed", "zip"),
        buf.getvalue(),
        content_type="application/zip",
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "archive_mixed_image_extensions"


@pytest.mark.full
def test_upload_archive_with_mixed_resolutions_rejected(
    http_client: requests.Session,
    sample_frame_bgr,
    upload_run_id: str,
) -> None:
    """A zip mixing two resolutions of the same extension is rejected."""
    import cv2

    # Build a second frame at half the resolution.
    small = cv2.resize(
        sample_frame_bgr,
        (
            max(1, sample_frame_bgr.shape[1] // 2),
            max(1, sample_frame_bgr.shape[0] // 2),
        ),
    )
    ok_a, frame_a = cv2.imencode(".png", sample_frame_bgr)
    ok_b, frame_b = cv2.imencode(".png", small)
    assert ok_a and ok_b
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.png", frame_a.tobytes())
        zf.writestr("b.png", frame_b.tobytes())

    response = upload_image_archive(
        http_client,
        _archive_name(upload_run_id, "resmix", "zip"),
        buf.getvalue(),
        content_type="application/zip",
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "archive_mixed_image_resolutions"


@pytest.mark.full
def test_upload_duplicate_image_set_rejected(
    http_client: requests.Session,
    make_zip_archive,
    upload_run_id: str,
) -> None:
    """Uploading the same archive name twice fails with
    ``image_set_already_exists``."""
    archive_bytes, _ = make_zip_archive(ext="png", count=2)
    archive_filename = _archive_name(upload_run_id, "dup", "zip")

    first = upload_image_archive(
        http_client,
        archive_filename,
        archive_bytes,
        content_type="application/zip",
    )
    assert first.status_code == 201, first.text

    second = upload_image_archive(
        http_client,
        archive_filename,
        archive_bytes,
        content_type="application/zip",
    )
    assert second.status_code == 422, second.text
    body = second.json()
    assert body["error"] == "image_set_already_exists"
