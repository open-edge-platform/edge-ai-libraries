# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Setuptools entry for thin binary wheels (native ``_native*.so`` as package-data)."""

from setuptools import setup

try:
    from setuptools.command.bdist_wheel import bdist_wheel
except ImportError:  # older setuptools / wheel-only layouts
    from wheel.bdist_wheel import bdist_wheel


class BinaryWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        # Ensure platform tag (not py3-none-any) even though we ship .so via package-data.
        self.root_is_pure = False


setup(cmdclass={"bdist_wheel": BinaryWheel})
