# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/strip_wheel_libraries.sh"


class StripWheelLibrariesTests(unittest.TestCase):
    def test_strips_only_large_non_debian_shared_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            libraries = root / "libraries"
            binaries = root / "bin"
            libraries.mkdir()
            binaries.mkdir()

            wheel_library = libraries / "libwheel.so.1"
            driver_library = libraries / "libdriver.so.1"
            python_library = libraries / "libpython3.14.so.1"
            static_library = libraries / "libwheel.a"
            for library in (wheel_library, driver_library, python_library, static_library):
                library.write_bytes(b"x" * (2 * 1024 * 1024))
            (libraries / "libsmall.so").write_bytes(b"x")
            (libraries / "libsymlink.so").symlink_to(wheel_library)

            (binaries / "dpkg-query").write_text(
                '#!/bin/sh\n[ "$1" = "-S" ] && [ "$2" = "$DEBIAN_FILE" ]\n'
            )
            (binaries / "strip").write_text(
                '#!/bin/sh\nprintf "%s\\n" "$*" >> "$STRIP_LOG"\n'
            )
            for binary in binaries.iterdir():
                binary.chmod(0o755)

            log = root / "stripped.log"
            env = os.environ.copy()
            env.update({
                "PATH": f"{binaries}:{env['PATH']}",
                "DEBIAN_FILE": str(driver_library),
                "STRIP_LOG": str(log),
            })
            subprocess.run(["sh", str(SCRIPT), str(libraries)], check=True, env=env)

            self.assertEqual(log.read_text().splitlines(), [f"--strip-unneeded {wheel_library}"])