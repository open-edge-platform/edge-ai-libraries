# Example: Writing Tests for a Plugin

## Scenario

Write a complete unit test suite for the `ModelScopePlugin` from the
[new-plugin.md](./new-plugin.md) example.

---

## `tests/unit/test_modelscope_plugin.py`

```python
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from src.plugins.modelscope_plugin import ModelScopePlugin


class TestModelScopePlugin:
    """Test suite for ModelScopePlugin."""

    @pytest.fixture
    def plugin(self):
        return ModelScopePlugin()

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    # -----------------------------------------------------------------------
    # Plugin contract tests
    # -----------------------------------------------------------------------

    def test_plugin_name(self, plugin):
        assert plugin.plugin_name == "modelscope"

    def test_plugin_type(self, plugin):
        assert plugin.plugin_type == "downloader"

    # -----------------------------------------------------------------------
    # can_handle tests — always parametrize for full coverage
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("hub,expected", [
        ("modelscope", True),
        ("ModelScope", True),   # case-insensitive
        ("MODELSCOPE", True),
        ("huggingface", False),
        ("ollama", False),
        ("openvino", False),
        ("", False),
    ])
    def test_can_handle_hub(self, plugin, hub, expected):
        assert plugin.can_handle("any/model", hub) == expected

    @pytest.mark.parametrize("model_name", [
        "damo/nlp_structbert_backbone_base_std",
        "iic/cv_resnet50_image-classification_imagenet",
        "simple-model",
    ])
    def test_can_handle_model_names(self, plugin, model_name):
        """Any model name is accepted when hub matches."""
        assert plugin.can_handle(model_name, "modelscope") is True

    # -----------------------------------------------------------------------
    # download() — happy path
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    @patch('src.plugins.modelscope_plugin.os.getenv')
    @patch('src.plugins.modelscope_plugin.ModelScopePlugin.download')
    async def test_download_success(self, mock_download, mock_getenv, plugin, temp_dir):
        """Test that download() returns the expected structure."""
        expected_result = {
            "model_name": "damo/nlp_bert",
            "source": "modelscope",
            "download_path": f"{temp_dir}/modelscope/",
            "success": True,
        }
        mock_download.return_value = expected_result

        result = await plugin.download(
            model_name="damo/nlp_bert",
            output_dir=temp_dir
        )

        assert result["success"] is True
        assert result["source"] == "modelscope"
        assert result["model_name"] == "damo/nlp_bert"
        assert "modelscope" in result["download_path"]

    @pytest.mark.asyncio
    async def test_download_creates_hub_directory(self, plugin, temp_dir):
        """Verify the hub_dir is created under output_dir."""
        with patch('src.plugins.modelscope_plugin.snapshot_download') as mock_dl:
            mock_dl.return_value = os.path.join(temp_dir, "modelscope", "damo_nlp_bert")

            await plugin.download(
                model_name="damo/nlp_bert",
                output_dir=temp_dir
            )

            hub_dir = os.path.join(temp_dir, "modelscope")
            assert os.path.isdir(hub_dir)

    # -----------------------------------------------------------------------
    # download() — revision / token handling
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_download_with_revision(self, plugin, temp_dir):
        with patch('src.plugins.modelscope_plugin.snapshot_download') as mock_dl:
            mock_dl.return_value = temp_dir

            await plugin.download(
                model_name="damo/nlp_bert",
                output_dir=temp_dir,
                revision="v1.0.0"
            )

            call_kwargs = mock_dl.call_args[1]
            assert call_kwargs["revision"] == "v1.0.0"

    @pytest.mark.asyncio
    async def test_download_uses_env_token(self, plugin, temp_dir):
        with patch('src.plugins.modelscope_plugin.snapshot_download') as mock_dl, \
             patch.dict(os.environ, {"MODELSCOPE_TOKEN": "env-token"}):
            mock_dl.return_value = temp_dir

            await plugin.download(
                model_name="damo/nlp_bert",
                output_dir=temp_dir
            )

            call_kwargs = mock_dl.call_args[1]
            assert call_kwargs["token"] == "env-token"

    # -----------------------------------------------------------------------
    # download() — error paths
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_download_sdk_failure(self, plugin, temp_dir):
        with patch('src.plugins.modelscope_plugin.snapshot_download') as mock_dl:
            mock_dl.side_effect = RuntimeError("ModelScope API error")

            with pytest.raises(RuntimeError, match="ModelScope API error"):
                await plugin.download(
                    model_name="damo/nlp_bert",
                    output_dir=temp_dir
                )

    @pytest.mark.asyncio
    async def test_download_invalid_model_name(self, plugin, temp_dir):
        with patch('src.plugins.modelscope_plugin.snapshot_download') as mock_dl:
            mock_dl.side_effect = ValueError("Model not found: invalid-model")

            with pytest.raises(ValueError):
                await plugin.download(
                    model_name="invalid-model",
                    output_dir=temp_dir
                )
```

---

## Key Patterns to Follow

### 1. Import path for patches

Always patch at the **usage location**, not the definition:
```python
# WRONG — patches the original module
@patch('modelscope.snapshot_download')

# RIGHT — patches where the plugin uses it
@patch('src.plugins.modelscope_plugin.snapshot_download')
```

### 2. Async tests need `@pytest.mark.asyncio`

```python
@pytest.mark.asyncio
async def test_something(plugin, temp_dir):
    result = await plugin.download(...)
```

### 3. Check `pyproject.toml` for `asyncio_mode`

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### 4. Don't test implementation — test behavior

Test that:
- The right SDK function was called with the right arguments
- The return dict has the correct shape
- Error conditions raise the expected exceptions

Don't test:
- Internal variables
- Log messages (fragile)
- File system layout beyond what the plugin promises

---

## Running the Tests

```bash
cd microservices/model-download

# Install test dependencies
pip install -e ".[dev]"

# Run only the new plugin tests
pytest tests/unit/test_modelscope_plugin.py -v

# Run with coverage
pytest tests/unit/test_modelscope_plugin.py -v --cov=src.plugins.modelscope_plugin
```
