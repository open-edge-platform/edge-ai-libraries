# Testing Patterns Reference

Unit test conventions for the Model Download microservice.

---

## Table of Contents

1. [Test Structure](#test-structure)
2. [Fixtures](#fixtures)
3. [Testing Plugin Properties](#testing-plugin-properties)
4. [Mocking subprocess (Ollama, Ultralytics, HLS)](#mocking-subprocess)
5. [Mocking HuggingFace Downloads](#mocking-huggingface-downloads)
6. [Async Plugin Tests](#async-plugin-tests)
7. [Parametrize for can_handle](#parametrize-for-can_handle)
8. [Testing Error Paths](#testing-error-paths)
9. [Test File Template](#test-file-template)

---

## Test Structure

```
tests/
├── __init__.py
├── conftest.py              ← shared fixtures (temp dirs, mock env vars)
└── unit/
    ├── test_huggingface_plugin.py
    ├── test_ollama_plugin.py
    ├── test_ultralytics_plugin.py
    ├── test_openvino_plugin.py
    ├── test_geti_plugin.py
    ├── test_hls_plugin.py
    └── test_pipeline_zoo_models_plugin.py
```

Run tests with:
```bash
pytest tests/ -v
# or with coverage
pytest tests/ -v --cov=src --cov-report=term-missing
```

---

## Fixtures

### Standard fixtures (define per test file or in `conftest.py`):

```python
import pytest
import tempfile

@pytest.fixture
def plugin():
    """Plugin instance for testing."""
    return MyHubPlugin()

@pytest.fixture
def temp_dir():
    """Temporary directory that cleans up after each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir
```

### Env var fixtures:

```python
@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set required env vars for the test session."""
    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setenv("GETI_HOST", "https://geti.test")
    monkeypatch.setenv("GETI_TOKEN", "test-geti-token")
    monkeypatch.setenv("GETI_WORKSPACE_ID", "test-workspace")
```

---

## Testing Plugin Properties

Always verify the contract properties before testing behavior:

```python
def test_plugin_properties(plugin):
    assert plugin.plugin_name == "myhub"       # exact lowercase name
    assert plugin.plugin_type == "downloader"  # or "converter"
```

---

## Mocking subprocess

The Ollama plugin uses `subprocess.Popen` and `subprocess.run`. The critical detail is
**patching at the import path** — where the name is used, not where it is defined:

```python
from unittest.mock import patch, MagicMock

@patch('src.plugins.ollama_plugin.subprocess.Popen')
@patch('src.plugins.ollama_plugin.subprocess.run')
@patch('src.plugins.ollama_plugin.time.sleep')
def test_ollama_download_success(mock_sleep, mock_run, mock_popen, plugin, temp_dir):
    # Setup
    mock_process = MagicMock()
    mock_popen.return_value = mock_process

    # Exercise
    result = plugin.download(model_name="llama2", output_dir=temp_dir, revision="7b")

    # Verify subprocess calls
    mock_popen.assert_called_once_with(["ollama", "serve"], env=mock.ANY)
    mock_run.assert_called_once_with(["ollama", "pull", "llama2:7b"], check=True, env=mock.ANY)

    # Verify return value
    assert result["success"] is True
    assert result["model_name"] == "llama2:7b"
    assert "ollama" in result["download_path"]
```

**Patch paths for each plugin:**

| Plugin | Patch path for subprocess |
|--------|--------------------------|
| Ollama | `src.plugins.ollama_plugin.subprocess.Popen`, `.run` |
| Ultralytics | `src.plugins.ultralytics_plugin.subprocess.run` |
| HLS | `src.plugins.hls_plugin.subprocess.run` |
| OpenVINO | `src.plugins.openvino_plugin.subprocess.run` |

---

## Mocking HuggingFace Downloads

```python
from unittest.mock import patch

@patch('src.plugins.huggingface_plugin.snapshot_download')
def test_hf_download_success(mock_snapshot, plugin, temp_dir):
    # snapshot_download returns the local path
    mock_snapshot.return_value = f"{temp_dir}/huggingface/bert-base-uncased"

    result = plugin.download(
        model_name="bert-base-uncased",
        output_dir=temp_dir,
        hf_token="test-token"
    )

    mock_snapshot.assert_called_once_with(
        repo_id="bert-base-uncased",
        token="test-token",
        local_dir=mock.ANY,
        revision=None,
    )
    assert result["success"] is True
    assert result["source"] == "huggingface"

@patch('src.plugins.huggingface_plugin.snapshot_download')
def test_hf_download_auth_error(mock_snapshot, plugin, temp_dir):
    from huggingface_hub.errors import GatedRepoError
    mock_snapshot.side_effect = GatedRepoError("Repository is gated")

    with pytest.raises(GatedRepoError):
        plugin.download(model_name="gated-model", output_dir=temp_dir)
```

---

## Async Plugin Tests

Some plugins (HLS, Geti) have `async download()` methods. Use `pytest-asyncio`:

```python
import pytest

@pytest.mark.asyncio
async def test_hls_download_3d_pose(plugin, temp_dir):
    with patch('src.plugins.hls_plugin.subprocess.run') as mock_run, \
         patch.object(plugin, '_ensure_hls_venv', return_value='/opt/hls_venv/bin/python'):
        
        result = await plugin.download(
            model_name="hls-3d-pose",
            output_dir=temp_dir,
            type="3d-pose"
        )
        
        assert result["success"] is True
```

**`pyproject.toml` setting needed:**
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## Parametrize for can_handle

Test `can_handle` across all hubs using `@pytest.mark.parametrize`:

```python
@pytest.mark.parametrize("hub,expected", [
    ("myhub", True),
    ("MyHub", True),      # case-insensitive
    ("MYHUB", True),
    ("huggingface", False),
    ("ollama", False),
    ("", False),
    ("random", False),
])
def test_can_handle_hub(plugin, hub, expected):
    assert plugin.can_handle("any-model", hub) == expected
```

---

## Testing Error Paths

### subprocess failure:

```python
@patch('src.plugins.ollama_plugin.subprocess.run')
@patch('src.plugins.ollama_plugin.subprocess.Popen')
@patch('src.plugins.ollama_plugin.time.sleep')
def test_ollama_download_failure(mock_sleep, mock_popen, mock_run, plugin, temp_dir):
    mock_popen.return_value = MagicMock()
    mock_run.side_effect = subprocess.CalledProcessError(1, "ollama pull")

    with pytest.raises(subprocess.CalledProcessError):
        plugin.download(model_name="bad-model", output_dir=temp_dir)
```

### Plugin not activated (PluginRegistry):

```python
from src.core.plugin_registry import PluginRegistry

def test_plugin_not_activated():
    registry = PluginRegistry()
    # Simulate /opt/activated_plugins.env containing only 'ollama'
    with patch.object(registry, 'activated_plugins', ['ollama']):
        available, reason = registry.check_plugin_dependencies("huggingface")
        assert available is False
        assert "not activated" in reason
```

---

## Test File Template

Use this as a starting point for a new plugin's test file:

```python
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from src.plugins.myhub_plugin import MyHubPlugin


class TestMyHubPlugin:
    """Test suite for MyHubPlugin"""

    @pytest.fixture
    def plugin(self):
        return MyHubPlugin()

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_plugin_properties(self, plugin):
        assert plugin.plugin_name == "myhub"
        assert plugin.plugin_type == "downloader"

    @pytest.mark.parametrize("hub,expected", [
        ("myhub", True),
        ("MyHub", True),
        ("huggingface", False),
        ("ollama", False),
    ])
    def test_can_handle_hub(self, plugin, hub, expected):
        assert plugin.can_handle("test-model", hub) == expected

    @patch('src.plugins.myhub_plugin.some_sdk_function')
    def test_download_success(self, mock_sdk, plugin, temp_dir):
        mock_sdk.return_value = f"{temp_dir}/myhub/test-model"

        result = plugin.download(model_name="org/model", output_dir=temp_dir)

        assert result["success"] is True
        assert result["source"] == "myhub"
        assert "myhub" in result["download_path"]

    @patch('src.plugins.myhub_plugin.some_sdk_function')
    def test_download_failure(self, mock_sdk, plugin, temp_dir):
        mock_sdk.side_effect = RuntimeError("Connection failed")

        with pytest.raises(RuntimeError, match="Connection failed"):
            plugin.download(model_name="org/model", output_dir=temp_dir)
```
