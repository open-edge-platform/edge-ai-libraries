# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0


class DataPrepException(Exception):
    """Custom exception for VDMS-DataPrep application."""

    def __init__(self, msg: str, status_code: int):
        self.message = msg
        self.status_code = status_code
        super().__init__(self.message)
