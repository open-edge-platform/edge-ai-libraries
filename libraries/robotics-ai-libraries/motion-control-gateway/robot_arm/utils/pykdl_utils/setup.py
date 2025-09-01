# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Intel Corporation
from setuptools import find_packages, setup

package_name = 'pykdl_utils'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='eci',
    maintainer_email='yu.yan@intel.com',
    description='Python utils to use PyKDL for robotic kinematics',
    license='BSD',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            "pose_converter = pykdl_utils.pose_converter:main",
            "kdl_parser = pykdl_utils.kdl_parser:main",
            "kdl_kinematics = pykdl_utils.kdl_kinematics:main",
        ],
    },
)
