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
    ImageSet,
    ImageUploadError,
    ImagesManager,
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


if __name__ == "__main__":
    unittest.main()
