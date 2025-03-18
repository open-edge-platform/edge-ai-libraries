#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import os
import cv2
import glob
import time
import argparse
import numpy as np
import logging

class Udf:

    def __init__(self, width, height):
        self.width = width
        self.height = height

    def process(self, frame, metadata):

        resized = cv2.resize(frame, (self.width, self.height),
                        interpolation = cv2.INTER_AREA)

        return False, resized, metadata
