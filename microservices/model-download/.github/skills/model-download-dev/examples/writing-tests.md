# Example: Writing Tests for a Plugin

## Scenario

Write a realistic unit test suite for the `MyHubPlugin` from
[new-downloader-plugin.md](./new-downloader-plugin.md), following the same style as the existing
plugin tests under `tests/unit/`.

---

## `tests/unit/test_myhub_plugin.py`

```python
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import tempfile
from unittest.mock import patch

import pytest

from src.plugins.myhub_plugin import MyHubPlugin


class TestMyHubPlugin:
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

    @pytest.mark.parametrize(
        "hub,expected",
        [
            ("myhub", True),
            ("MyHub", True),
            ("MYHUB", True),
            ("huggingface", False),
            ("ollama", False),
            ("", False),
        ],
    )
    def test_can_handle_hub(self, plugin, hub, expected):
        assert plugin.can_handle("org/model-name", hub) is expected

    @pytest.mark.asyncio
    @patch("src.plugins.myhub_plugin.download_from_provider")
    async def test_download_success(self, mock_snapshot_download, plugin, temp_dir):
        mock_snapshot_download.return_value = os.path.join(
            temp_dir,
            "myhub",
            "org_model-name",
        )

        result = await plugin.download(
            model_name="org/model-name",
            output_dir=temp_dir,
            revision="main",
            api_token="test-token",
        )

        expected_model_dir = os.path.join(
            temp_dir,
            "myhub",
            "org_model-name",
        )
        mock_snapshot_download.assert_called_once_with(
            model_name="org/model-name",
            revision="main",
            destination=expected_model_dir,
            token="test-token",
        )
        assert result == {
            "model_name": "org/model-name",
            "source": "myhub",
            "download_path": os.path.join(temp_dir, "myhub"),
            "success": True,
        }

    @pytest.mark.asyncio
    @patch("src.plugins.myhub_plugin.download_from_provider")
    async def test_download_uses_env_token(self, mock_snapshot_download, plugin, temp_dir, monkeypatch):
        monkeypatch.setenv("MYHUB_TOKEN", "env-token")

        await plugin.download(
            model_name="org/model-name",
            output_dir=temp_dir,
        )

        assert mock_snapshot_download.call_args.kwargs["token"] == "env-token"

    @pytest.mark.asyncio
    @patch("src.plugins.myhub_plugin.download_from_provider")
    @patch("src.plugins.myhub_plugin.os.getenv")
    async def test_download_rewrites_opt_models_path(
        self,
        mock_getenv,
        mock_snapshot_download,
        plugin,
    ):
        mock_getenv.return_value = "/host/models"

        result = await plugin.download(
            model_name="org/model-name",
            output_dir="/opt/models/downloads",
        )

        assert result["download_path"] == "/host/models/downloads/myhub"

    @pytest.mark.asyncio
    @patch("src.plugins.myhub_plugin.download_from_provider")
    async def test_download_surfaces_sdk_errors(self, mock_snapshot_download, plugin, temp_dir):
        mock_snapshot_download.side_effect = RuntimeError("provider API error")

        with pytest.raises(RuntimeError, match="provider API error"):
            await plugin.download(
                model_name="org/model-name",
                output_dir=temp_dir,
            )
```

---

## Why this version is better

- It patches the SDK function, not the method under test.
- It mirrors the structure already used in `test_huggingface_plugin.py` and other plugin tests.
- It verifies behavior that matters to users: request routing, token use, returned paths, and surfaced failures.

---

## Key Patterns to Follow

### 1. Patch at the usage site

```python
@patch("src.plugins.myhub_plugin.download_from_provider")
```

Do not patch the original third-party module path if the plugin imports the symbol locally.

### 2. Use `@pytest.mark.asyncio` for async plugins

```python
@pytest.mark.asyncio
async def test_download_success(...):
    result = await plugin.download(...)
```

### 3. Prefer a few high-signal tests

Cover:

- plugin properties
- `can_handle()`
- happy path
- auth / env handling
- error propagation
- host-path rewriting if the plugin returns a container path

### 4. Match existing repository style

Use:

- `tests/unit/test_<plugin>_plugin.py`
- `tempfile.TemporaryDirectory()` fixtures
- `unittest.mock.patch`
- direct assertions on the returned result dict

---

## Running the Tests

```bash
cd microservices/model-download
pip install -e ".[dev]"

pytest tests/unit/test_myhub_plugin.py -v

# Run with coverage
pytest tests/unit/test_myhub_plugin.py -v --cov=src.plugins.myhub_plugin
```
