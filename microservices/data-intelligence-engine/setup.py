# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Include the separately built console in engine wheels."""

from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.errors import SetupError


class BuildWithConsole(build_py):
    def run(self):
        dist = Path(__file__).parent / "ui" / "dist"
        if not (dist / "index.html").is_file():
            raise SetupError(
                "Console is not built. Run npm ci && npm run build in "
                "data-intelligence-engine/ui before building the engine package."
            )
        super().run()
        shutil.copytree(dist, Path(self.build_lib) / "console_ui_dist", dirs_exist_ok=True)


setup(cmdclass={"build_py": BuildWithConsole})
