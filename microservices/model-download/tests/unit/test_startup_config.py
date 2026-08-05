# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
from unittest.mock import patch

import pytest
import yaml

from src.core.startup_config import (
    MAX_STARTUP_CONFIG_SIZE_BYTES,
    MAX_STARTUP_MODELS,
    STARTUP_MODELS_CONFIG_ENV,
    load_startup_models_config,
)


def _valid_config(**overrides):
    config = {
        "download_path": "preloaded",
        "parallel_downloads": True,
        "models": [{"name": "org/model", "hub": "huggingface"}],
    }
    config.update(overrides)
    return config


@pytest.mark.parametrize("suffix", [".yaml", ".yml"])
def test_loads_yaml_config_with_default_and_per_model_paths(tmp_path, suffix):
    config_path = tmp_path / f"startup{suffix}"
    config_path.write_text(
        """
download_path: defaults
parallel_downloads: true
models:
  - name: org/default
    hub: huggingface
  - name: org/override
    hub: ultralytics
    type: vision
    download_path: vision
""",
        encoding="utf-8",
    )

    config = load_startup_models_config(config_path)

    assert config is not None
    assert config.download_path == "defaults"
    assert config.parallel_downloads is True
    assert config.models[0].download_path is None
    assert config.models[1].download_path == "vision"


def test_loads_yaml_config_from_environment(tmp_path, monkeypatch):
    config_path = tmp_path / "startup.yaml"
    config_path.write_text(yaml.safe_dump(_valid_config()), encoding="utf-8")
    monkeypatch.setenv(STARTUP_MODELS_CONFIG_ENV, str(config_path))

    config = load_startup_models_config()

    assert config is not None
    assert config.download_path == "preloaded"
    assert config.models[0].name == "org/model"


def test_loads_json_config_for_future_compatibility(tmp_path):
    config_path = tmp_path / "startup.json"
    config_path.write_text(json.dumps(_valid_config()), encoding="utf-8")

    config = load_startup_models_config(config_path)

    assert config is not None
    assert config.download_path == "preloaded"


def test_rejects_unsupported_config_extension(tmp_path):
    config_path = tmp_path / "startup.txt"
    config_path.write_text(yaml.safe_dump(_valid_config()), encoding="utf-8")

    with patch("src.core.startup_config.yaml.safe_load") as yaml_load:
        result = load_startup_models_config(config_path)

    assert result is None
    yaml_load.assert_not_called()


def test_unset_environment_disables_startup_config(monkeypatch):
    monkeypatch.delenv(STARTUP_MODELS_CONFIG_ENV, raising=False)

    assert load_startup_models_config() is None


@pytest.mark.parametrize(
    ("path_factory", "expected_reason"),
    [
        (lambda root: "", "is empty"),
        (lambda root: root / "missing.yaml", "cannot be read"),
        (lambda root: root / "startup.toml", "unsupported file extension"),
        (lambda root: root / "directory.yaml", "not a regular file"),
    ],
)
def test_unusable_paths_are_logged_without_raising(
    tmp_path,
    path_factory,
    expected_reason,
):
    configured_path = path_factory(tmp_path)
    if expected_reason == "not a regular file":
        configured_path.mkdir()

    with patch("src.core.startup_config.logger.error") as log_error:
        result = load_startup_models_config(configured_path)

    assert result is None
    assert expected_reason in log_error.call_args.kwargs["reason"]
    assert log_error.call_args.kwargs["action"]


def test_oversized_config_is_rejected_before_parsing(tmp_path):
    config_path = tmp_path / "oversized.yaml"
    config_path.write_bytes(b" " * (MAX_STARTUP_CONFIG_SIZE_BYTES + 1))

    with patch("src.core.startup_config.yaml.safe_load") as yaml_load:
        result = load_startup_models_config(config_path)

    assert result is None
    yaml_load.assert_not_called()


@pytest.mark.parametrize(
    ("filename", "contents"),
    [
        ("empty.yaml", ""),
        ("malformed.json", "{"),
        ("malformed.yaml", "models: ["),
        ("unsafe.yaml", "!!python/object/apply:os.system ['echo unsafe']"),
        ("invalid.yaml", "download_path: models\nmodels:\n  - name: model\n    hub: invalid"),
        ("unknown.yaml", "download_path: models\nmodels: []\nunknown: value"),
    ],
)
def test_malformed_or_invalid_config_is_rejected(tmp_path, filename, contents):
    config_path = tmp_path / filename
    config_path.write_text(contents, encoding="utf-8")

    assert load_startup_models_config(config_path) is None


def test_invalid_utf8_config_is_rejected(tmp_path):
    config_path = tmp_path / "startup.yaml"
    config_path.write_bytes(b"\xff\xfe")

    assert load_startup_models_config(config_path) is None


@pytest.mark.parametrize(
    "config",
    [
        _valid_config(download_path=" "),
        _valid_config(download_path="bad\0path"),
        _valid_config(models=[]),
        _valid_config(models=[{"name": "", "hub": "huggingface"}]),
        _valid_config(models=[{"name": "model", "hub": "unsupported"}]),
        _valid_config(models=[{"name": "model", "hub": "huggingface", "extra": True}]),
        _valid_config(
            models=[
                {
                    "name": "model",
                    "hub": "huggingface",
                    "download_path": "../bad\0path",
                }
            ]
        ),
    ],
)
def test_schema_rejects_invalid_values(tmp_path, config):
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    assert load_startup_models_config(config_path) is None


@pytest.mark.parametrize(
    ("model_count", "is_valid"),
    [
        (MAX_STARTUP_MODELS, True),
        (MAX_STARTUP_MODELS + 1, False),
    ],
)
def test_model_count_is_bounded(tmp_path, model_count, is_valid):
    models = [
        {"name": f"org/model-{index}", "hub": "huggingface"}
        for index in range(model_count)
    ]
    config_path = tmp_path / "startup.yaml"
    config_path.write_text(
        yaml.safe_dump(_valid_config(models=models)),
        encoding="utf-8",
    )

    config = load_startup_models_config(config_path)

    assert (config is not None) is is_valid
