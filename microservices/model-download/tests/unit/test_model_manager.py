# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import pytest

from src.core.model_manager import ModelManager


@pytest.mark.asyncio
async def test_process_conversion_keeps_explicit_converter_for_huggingface_source(tmp_path):
    registry = MagicMock()
    converter_plugin = MagicMock()
    converter_plugin.plugin_name = "openvino"
    converter_plugin.convert.return_value = {"success": True, "source": "openvino"}

    registry.get_plugin.return_value = converter_plugin
    registry.find_plugin_for_model.return_value = None

    manager = ModelManager(registry, default_dir=str(tmp_path))
    output_dir = tmp_path / "converted"
    job_id = manager.register_job(
        "convert",
        "meta-llama/Llama-3.2-1B",
        "openvino",
        str(output_dir),
        "openvino",
        "llm",
    )

    result = await manager.process_conversion(
        job_id=job_id,
        model_path="llm-converted",
        model_name="meta-llama/Llama-3.2-1B",
        hub="openvino",
        hf_token="test-token",
        output_dir=str(output_dir),
        converter="openvino",
        precision="int4",
        device="CPU",
        cache_size=4,
    )

    assert result["status"] == "completed"
    assert manager.get_job_status(job_id)["status"] == "completed"
    registry.get_plugin.assert_called_once_with("converter", "openvino")
    registry.find_plugin_for_model.assert_not_called()
    converter_plugin.convert.assert_called_once()


@pytest.mark.asyncio
async def test_process_conversion_auto_detects_converter_for_huggingface_source(tmp_path):
    registry = MagicMock()
    converter_plugin = MagicMock()
    converter_plugin.plugin_name = "openvino"
    converter_plugin.convert.return_value = {"success": True, "source": "openvino"}

    registry.find_plugin_for_model.return_value = converter_plugin

    manager = ModelManager(registry, default_dir=str(tmp_path))
    output_dir = tmp_path / "converted"
    job_id = manager.register_job(
        "convert",
        "sentence-transformers/all-MiniLM-L6-v2",
        "openvino",
        str(output_dir),
        None,
        "embeddings",
    )

    result = await manager.process_conversion(
        job_id=job_id,
        model_path="embedding-models",
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        hub="openvino",
        hf_token="test-token",
        output_dir=str(output_dir),
        converter=None,
        precision="int8",
        device="CPU",
    )

    assert result["status"] == "completed"
    registry.find_plugin_for_model.assert_called_once_with(
        "converter",
        hub="openvino",
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        is_ovms=True,
        precision="int8",
        device="CPU",
    )
