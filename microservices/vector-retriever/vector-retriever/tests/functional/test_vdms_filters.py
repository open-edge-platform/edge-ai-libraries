# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.functional.data import FILTER_CASES
from tests.functional.filter_assertions import (
    assert_batch_query,
    assert_explain_filters,
    assert_filter_capabilities,
    assert_image_query,
    assert_ready,
    assert_top_k_limiting,
    execute_filter_case,
)


@pytest.fixture(scope="module")
def backend_name() -> str:
    """Select VDMS backend overlay for this module."""
    return "vdms"


@pytest.mark.parametrize("case", FILTER_CASES, ids=[c["name"] for c in FILTER_CASES])
def test_vdms_filter(backend_stack, case):
    """VDMS backend should satisfy each filter case individually."""
    execute_filter_case(backend_stack["base_url"], backend_stack["backend"], case)


def test_vdms_ready(backend_stack):
    """VDMS stack /ready endpoint reports ready status."""
    assert_ready(backend_stack["base_url"])


def test_vdms_filter_capabilities(backend_stack):
    """VDMS stack /filter-capabilities includes active backend info."""
    assert_filter_capabilities(backend_stack["base_url"], backend_stack["backend"])


def test_vdms_batch_query(backend_stack):
    """VDMS stack handles a batch of 2 queries correctly."""
    assert_batch_query(backend_stack["base_url"])


def test_vdms_explain_filters(backend_stack):
    """VDMS stack returns compiled_backend_filter when explain_filters=True."""
    assert_explain_filters(backend_stack["base_url"])


def test_vdms_top_k_limiting(backend_stack):
    """VDMS stack respects top_k=2 limit on query results."""
    assert_top_k_limiting(backend_stack["base_url"])


def test_vdms_image_query(backend_stack):
    """VDMS stack handles image queries via base64 and validates mutual exclusivity."""
    assert_image_query(backend_stack["base_url"])
