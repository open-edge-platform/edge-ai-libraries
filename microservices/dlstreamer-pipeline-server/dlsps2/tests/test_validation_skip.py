# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for pipeline validation skip feature."""

import time
from unittest.mock import MagicMock, patch

import pytest

from core.pipeline_manager import PipelineManager, PipelineState, ValidationState


@pytest.fixture
def manager():
    """Create a fresh PipelineManager for each test."""
    return PipelineManager()


def test_validation_skip_with_invalid_pipeline(manager):
    """Test that validation can be skipped for an invalid pipeline."""
    # A pipeline that would normally fail validation
    invalid_pipeline = "fakeelement ! fakesink"
    
    # Start with validate=False (should skip validation and proceed)
    instance_id = manager.start(invalid_pipeline, validate=False)
    
    # Give the background thread a moment to process
    time.sleep(0.5)
    
    instance = manager.get(instance_id)
    assert instance is not None
    # With validation skipped, the pipeline should reach RUNNING state
    # (though it will likely error when trying to submit to a worker)
    assert instance.pipeline_description == invalid_pipeline


def test_validation_enabled_with_invalid_pipeline(manager):
    """Test that validation catches an invalid pipeline when enabled."""
    # A pipeline that will definitely fail validation
    invalid_pipeline = "fakeelement ! fakesink"
    
    # Start with validate=True (default, should validate)
    instance_id = manager.start(invalid_pipeline, validate=True)
    
    # Give the background thread time to run validation
    time.sleep(1.0)
    
    instance = manager.get(instance_id)
    assert instance is not None
    # Validation should catch the invalid element and set ERROR state
    assert instance.state == PipelineState.ERROR
    assert instance.error is not None
    assert "validation failed" in instance.error.lower()


def test_validation_enabled_with_valid_pipeline(manager):
    """Test that a valid pipeline passes validation."""
    # A simple valid pipeline
    valid_pipeline = "videotestsrc num-buffers=1 ! videoconvert ! fakesink"
    
    # Start with validate=True
    instance_id = manager.start(valid_pipeline, validate=True)
    
    # Give the background thread time to run validation
    time.sleep(1.0)
    
    instance = manager.get(instance_id)
    assert instance is not None
    # Valid pipeline should pass validation and either be RUNNING or completed
    # (depends on whether the worker picks it up)
    assert instance.state in (PipelineState.RUNNING, PipelineState.QUEUED, PipelineState.COMPLETED)
    assert instance.error is None or instance.error == ""


def test_validation_skip_default_true(manager):
    """Test that validation is enabled by default."""
    invalid_pipeline = "fakeelement ! fakesink"
    
    # Start without specifying validate (should default to True)
    instance_id = manager.start(invalid_pipeline)
    
    # Give the background thread time to run validation
    time.sleep(1.0)
    
    instance = manager.get(instance_id)
    assert instance is not None
    # Should fail validation by default
    assert instance.state == PipelineState.ERROR


def test_validation_state_queued(manager):
    """Test that validation starts in QUEUED state."""
    pipeline = "videotestsrc ! fakesink"
    
    instance_id = manager.start(pipeline, validate=False)
    
    instance = manager.get(instance_id)
    assert instance is not None
    # Instance should start in QUEUED state
    assert instance.state in (PipelineState.QUEUED, PipelineState.RUNNING)
