"""
Unit tests for the val_to_correct_type method in ModelIn and UpdateModelIn classes.
Tests validation and conversion of input values for 'overview' and 'labels' fields.
"""

import pytest
from fastapi import HTTPException
from models.registered_model import ModelIn, UpdateModelIn


@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_overview_valid(cls):
    """Test that a valid JSON string for 'overview' is converted to a dict."""
    val = '{"description": "test"}'
    result = cls.val_to_correct_type("overview", val)
    assert isinstance(result, dict)
    assert result["description"] == "test"

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_overview_invalid(cls):
    """Test that an invalid JSON string for 'overview' raises HTTPException 422."""
    val = '{"description": "test"'  # missing closing }
    with pytest.raises(HTTPException) as exc:
        cls.val_to_correct_type("overview", val)
    assert exc.value.status_code == 422
    assert "overview is not a valid JSON object." in str(exc.value.detail)

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_labels_valid(cls):
    """Test that a valid JSON string for 'labels' is converted to a list."""
    val = '[{"name": "cat"}, {"name": "dog"}]'
    result = cls.val_to_correct_type("labels", val)
    assert isinstance(result, list)
    assert result[0]["name"] == "cat"

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_labels_invalid_syntax(cls):
    """Test that an invalid JSON string for 'labels' raises HTTPException 422."""
    val = '[{"name": "cat"}, {"name": "dog"}'  # missing closing ]
    with pytest.raises(HTTPException) as exc:
        cls.val_to_correct_type("labels", val)
    assert exc.value.status_code == 422
    assert "labels is not a valid list." in str(exc.value.detail)

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_labels_not_list(cls):
    """Test that a non-list JSON string for 'labels' raises HTTPException 422."""
    val = '{"name": "cat"}'  # not a list
    with pytest.raises(HTTPException) as exc:
        cls.val_to_correct_type("labels", val)
    assert exc.value.status_code == 422
    assert "labels is not a valid list." in str(exc.value.detail)

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
@pytest.mark.parametrize("var_name,val", [
    ("overview", {"description": "test"}),
    ("optimization_capabilities", {"optimization": "speed"}),
    ("labels", [{"name": "cat"}]),
    ("labels", []),
    ("overview", None),
    ("labels", None),
])
def test_val_to_correct_type_passthrough(cls, var_name, val):
    """Test that non-string values are returned as-is by val_to_correct_type."""
    # Should return the value as-is if not a string
    result = cls.val_to_correct_type(var_name, val)
    assert result == val
