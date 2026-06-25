# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for ``vippet.images``.

The tests exercise the full upload pipeline (validation + extraction +
rename + sidecar) against real archives written to a per-test temporary
directory, so the assertions also cover the on-disk layout and the
``set.json`` schema. Where possible the tests avoid mocking cv2 so the
resolution check is verified end-to-end.
"""

import io
import json
import os
import shutil
import tarfile
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch

import cv2
import numpy as np

import images as images_mod
from images import (
    ARCHIVE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    ImageInfo,
    ImageSet,
    ImageUploadError,
    ImagesManager,
    _resolve_max_size_bytes,
    sanitise_trunk,
)


def _png_bytes(width: int = 16, height: int = 16, color: int = 200) -> bytes:
    """Return a valid PNG byte stream of the requested dimensions."""
    arr = np.full((height, width, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", arr)
    assert ok, "cv2.imencode failed in test fixture"
    return buf.tobytes()


def _jpg_bytes(width: int = 16, height: int = 16, color: int = 200) -> bytes:
    arr = np.full((height, width, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", arr)
    assert ok, "cv2.imencode failed in test fixture"
    return buf.tobytes()


def _bmp_bytes(width: int = 16, height: int = 16, color: int = 200) -> bytes:
    arr = np.full((height, width, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".bmp", arr)
    assert ok
    return buf.tobytes()


def _make_zip(entries: dict[str, bytes]) -> bytes:
    """Build a flat or nested zip from a {arcname: payload} mapping."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, payload in entries.items():
            zf.writestr(arcname, payload)
    return buf.getvalue()


def _make_tar(entries: dict[str, bytes], gz: bool = False) -> bytes:
    buf = io.BytesIO()
    mode = "w:gz" if gz else "w"
    with tarfile.open(fileobj=buf, mode=mode) as tf:
        for arcname, payload in entries.items():
            info = tarfile.TarInfo(name=arcname)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def _write_archive(tmpdir: str, name: str, content: bytes) -> str:
    path = os.path.join(tmpdir, name)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


