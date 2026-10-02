# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/deduplicate_native_libraries.sh"


class DeduplicateNativeLibrariesTests(unittest.TestCase):
    def test_identical_shared_libraries_are_hard_linked(self):
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            original = library_dir / "libexample.so"
            duplicate = library_dir / "libexample.so.1"
            different = library_dir / "libdifferent.so"
            small = library_dir / "libsmall.so"
            different_permissions = library_dir / "libother.so"

            original.write_bytes(b"a" * (2 * 1024 * 1024))
            duplicate.write_bytes(original.read_bytes())
            different.write_bytes(b"b" * (2 * 1024 * 1024))
            small.write_bytes(b"short")
            different_permissions.write_bytes(original.read_bytes())
            different_permissions.chmod(0o600)

            subprocess.run(["sh", str(SCRIPT), str(library_dir)], check=True)

            self.assertEqual(original.stat().st_ino, duplicate.stat().st_ino)
            self.assertEqual(original.read_bytes(), duplicate.read_bytes())
            self.assertNotEqual(different.stat().st_ino, original.stat().st_ino)
            self.assertEqual(small.read_bytes(), b"short")
            self.assertNotEqual(different_permissions.stat().st_ino, original.stat().st_ino)
            self.assertEqual(different_permissions.stat().st_mode & 0o777, 0o600)

            # Already linked libraries must remain safe to process again.
            subprocess.run(["sh", str(SCRIPT), str(library_dir)], check=True)
            self.assertEqual(original.stat().st_ino, duplicate.stat().st_ino)