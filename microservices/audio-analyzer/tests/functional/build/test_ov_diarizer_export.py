# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""OpenVINO-backed (GPU/NPU) diarization exports pyannote with the legacy ONNX exporter.

torch>=2.9 defaults torch.onnx.export to the dynamo exporter, which fails on the
pyannote segmentation graph and aborted startup with models.diarization.device=GPU.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.tier1
def test_segmentation_export_uses_legacy_exporter():
    import components.asr.diarization.ov_pyannote_diarizer as ov_mod

    with patch.object(ov_mod.torch.onnx, "export") as export:
        ov_mod._export_to_onnx_bytes(
            MagicMock(), example_input=MagicMock(), input_name="waveform",
            output_name="scores", dynamic_axes=None,
        )
    assert export.call_args.kwargs["dynamo"] is False