class _BaseImagesTest(unittest.TestCase):
    """
    Base class that gives every test its own UPLOADED_IMAGES_DIR and
    resets the singleton so cross-test state does not leak.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="vippet-images-test-")
        self.uploads_dir = os.path.join(self.tmpdir, "uploads")
        os.makedirs(self.uploads_dir, exist_ok=True)

        # Reset the singleton so each test gets a fresh manager bound
        # to its own uploads directory.
        ImagesManager._instance = None

        self._patch = patch.object(images_mod, "UPLOADED_IMAGES_DIR", self.uploads_dir)
        self._patch.start()
        # Re-create root via the manager constructor.
        self.manager = ImagesManager()

    def tearDown(self) -> None:
        self._patch.stop()
        ImagesManager._instance = None
        shutil.rmtree(self.tmpdir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Helpers / pure functions.
# --------------------------------------------------------------------------- #


class TestSanitiseTrunk(unittest.TestCase):
    def test_keeps_alnum(self) -> None:
        self.assertEqual(sanitise_trunk("Cats_2024-01"), "cats_2024-01")

    def test_collapses_runs_of_invalid(self) -> None:
        self.assertEqual(sanitise_trunk("hello   world!!!"), "hello_world")

    def test_strips_edge_underscores(self) -> None:
        self.assertEqual(sanitise_trunk("___abc___"), "abc")

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(sanitise_trunk(""))

    def test_only_invalid_returns_none(self) -> None:
        self.assertIsNone(sanitise_trunk("!!!"))

    def test_dot_returns_none(self) -> None:
        self.assertIsNone(sanitise_trunk("."))


class TestDeriveTrunk(unittest.TestCase):
    def test_zip(self) -> None:
        self.assertEqual(ImagesManager.derive_trunk("dorota.zip"), "dorota")

    def test_tar_gz(self) -> None:
        self.assertEqual(ImagesManager.derive_trunk("Dataset.tar.gz"), "dataset")

    def test_tgz(self) -> None:
        self.assertEqual(ImagesManager.derive_trunk("ds.tgz"), "ds")

    def test_strips_path_components(self) -> None:
        # Defends against client-supplied paths.
        self.assertEqual(ImagesManager.derive_trunk("/etc/passwd/foo.zip"), "foo")

    def test_unsupported_extension(self) -> None:
        self.assertIsNone(ImagesManager.derive_trunk("foo.7z"))

    def test_no_extension(self) -> None:
        self.assertIsNone(ImagesManager.derive_trunk("foo"))

    def test_empty(self) -> None:
        self.assertIsNone(ImagesManager.derive_trunk(""))

    def test_sanitisation_collapses_to_empty(self) -> None:
        # ``!!!.zip`` strips to ``!!!`` then sanitises to empty.
        self.assertIsNone(ImagesManager.derive_trunk("!!!.zip"))


# --------------------------------------------------------------------------- #
# Singleton behaviour.
# --------------------------------------------------------------------------- #


class TestSingleton(_BaseImagesTest):
    def test_returns_same_instance(self) -> None:
        a = ImagesManager()
        b = ImagesManager()
        self.assertIs(a, b)

    def test_concurrent_construction_returns_same_instance(self) -> None:
        ImagesManager._instance = None
        results: list[ImagesManager] = []

        def worker() -> None:
            results.append(ImagesManager())

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        first = results[0]
        for inst in results[1:]:
            self.assertIs(inst, first)


# --------------------------------------------------------------------------- #
# Discovery / lookup.
# --------------------------------------------------------------------------- #


class TestDiscovery(_BaseImagesTest):
    def _make_set_dir(
        self,
        name: str,
        *,
        write_set_json: bool = True,
        image_count: int = 2,
        extension: str = "png",
    ) -> str:
        set_dir = os.path.join(self.uploads_dir, name)
        os.makedirs(set_dir, exist_ok=True)
        for i in range(1, image_count + 1):
            with open(os.path.join(set_dir, f"{name}_{i:03d}.{extension}"), "wb") as fh:
                fh.write(_png_bytes())
        if write_set_json:
            payload = {
                "name": name,
                "source_archive": f"{name}.zip",
                "image_count": image_count,
                "extension": extension,
                "width": 16,
                "height": 16,
                "uploaded_at": "2026-04-28T00:00:00Z",
            }
            with open(os.path.join(set_dir, "set.json"), "w") as fh:
                json.dump(payload, fh)
        return set_dir

    def test_get_all_image_sets_empty(self) -> None:
        self.assertEqual(self.manager.get_all_image_sets(), {})

    def test_get_all_image_sets_returns_only_sets_with_set_json(self) -> None:
        self._make_set_dir("alpha")
        self._make_set_dir("beta", write_set_json=False)
        result = self.manager.get_all_image_sets()
        self.assertIn("alpha", result)
        self.assertNotIn("beta", result)

    def test_get_all_image_sets_skips_staging_dirs(self) -> None:
        os.makedirs(os.path.join(self.uploads_dir, ".staging-foo"))
        self.assertEqual(self.manager.get_all_image_sets(), {})

    def test_image_set_exists(self) -> None:
        self._make_set_dir("alpha")
        self.assertTrue(self.manager.image_set_exists("alpha"))
        self.assertFalse(self.manager.image_set_exists("missing"))

    def test_image_set_exists_rejects_traversal(self) -> None:
        self.assertFalse(self.manager.image_set_exists("../etc"))
        self.assertFalse(self.manager.image_set_exists(""))
        self.assertFalse(self.manager.image_set_exists("."))
        self.assertFalse(self.manager.image_set_exists("a/b"))

    def test_get_image_set_returns_none_for_missing(self) -> None:
        self.assertIsNone(self.manager.get_image_set("nope"))

    def test_get_image_set_overrides_name_with_dir(self) -> None:
        # Persist a set.json whose ``name`` field disagrees with the
        # directory name; the directory wins.
        set_dir = self._make_set_dir("alpha")
        with open(os.path.join(set_dir, "set.json"), "r") as fh:
            data = json.load(fh)
        data["name"] = "tampered"
        with open(os.path.join(set_dir, "set.json"), "w") as fh:
            json.dump(data, fh)
        result = self.manager.get_image_set("alpha")
        assert result is not None
        self.assertEqual(result.name, "alpha")

    def test_get_image_set_handles_corrupted_set_json(self) -> None:
        set_dir = self._make_set_dir("alpha")
        with open(os.path.join(set_dir, "set.json"), "w") as fh:
            fh.write("{not json")
        self.assertIsNone(self.manager.get_image_set("alpha"))

    def test_get_image_set_handles_non_object_set_json(self) -> None:
        set_dir = self._make_set_dir("alpha")
        with open(os.path.join(set_dir, "set.json"), "w") as fh:
            json.dump([1, 2, 3], fh)
        self.assertIsNone(self.manager.get_image_set("alpha"))

    def test_get_images_in_set_excludes_set_json(self) -> None:
        self._make_set_dir("alpha", image_count=3)
        infos = self.manager.get_images_in_set("alpha")
        assert infos is not None
        names = [i.filename for i in infos]
        self.assertEqual(len(infos), 3)
        self.assertNotIn("set.json", names)
        # All entries share the canonical extension and metadata.
        for info in infos:
            self.assertEqual(info.extension, "png")
            self.assertEqual(info.width, 16)
            self.assertEqual(info.height, 16)
            self.assertGreater(info.size_bytes, 0)

    def test_get_images_in_set_returns_none_for_missing(self) -> None:
        self.assertIsNone(self.manager.get_images_in_set("nope"))

    def test_get_location_pattern(self) -> None:
        self._make_set_dir("dorota", image_count=40)
        pattern = self.manager.get_location_pattern("dorota")
        self.assertEqual(
            pattern,
            os.path.join(self.uploads_dir, "dorota", "dorota_%02d.png"),
        )

    def test_get_location_pattern_widths(self) -> None:
        self._make_set_dir("a", image_count=9)
        self._make_set_dir("b", image_count=10)
        self._make_set_dir("c", image_count=1000)
        pat_a = self.manager.get_location_pattern("a")
        pat_b = self.manager.get_location_pattern("b")
        pat_c = self.manager.get_location_pattern("c")
        assert pat_a is not None and pat_b is not None and pat_c is not None
        self.assertTrue(pat_a.endswith("a_%01d.png"))
        self.assertTrue(pat_b.endswith("b_%02d.png"))
        self.assertTrue(pat_c.endswith("c_%04d.png"))

    def test_get_location_pattern_missing(self) -> None:
        self.assertIsNone(self.manager.get_location_pattern("nope"))


# --------------------------------------------------------------------------- #
# Upload pipeline: register_uploaded_archive.
# --------------------------------------------------------------------------- #


class TestRegisterUploadedArchive(_BaseImagesTest):
    @staticmethod
    def _temp_name_for(original: str) -> str:
        """
        Pick a temp filename whose extension matches the original so
        ``_safe_extract`` dispatches to the right archive handler.
        """
        lower = original.lower()
        if lower.endswith(".zip"):
            return "incoming.zip"
        if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
            return "incoming.tar.gz"
        if lower.endswith(".tar"):
            return "incoming.tar"
        return "incoming.bin"

    def _register(self, archive_bytes: bytes, original_name: str) -> ImageSet:
        path = _write_archive(
            self.tmpdir, self._temp_name_for(original_name), archive_bytes
        )
        return self.manager.register_uploaded_archive(path, original_name)

    def _expect_error(
        self, archive_bytes: bytes, original_name: str, expected_kind: str
    ) -> ImageUploadError:
        path = _write_archive(
            self.tmpdir, self._temp_name_for(original_name), archive_bytes
        )
        with self.assertRaises(ImageUploadError) as cm:
            self.manager.register_uploaded_archive(path, original_name)
        self.assertEqual(cm.exception.kind, expected_kind)
        return cm.exception

    # ---- success ---------------------------------------------------------

    def test_zip_with_pngs_succeeds(self) -> None:
        entries = {
            "frame_b.png": _png_bytes(width=32, height=24),
            "frame_a.png": _png_bytes(width=32, height=24),
        }
        result = self._register(_make_zip(entries), "Cats Set.zip")

        self.assertEqual(result.name, "cats_set")
        self.assertEqual(result.source_archive, "Cats Set.zip")
        self.assertEqual(result.image_count, 2)
        self.assertEqual(result.extension, "png")
        self.assertEqual(result.width, 32)
        self.assertEqual(result.height, 24)
        self.assertTrue(result.uploaded_at.endswith("Z"))

        # On-disk layout matches the renamed pattern.
        set_dir = os.path.join(self.uploads_dir, "cats_set")
        files = sorted(os.listdir(set_dir))
        self.assertIn("set.json", files)
        # Width is len(str(2)) == 1.
        self.assertIn("cats_set_1.png", files)
        self.assertIn("cats_set_2.png", files)

        # set.json round-trips through ImageSet.from_dict.
        with open(os.path.join(set_dir, "set.json")) as fh:
            sidecar = json.load(fh)
        self.assertEqual(sidecar["image_count"], 2)
        self.assertEqual(sidecar["extension"], "png")

    def test_jpeg_normalised_to_jpg(self) -> None:
        entries = {
            "a.JPEG": _jpg_bytes(),
            "b.jpg": _jpg_bytes(),
            "c.jpeg": _jpg_bytes(),
        }
        result = self._register(_make_zip(entries), "mixed_case.zip")
        self.assertEqual(result.extension, "jpg")
        files = os.listdir(os.path.join(self.uploads_dir, "mixed_case"))
        for f in files:
            if f != "set.json":
                self.assertTrue(f.endswith(".jpg"))

    def test_tiff_normalised_to_tif(self) -> None:
        entries = {
            "a.tif": _png_bytes(),  # cv2 imencode for tif requires libtiff; reuse png bytes via avdec irrelevant
        }
        # Build real tiff bytes through cv2.imencode.
        arr = np.full((8, 8, 3), 100, dtype=np.uint8)
        ok, buf = cv2.imencode(".tif", arr)
        if not ok:
            self.skipTest("cv2 build lacks TIFF support")
        tif_payload = buf.tobytes()
        entries = {"a.tiff": tif_payload, "b.tif": tif_payload}
        result = self._register(_make_zip(entries), "tdata.zip")
        self.assertEqual(result.extension, "tif")

    def test_zip_with_tar_gz_archive(self) -> None:
        entries = {
            "img1.png": _png_bytes(),
            "img2.png": _png_bytes(),
        }
        result = self._register(_make_tar(entries, gz=True), "set.tar.gz")
        self.assertEqual(result.image_count, 2)
        self.assertEqual(result.extension, "png")

    def test_renamed_files_zero_padded_by_count(self) -> None:
        entries = {f"img{i:02d}.png": _png_bytes() for i in range(1, 13)}
        result = self._register(_make_zip(entries), "twelve.zip")
        files = sorted(
            f
            for f in os.listdir(os.path.join(self.uploads_dir, "twelve"))
            if f != "set.json"
        )
        # 12 files -> width = 2.
        self.assertEqual(files[0], "twelve_01.png")
        self.assertEqual(files[-1], "twelve_12.png")
        self.assertEqual(result.image_count, 12)

    # ---- error paths -----------------------------------------------------

    def test_invalid_archive_name(self) -> None:
        # Trunk sanitises to empty -> invalid_archive_name.
        self._expect_error(
            _make_zip({"a.png": _png_bytes()}), "!!!.zip", "invalid_archive_name"
        )

    def test_unsupported_archive_format_handled_at_filename_level(self) -> None:
        # Manager-level entry point: derive_trunk returns None.
        self._expect_error(b"junk", "foo.7z", "invalid_archive_name")

    def test_archive_corrupted(self) -> None:
        self._expect_error(b"not a real zip", "x.zip", "archive_corrupted")

    def test_archive_contains_subdirectories(self) -> None:
        entries = {
            "sub/a.png": _png_bytes(),
            "sub/b.png": _png_bytes(),
        }
        self._expect_error(
            _make_zip(entries), "nested.zip", "archive_contains_subdirectories"
        )

    def test_archive_contains_no_images(self) -> None:
        # Empty zip archive (no entries at all): extraction succeeds,
        # leaving the staging dir empty, which trips the no-images guard.
        empty_zip = _make_zip({})
        self._expect_error(empty_zip, "empty.zip", "archive_contains_no_images")

    def test_archive_disallowed_image_extension(self) -> None:
        entries = {"a.txt": b"hi"}
        self._expect_error(
            _make_zip(entries), "txt.zip", "archive_disallowed_image_extension"
        )

    def test_archive_mixed_image_extensions(self) -> None:
        entries = {
            "a.png": _png_bytes(),
            "b.jpg": _jpg_bytes(),
        }
        exc = self._expect_error(
            _make_zip(entries), "mixed.zip", "archive_mixed_image_extensions"
        )
        # Sorted families exposed for the API layer.
        assert isinstance(exc.found, list)
        self.assertEqual(sorted(exc.found), ["jpg", "png"])

    def test_archive_mixed_image_resolutions(self) -> None:
        entries = {
            "a.png": _png_bytes(width=16, height=16),
            "b.png": _png_bytes(width=32, height=16),
        }
        self._expect_error(
            _make_zip(entries), "mixed.zip", "archive_mixed_image_resolutions"
        )

    def test_image_set_already_exists_pre_check(self) -> None:
        os.makedirs(os.path.join(self.uploads_dir, "dup"), exist_ok=False)
        entries = {"a.png": _png_bytes()}
        self._expect_error(_make_zip(entries), "dup.zip", "image_set_already_exists")

    def test_archive_uncompressed_too_large(self) -> None:
        # Force the cap down to 100 bytes total uncompressed.
        with patch.dict(os.environ, {"UPLOAD_MAX_SIZE_BYTES": "10"}):
            # 10 * 10 = 100 bytes uncompressed allowed.
            entries = {
                "a.png": _png_bytes(),  # PNGs are ~70-90 bytes for 16x16 solid.
                "b.png": _png_bytes(),
            }
            self._expect_error(
                _make_zip(entries), "big.zip", "archive_uncompressed_too_large"
            )

    def test_unsafe_archive_path_via_traversal(self) -> None:
        # Build a zip with a path-traversal entry by hand.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../escape.png", _png_bytes())
        # Either subdirectories or unsafe_archive_path is acceptable -
        # the slash in the name trips ``_check_member_layout`` first.
        with self.assertRaises(ImageUploadError) as cm:
            path = _write_archive(self.tmpdir, "evil.zip", buf.getvalue())
            self.manager.register_uploaded_archive(path, "evil.zip")
        self.assertIn(
            cm.exception.kind,
            ("archive_contains_subdirectories", "unsafe_archive_path"),
        )

    def test_tar_with_symlink_rejected(self) -> None:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            info = tarfile.TarInfo("link.png")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tf.addfile(info)
        path = _write_archive(self.tmpdir, "evil.tar", buf.getvalue())
        with self.assertRaises(ImageUploadError) as cm:
            self.manager.register_uploaded_archive(path, "evil.tar")
        self.assertEqual(cm.exception.kind, "unsafe_archive_path")

    # ---- staging cleanup -------------------------------------------------

    def test_failure_cleans_up_staging(self) -> None:
        entries = {"a.txt": b"nope"}
        with self.assertRaises(ImageUploadError):
            self._register(_make_zip(entries), "fail.zip")
        # No leftover .staging-* directories.
        leftovers = [
            e for e in os.listdir(self.uploads_dir) if e.startswith(".staging-")
        ]
        self.assertEqual(leftovers, [])

    def test_success_cleans_up_staging(self) -> None:
        entries = {"a.png": _png_bytes(), "b.png": _png_bytes()}
        self._register(_make_zip(entries), "ok.zip")
        leftovers = [
            e for e in os.listdir(self.uploads_dir) if e.startswith(".staging-")
        ]
        self.assertEqual(leftovers, [])

    # ---- integration with discovery -------------------------------------

    def test_uploaded_set_is_discoverable(self) -> None:
        entries = {"a.png": _png_bytes(), "b.png": _png_bytes()}
        self._register(_make_zip(entries), "discover.zip")
        sets = self.manager.get_all_image_sets()
        self.assertIn("discover", sets)
        self.assertEqual(sets["discover"].image_count, 2)

        pattern = self.manager.get_location_pattern("discover")
        assert pattern is not None
        self.assertTrue(pattern.endswith("discover_%01d.png"))


class TestImageSetSchema(unittest.TestCase):
    def test_archive_extensions_constant(self) -> None:
        self.assertEqual(set(ARCHIVE_EXTENSIONS), {"zip", "tar", "tar.gz", "tgz"})

    def test_image_extensions_constant(self) -> None:
        # webp removed; tiff and jpeg accepted as aliases.
        self.assertEqual(
            set(IMAGE_EXTENSIONS),
            {"jpg", "jpeg", "png", "bmp", "tif", "tiff"},
        )

    def test_image_set_round_trip(self) -> None:
        original = ImageSet(
            name="x",
            source_archive="x.zip",
            image_count=3,
            extension="png",
            width=10,
            height=20,
            uploaded_at="2026-01-01T00:00:00Z",
        )
        revived = ImageSet.from_dict(original.to_dict())
        self.assertEqual(revived, original)


# --------------------------------------------------------------------------- #
# Module-level helpers and small data classes.
# --------------------------------------------------------------------------- #


class TestResolveMaxSizeBytes(unittest.TestCase):
    """Cover every branch of ``images._resolve_max_size_bytes``."""

    def test_default_when_env_missing(self) -> None:
        # Drop the env var to force the default path.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("UPLOAD_MAX_SIZE_BYTES", None)
            self.assertEqual(_resolve_max_size_bytes(), 2 * 1024 * 1024 * 1024)

    def test_default_when_env_blank(self) -> None:
        with patch.dict(os.environ, {"UPLOAD_MAX_SIZE_BYTES": "   "}):
            self.assertEqual(_resolve_max_size_bytes(), 2 * 1024 * 1024 * 1024)

    def test_explicit_integer(self) -> None:
        with patch.dict(os.environ, {"UPLOAD_MAX_SIZE_BYTES": "12345"}):
            self.assertEqual(_resolve_max_size_bytes(), 12345)

    def test_invalid_falls_back_to_default_and_warns(self) -> None:
        with patch.dict(os.environ, {"UPLOAD_MAX_SIZE_BYTES": "not-a-number"}):
            with self.assertLogs("images", level="WARNING") as cm:
                self.assertEqual(_resolve_max_size_bytes(), 2 * 1024 * 1024 * 1024)
        self.assertTrue(any("Invalid integer" in m for m in cm.output))


class TestImageInfoToDict(unittest.TestCase):
    """``ImageInfo.to_dict`` is a tiny helper but it crosses the API
    boundary - keep it covered explicitly."""

    def test_to_dict_round_trip(self) -> None:
        info = ImageInfo(
            filename="alpha_01.png",
            extension="png",
            size_bytes=42,
            width=640,
            height=480,
        )
        self.assertEqual(
            info.to_dict(),
            {
                "filename": "alpha_01.png",
                "extension": "png",
                "size_bytes": 42,
                "width": 640,
                "height": 480,
            },
        )


# --------------------------------------------------------------------------- #
# Bootstrap and discovery edge cases.
# --------------------------------------------------------------------------- #


class TestEnsureRootDir(unittest.TestCase):
    """``ImagesManager.ensure_root_dir`` translates OSError to RuntimeError."""

    def test_os_error_becomes_runtime_error(self) -> None:
        # Force os.makedirs to fail so the wrapping RuntimeError fires.
        with patch("images.os.makedirs", side_effect=OSError("denied")):
            with self.assertRaises(RuntimeError) as ctx:
                ImagesManager.ensure_root_dir()
        self.assertIn("Failed to create image set root", str(ctx.exception))


class TestDiscoveryEdgeCases(_BaseImagesTest):
    """Coverage for the small branches in ``get_all_image_sets`` and
    ``get_image_set``."""

    def test_get_all_image_sets_returns_empty_when_root_missing(self) -> None:
        """If the uploads root does not exist at all, return ``{}``."""
        # Remove the uploads dir created by _BaseImagesTest.setUp.
        shutil.rmtree(self.uploads_dir)
        self.assertFalse(os.path.isdir(self.uploads_dir))
        self.assertEqual(self.manager.get_all_image_sets(), {})

    def test_get_all_image_sets_skips_plain_files(self) -> None:
        """Stray files at the root are ignored - we only care about dirs."""
        with open(os.path.join(self.uploads_dir, "stray.txt"), "w") as fh:
            fh.write("noise")
        self.assertEqual(self.manager.get_all_image_sets(), {})

    def test_get_image_set_rejects_unsafe_name(self) -> None:
        """A name with a separator never touches disk - returns ``None``."""
        # Path-traversal attempts must be rejected by ``_is_safe_set_name``.
        self.assertIsNone(self.manager.get_image_set("../etc"))
        self.assertIsNone(self.manager.get_image_set("a/b"))
        self.assertIsNone(self.manager.get_image_set(""))


class TestGetImageSetPath(_BaseImagesTest):
    """Direct coverage for ``ImagesManager.get_image_set_path``."""

    def _make_set(self, name: str = "alpha") -> str:
        set_dir = os.path.join(self.uploads_dir, name)
        os.makedirs(set_dir)
        payload = {
            "name": name,
            "source_archive": f"{name}.zip",
            "image_count": 1,
            "extension": "png",
            "width": 16,
            "height": 16,
            "uploaded_at": "2026-04-28T00:00:00Z",
        }
        with open(os.path.join(set_dir, "set.json"), "w") as fh:
            json.dump(payload, fh)
        return set_dir

    def test_returns_absolute_path_for_existing_set(self) -> None:
        set_dir = self._make_set("alpha")
        self.assertEqual(self.manager.get_image_set_path("alpha"), set_dir)

    def test_returns_none_for_missing_set(self) -> None:
        self.assertIsNone(self.manager.get_image_set_path("missing"))

    def test_returns_none_for_unsafe_name(self) -> None:
        # ``image_set_exists`` short-circuits unsafe names to False.
        self.assertIsNone(self.manager.get_image_set_path("a/b"))


class TestGetImagesInSetEdgeCases(_BaseImagesTest):
    """Cover the ``not isfile`` and ``OSError on stat`` branches."""

    def _make_set(self, name: str = "alpha", *, image_count: int = 1) -> str:
        set_dir = os.path.join(self.uploads_dir, name)
        os.makedirs(set_dir, exist_ok=True)
        for i in range(1, image_count + 1):
            with open(os.path.join(set_dir, f"{name}_{i:03d}.png"), "wb") as fh:
                fh.write(_png_bytes())
        payload = {
            "name": name,
            "source_archive": f"{name}.zip",
            "image_count": image_count,
            "extension": "png",
            "width": 16,
            "height": 16,
            "uploaded_at": "2026-04-28T00:00:00Z",
        }
        with open(os.path.join(set_dir, "set.json"), "w") as fh:
            json.dump(payload, fh)
        return set_dir

    def test_skips_subdirectories_inside_set(self) -> None:
        """A stray subdirectory inside the set dir is ignored."""
        set_dir = self._make_set("alpha", image_count=1)
        os.makedirs(os.path.join(set_dir, "stray_subdir"))
        infos = self.manager.get_images_in_set("alpha")
        assert infos is not None
        # Only the single PNG must be returned; the subdir is filtered.
        self.assertEqual([i.filename for i in infos], ["alpha_001.png"])

    def test_stat_failure_recorded_as_zero_size(self) -> None:
        """If ``os.path.getsize`` fails, the entry is still listed
        with ``size_bytes=0`` and a warning is logged."""
        self._make_set("alpha", image_count=1)
        with patch("images.os.path.getsize", side_effect=OSError("perm denied")):
            with self.assertLogs("images", level="WARNING") as cm:
                infos = self.manager.get_images_in_set("alpha")
        assert infos is not None
        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].size_bytes, 0)
        self.assertTrue(any("Failed to stat image" in m for m in cm.output))


# --------------------------------------------------------------------------- #
# Multi-format archive happy-paths.
# --------------------------------------------------------------------------- #


class TestArchiveFormatsHappyPath(_BaseImagesTest):
    """Cover the three archive formats with the three canonical image extensions."""

    def _register(self, name: str, archive_bytes: bytes) -> ImageSet:
        path = _write_archive(self.tmpdir, "incoming.bin", archive_bytes)
        # Match the manager's expected temp name to the archive type so
        # ``_safe_extract`` dispatches to the right handler.
        return self.manager.register_uploaded_archive(path, name)

    def test_zip_multiple_jpgs(self) -> None:
        """Valid .zip with multiple jpgs → 201 with images renamed to
        ``<trunk>_<NNNN>.jpg`` in alphabetical order."""
        entries = {
            f"img{i:02d}.jpg": _jpg_bytes(width=32, height=24) for i in range(1, 6)
        }
        # Use a .zip temp name so the dispatcher routes to the zip path.
        archive_path = _write_archive(self.tmpdir, "in.zip", _make_zip(entries))
        result = self.manager.register_uploaded_archive(archive_path, "Photos_2026.zip")

        self.assertEqual(result.image_count, 5)
        self.assertEqual(result.extension, "jpg")
        files = sorted(
            f
            for f in os.listdir(os.path.join(self.uploads_dir, "photos_2026"))
            if f != "set.json"
        )
        # 5 files -> width 1.
        self.assertEqual(files, [f"photos_2026_{i}.jpg" for i in range(1, 6)])

    def test_tar_multiple_pngs(self) -> None:
        """Valid uncompressed .tar with multiple pngs → 201."""
        entries = {
            "frame_01.png": _png_bytes(width=64, height=48),
            "frame_02.png": _png_bytes(width=64, height=48),
            "frame_03.png": _png_bytes(width=64, height=48),
        }
        archive_path = _write_archive(
            self.tmpdir, "in.tar", _make_tar(entries, gz=False)
        )
        result = self.manager.register_uploaded_archive(archive_path, "frames.tar")

        self.assertEqual(result.image_count, 3)
        self.assertEqual(result.extension, "png")
        self.assertEqual(result.width, 64)
        self.assertEqual(result.height, 48)
        files = sorted(
            f
            for f in os.listdir(os.path.join(self.uploads_dir, "frames"))
            if f != "set.json"
        )
        self.assertEqual(files, ["frames_1.png", "frames_2.png", "frames_3.png"])

    def test_tar_gz_multiple_bmps(self) -> None:
        """Valid .tar.gz with multiple bmps → 201."""
        entries = {
            "a.bmp": _bmp_bytes(width=8, height=8),
            "b.bmp": _bmp_bytes(width=8, height=8),
        }
        archive_path = _write_archive(
            self.tmpdir, "in.tar.gz", _make_tar(entries, gz=True)
        )
        result = self.manager.register_uploaded_archive(archive_path, "bitmaps.tar.gz")

        self.assertEqual(result.image_count, 2)
        self.assertEqual(result.extension, "bmp")
        files = sorted(
            f
            for f in os.listdir(os.path.join(self.uploads_dir, "bitmaps"))
            if f != "set.json"
        )
        self.assertEqual(files, ["bitmaps_1.bmp", "bitmaps_2.bmp"])


# --------------------------------------------------------------------------- #
# Internal validation/extraction helpers - cover the small branches.
# --------------------------------------------------------------------------- #


class TestSafeExtractZipBranches(_BaseImagesTest):
    """Branches inside ``_safe_extract_zip`` and ``_check_member_layout``
    that the higher-level tests do not always exercise."""

    def test_explicit_directory_entry_is_rejected(self) -> None:
        """A zip with a bare ``foo/`` directory entry must be rejected
        even when no files live in it."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            # Trailing slash in the arcname creates a directory entry.
            zf.writestr("nested_dir/", b"")
        archive_path = _write_archive(self.tmpdir, "evil.zip", buf.getvalue())
        with self.assertRaises(ImageUploadError) as cm:
            self.manager.register_uploaded_archive(archive_path, "evil.zip")
        self.assertEqual(cm.exception.kind, "archive_contains_subdirectories")


