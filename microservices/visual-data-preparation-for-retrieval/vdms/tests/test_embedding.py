# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from src.core.embedding import vCLIPEmbeddings


def test_validate_environment():
    values = {"model": "super-model"}
    assert vCLIPEmbeddings.validate_environment(values) == values


def test_validate_environment_value_error():
    values = {"no-model": "zero-model"}
    with pytest.raises(ValueError):
        vCLIPEmbeddings.validate_environment(values)


def test_validate_environment_import_error(mocker):
    values = {"model": "super-model"}
    mocker.patch("src.core.embedding.vCLIPEmbeddings.validate_environment", side_effect=ImportError)
    with pytest.raises(ImportError):
        vCLIPEmbeddings.validate_environment(values)


def test_validate_environment_handle_value_error(mocker):
    values = {"no-model": "zero-model"}
    with pytest.raises(ValueError):
        vCLIPEmbeddings.validate_environment(values)
