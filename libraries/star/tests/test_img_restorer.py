# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import sys
from types import SimpleNamespace

from PIL import Image

from semantic_img_comp.utils import img_restorer



def test_enhance_image_passes_gpuid_when_supported(monkeypatch):
    calls = {}

    class _FakeRealesrgan:
        def __init__(self, *, model, gpuid):
            calls["model"] = model
            calls["gpuid"] = gpuid

        def process_pil(self, pil_img):
            return pil_img

    monkeypatch.setitem(sys.modules, "realesrgan_ncnn_py", SimpleNamespace(Realesrgan=_FakeRealesrgan))

    img = Image.new("RGB", (4, 4), color="white")
    out = img_restorer.enhance_image(img, gpuid=2, model=3)

    assert out is img
    assert calls == {"model": 3, "gpuid": 2}



def test_enhance_image_falls_back_when_gpuid_not_supported(monkeypatch):
    calls = {}

    class _FakeRealesrgan:
        def __init__(self, *, model, gpuid=None):
            if gpuid is not None:
                raise TypeError("gpuid not supported")
            calls["model"] = model

        def process_pil(self, pil_img):
            return pil_img

    monkeypatch.setitem(sys.modules, "realesrgan_ncnn_py", SimpleNamespace(Realesrgan=_FakeRealesrgan))

    img = Image.new("RGB", (4, 4), color="white")
    out = img_restorer.enhance_image(img, gpuid=1, model=4)

    assert out is img
    assert calls == {"model": 4}

