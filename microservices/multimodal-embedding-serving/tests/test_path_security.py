# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path

from src.utils.path_security import (
    resolve_manifest_artifact_reference,
    resolve_video_artifact_reference,
    validate_manifest_artifact_reference,
    validate_video_artifact_reference,
)


class TestPathSecurity(unittest.TestCase):
    def test_validate_video_artifact_reference_accepts_safe_filenames(self):
        self.assertEqual(
            validate_video_artifact_reference("base64DecodedVideo_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
            "base64DecodedVideo_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )
        self.assertEqual(
            validate_video_artifact_reference("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa_clip.mp4"),
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa_clip.mp4",
        )

    def test_validate_video_artifact_reference_rejects_unsafe_paths(self):
        with self.assertRaises(ValueError):
            validate_video_artifact_reference("../escape.mp4")
        with self.assertRaises(ValueError):
            validate_video_artifact_reference("/tmp/escape.mp4")
        with self.assertRaises(ValueError):
            validate_video_artifact_reference("nested/escape.mp4")
        with self.assertRaises(ValueError):
            validate_video_artifact_reference("video.exe")

    def test_validate_manifest_artifact_reference_requires_json(self):
        self.assertEqual(
            validate_manifest_artifact_reference("frames_manifest.json"),
            "frames_manifest.json",
        )
        with self.assertRaises(ValueError):
            validate_manifest_artifact_reference("frames_manifest.txt")
        with self.assertRaises(ValueError):
            validate_manifest_artifact_reference("../frames_manifest.json")

    def test_resolve_references_stay_under_allowed_root(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            manifest_path = resolve_manifest_artifact_reference(
                "video_frames.json", allowed_root=root
            )
            video_path = resolve_video_artifact_reference(
                "sample_clip.mp4", allowed_root=root
            )
            self.assertEqual(manifest_path, str(root / "video_frames.json"))
            self.assertEqual(video_path, str(root / "sample_clip.mp4"))


if __name__ == "__main__":
    unittest.main()
