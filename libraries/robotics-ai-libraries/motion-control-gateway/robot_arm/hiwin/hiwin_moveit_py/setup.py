# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
from setuptools import setup
import subprocess, os, platform
from glob import glob

package_name = "hiwin_moveit_py"

setup(
    name=package_name,
    version="0.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
        (os.path.join("share", package_name, "launch"), glob("launch/rviz/*.rviz")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    author="Peter David Fagan",
    author_email="peterdavidfagan@gmail.com",
    maintainer="Peter David Fagan",
    maintainer_email="peterdavidfagan@gmail.com",
    description="package description",
    license="license",
    entry_points={
        "console_scripts": [
            "hiwin_motion_planning = hiwin_moveit_py.hiwin_motion_planning:main",
        ],
    },
)
