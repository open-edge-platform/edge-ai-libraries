# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from typing import ClassVar, Optional

import config

RUNTIME_OV_GENAI = "ov_genai"
RUNTIME_OV_LLAMAINDEX = "ov_llamaindex"
RUNTIME_OV_GME = "ov_gme"
RUNTIME_OV_CORE = "ov_core"
RUNTIME_OV_OPTIMUM = "ov_optimum"


class InferenceMeta:
    """Model metadata mixin; attributes are ClassVars so pydantic subclasses ignore them."""

    BACKEND: ClassVar[str] = config.LOCAL_OPENVINO
    RUNTIME: ClassVar[str] = ""
    SUPPORT_MULTIMODAL: ClassVar[Optional[bool]] = None

    def get_backend(self) -> str:
        return self.BACKEND

    def get_runtime(self) -> str:
        return self.RUNTIME

    def get_support_multimodal(self) -> Optional[bool]:
        return self.SUPPORT_MULTIMODAL
