"""Test configuration and fixtures."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.matchers.base import MatchResult


@pytest.fixture
def mock_vlm_backend():
    """Mock VLM backend for testing."""
    backend = AsyncMock()
    backend.name = "mock"
    backend.is_available.return_value = True
    backend.generate_text.return_value = "YES"
    return backend


@pytest.fixture
def sample_expected_items():
    """Sample expected items for testing."""
    return [
        {"name": "apple", "quantity": 2},
        {"name": "banana", "quantity": 1},
        {"name": "milk", "quantity": 1},
    ]


@pytest.fixture
def sample_detected_items_exact_match():
    """Sample detected items with exact matches."""
    return [
        {"name": "apple", "quantity": 2},
        {"name": "banana", "quantity": 1},
        {"name": "milk", "quantity": 1},
    ]


@pytest.fixture
def sample_detected_items_with_mismatch():
    """Sample detected items with mismatches."""
    return [
        {"name": "green apple", "quantity": 2},  # Semantic match
        {"name": "banana", "quantity": 2},  # Quantity mismatch
        {"name": "orange", "quantity": 1},  # Extra item
    ]


@pytest.fixture
def sample_inventory():
    """Sample inventory for testing."""
    return [
        "Apple - Granny Smith",
        "Apple - Red Delicious",
        "Banana - Organic",
        "Milk - Whole 1L",
        "Bread - Wheat",
        "Cheese - Cheddar",
    ]


@pytest.fixture
def mock_match_result_positive():
    """Mock positive match result."""
    return MatchResult(
        match=True,
        confidence=0.95,
        reasoning="Semantic match via VLM",
        match_type="semantic",
    )


@pytest.fixture
def mock_match_result_negative():
    """Mock negative match result."""
    return MatchResult(
        match=False,
        confidence=0.1,
        reasoning="No semantic match",
        match_type="semantic",
    )