class TestSafeExtractTarBranches(_BaseImagesTest):
    """Branches inside ``_safe_extract_tar`` that need explicit cases."""

    def test_explicit_directory_entry_is_rejected(self) -> None:
        """A tar with a nested directory entry must be rejected.

        ``tarfile`` strips the trailing ``/`` from top-level directory
        members, so to actually trip the path-separator guard inside
        ``_check_member_layout`` we need a nested name (``parent/sub``)
        where the slash survives normalisation.
        """
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            info = tarfile.TarInfo("parent/sub")
            info.type = tarfile.DIRTYPE
            tf.addfile(info)
        archive_path = _write_archive(self.tmpdir, "evil.tar", buf.getvalue())
        with self.assertRaises(ImageUploadError) as cm:
            self.manager.register_uploaded_archive(archive_path, "evil.tar")
        self.assertEqual(cm.exception.kind, "archive_contains_subdirectories")

    def test_uncompressed_too_large_for_tar(self) -> None:
        """The TAR branch enforces the zip-bomb cap just like ZIP."""
        # 1 byte * 10 = 10 bytes total uncompressed allowed.
        with patch.dict(os.environ, {"UPLOAD_MAX_SIZE_BYTES": "1"}):
            entries = {
                "a.png": _png_bytes(),  # PNGs are well over 10 bytes.
            }
            archive_path = _write_archive(
                self.tmpdir, "in.tar", _make_tar(entries, gz=False)
            )
            with self.assertRaises(ImageUploadError) as cm:
                self.manager.register_uploaded_archive(archive_path, "big.tar")
        self.assertEqual(cm.exception.kind, "archive_uncompressed_too_large")


