# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import shutil
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

    def test_compatible_files_link_when_incompatible_mode_sorts_first(self):
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            restricted = library_dir / "lib0.so"
            first = library_dir / "lib1.so"
            second = library_dir / "lib2.so"

            for library in (restricted, first, second):
                library.write_bytes(b"a" * (2 * 1024 * 1024))
            restricted.chmod(0o600)
            first.chmod(0o644)
            second.chmod(0o644)

            subprocess.run(["sh", str(SCRIPT), str(library_dir)], check=True)

            self.assertNotEqual(restricted.stat().st_ino, first.stat().st_ino)
            self.assertEqual(first.stat().st_ino, second.stat().st_ino)
            self.assertEqual(first.stat().st_mode & 0o777, 0o644)

    def test_compatible_files_link_when_owners_or_groups_differ(self):
        with tempfile.TemporaryDirectory() as directory:
            library_dir = Path(directory)
            libraries = [library_dir / f"lib{index}.so" for index in range(5)]
            for library in libraries:
                library.write_bytes(b"a" * (2 * 1024 * 1024))
                library.chmod(0o644)

            # Simulate different UID/GID values without requiring root privileges.
            bin_dir = library_dir / "bin"
            bin_dir.mkdir()
            real_stat = shutil.which("stat")
            self.assertIsNotNone(real_stat)
            stat_script = bin_dir / "stat"
            stat_script.write_text(
                "#!/bin/sh\n"
                'if [ "$1" = "-c" ] && [ "$2" = "%a:%u:%g" ]; then\n'
                '    case "$3" in\n'
                '        ./lib0.so) printf "644:100:10\\n" ;;\n'
                '        ./lib1.so|./lib2.so) printf "644:100:20\\n" ;;\n'
                '        ./lib3.so|./lib4.so) printf "644:200:10\\n" ;;\n'
                '        *) exit 1 ;;\n'
                '    esac\n'
                'else\n'
                f'    exec "{real_stat}" "$@"\n'
                'fi\n'
            )
            stat_script.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"

            subprocess.run(["sh", str(SCRIPT), str(library_dir)], check=True, env=env)

            self.assertEqual(libraries[1].stat().st_ino, libraries[2].stat().st_ino)
            self.assertEqual(libraries[3].stat().st_ino, libraries[4].stat().st_ino)
            self.assertNotEqual(libraries[0].stat().st_ino, libraries[1].stat().st_ino)
            self.assertNotEqual(libraries[0].stat().st_ino, libraries[3].stat().st_ino)
            self.assertNotEqual(libraries[1].stat().st_ino, libraries[3].stat().st_ino)