class TestEnforceSingleResolutionDecodeFailure(_BaseImagesTest):
    """If cv2 returns None for one of the extracted files, the manager
    must raise ``archive_corrupted``."""

    def test_undecodable_image_triggers_corrupted(self) -> None:
        # A file with a valid .png extension but garbage payload makes
        # ``cv2.imread`` return None.
        entries = {"a.png": b"not really a png"}
        archive_path = _write_archive(self.tmpdir, "in.zip", _make_zip(entries))
        with self.assertRaises(ImageUploadError) as cm:
            self.manager.register_uploaded_archive(archive_path, "bad.zip")
        self.assertEqual(cm.exception.kind, "archive_corrupted")


# --------------------------------------------------------------------------- #
# Commit phase - race conditions and chmod fallbacks.
# --------------------------------------------------------------------------- #


class TestCommitStaging(_BaseImagesTest):
    """Cover the small branches inside ``_commit_staging``."""

    def test_concurrent_commit_race_raises_already_exists(self) -> None:
        """If another upload reserved the target name between the
        pre-check and the commit, ``_commit_staging`` translates the
        ``FileExistsError`` into ``image_set_already_exists``."""
        # Force ``os.makedirs`` to raise FileExistsError when the
        # commit tries to reserve the target.
        entries = {"a.png": _png_bytes(), "b.png": _png_bytes()}
        archive_path = _write_archive(self.tmpdir, "in.zip", _make_zip(entries))

        real_makedirs = images_mod.os.makedirs
        calls: list[str] = []

        def fake_makedirs(path, *args, **kwargs):
            # ``ensure_root_dir`` calls makedirs with exist_ok=True for
            # the uploads root - let that one through. Trip only the
            # reservation call (exist_ok=False) inside _commit_staging.
            calls.append(path)
            if kwargs.get("exist_ok") is False:
                raise FileExistsError(path)
            return real_makedirs(path, *args, **kwargs)

        with patch("images.os.makedirs", side_effect=fake_makedirs):
            with self.assertRaises(ImageUploadError) as cm:
                self.manager.register_uploaded_archive(archive_path, "race.zip")
        self.assertEqual(cm.exception.kind, "image_set_already_exists")
        # Staging dir was cleaned up.
        leftovers = [
            e for e in os.listdir(self.uploads_dir) if e.startswith(".staging-")
        ]
        self.assertEqual(leftovers, [])

    def test_chmod_failure_on_target_is_logged_and_non_fatal(self) -> None:
        """An OSError from the final ``os.chmod`` is logged but does
        not break the upload."""
        entries = {"a.png": _png_bytes(), "b.png": _png_bytes()}
        archive_path = _write_archive(self.tmpdir, "in.zip", _make_zip(entries))

        real_chmod = images_mod.os.chmod
        target_dir = os.path.join(self.uploads_dir, "chmodfail")

        def picky_chmod(path, mode):
            # Only fail for the final target chmod (0o755). Earlier
            # chmod calls (set.json -> 0o644, root -> 0o755) must keep
            # working so we don't crash other code paths.
            if path == target_dir and mode == 0o755:
                raise OSError("denied")
            return real_chmod(path, mode)

        with patch("images.os.chmod", side_effect=picky_chmod):
            with self.assertLogs("images", level="WARNING") as cm:
                result = self.manager.register_uploaded_archive(
                    archive_path, "chmodfail.zip"
                )
        # Upload succeeded.
        self.assertEqual(result.name, "chmodfail")
        # And the warning about chmod was logged.
        self.assertTrue(
            any("Could not chmod" in m and "chmodfail" in m for m in cm.output),
            cm.output,
        )


class TestWriteSetJsonChmodFailure(_BaseImagesTest):
    """The ``_write_set_json`` chmod fallback."""

    def test_chmod_set_json_failure_is_warning_only(self) -> None:
        entries = {"a.png": _png_bytes(), "b.png": _png_bytes()}
        archive_path = _write_archive(self.tmpdir, "in.zip", _make_zip(entries))

        real_chmod = images_mod.os.chmod

        def picky_chmod(path, mode):
            # Fail only on the set.json chmod (mode 0o644 on a file
            # whose name ends with ``set.json``).
            if os.path.basename(path) == "set.json" and mode == 0o644:
                raise OSError("denied")
            return real_chmod(path, mode)

        with patch("images.os.chmod", side_effect=picky_chmod):
            with self.assertLogs("images", level="WARNING") as cm:
                result = self.manager.register_uploaded_archive(
                    archive_path, "setjson.zip"
                )

        self.assertEqual(result.name, "setjson")
        self.assertTrue(
            any("Could not chmod" in m and "set.json" in m for m in cm.output),
            cm.output,
        )


# --------------------------------------------------------------------------- #
# register_uploaded_archive - unexpected exception path cleans up staging.
# --------------------------------------------------------------------------- #


class TestRegisterUnexpectedException(_BaseImagesTest):
    """The generic ``except Exception`` in ``register_uploaded_archive``
    re-raises but still cleans up the staging directory."""

    def test_unexpected_exception_cleans_up_staging_and_propagates(
        self,
    ) -> None:
        entries = {"a.png": _png_bytes(), "b.png": _png_bytes()}
        archive_path = _write_archive(self.tmpdir, "in.zip", _make_zip(entries))

        # Patch a step deep in the pipeline to raise a non-ImageUploadError.
        with patch.object(
            ImagesManager,
            "_rename_images",
            side_effect=RuntimeError("disk explode"),
        ):
            with self.assertRaises(RuntimeError):
                self.manager.register_uploaded_archive(archive_path, "boom.zip")

        # No leftover .staging-* dirs.
        leftovers = [
            e for e in os.listdir(self.uploads_dir) if e.startswith(".staging-")
        ]
        self.assertEqual(leftovers, [])
        # And the final target was never created.
        self.assertFalse(os.path.isdir(os.path.join(self.uploads_dir, "boom")))


if __name__ == "__main__":
    unittest.main()
