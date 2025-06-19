"""
Unit tests for the val_to_correct_type method in ModelIn and UpdateModelIn classes.
Tests validation and conversion of input values for 'overview' and 'labels' fields.
"""

import pytest
from fastapi import HTTPException
from models.registered_model import RegisteredModel, ModelIn, UpdateModelIn

def test_registered_model_initialization():
    """Test that a RegisteredModel is created."""
    registered_model = RegisteredModel()
    assert isinstance(registered_model, RegisteredModel)
    assert registered_model.name is None

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

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_overview_empty_string(cls):
    """Test that an empty string for 'overview' raises HTTPException 422."""
    val = ''
    with pytest.raises(HTTPException) as exc:
        cls.val_to_correct_type("overview", val)
    assert exc.value.status_code == 422
    assert "overview is not a valid JSON object." in str(exc.value.detail)

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_labels_empty_string(cls):
    """Test that an empty string for 'labels' raises HTTPException 422."""
    val = ''
    with pytest.raises(HTTPException) as exc:
        cls.val_to_correct_type("labels", val)
    assert exc.value.status_code == 422
    assert "labels is not a valid list." in str(exc.value.detail)

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_labels_not_json(cls):
    """Test that a non-JSON string for 'labels' raises HTTPException 422."""
    val = 'not a json'
    with pytest.raises(HTTPException) as exc:
        cls.val_to_correct_type("labels", val)
    assert exc.value.status_code == 422
    assert "labels is not a valid list." in str(exc.value.detail)

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_labels_dict_string(cls):
    """Test that a dict string for 'labels' raises HTTPException 422."""
    val = '{"name": "cat"}'
    with pytest.raises(HTTPException) as exc:
        cls.val_to_correct_type("labels", val)
    assert exc.value.status_code == 422
    assert "labels is not a valid list." in str(exc.value.detail)

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_labels_list_of_ints(cls):
    """Test that a valid list of ints string for 'labels' is accepted."""
    val = '[1, 2, 3]'
    result = cls.val_to_correct_type("labels", val)
    assert isinstance(result, list)
    assert result == [1, 2, 3]

@pytest.mark.parametrize("cls", [ModelIn, UpdateModelIn])
def test_val_to_correct_type_labels_list_of_dicts(cls):
    """Test that a valid list of dicts string for 'labels' is accepted."""
    val = '[{"name": "cat"}, {"name": "dog"}]'
    result = cls.val_to_correct_type("labels", val)
    assert isinstance(result, list)
    assert result[0]["name"] == "cat"

def test_modelin_constructor_sets_attributes():
    """Test ModelIn constructor sets attributes correctly."""
    class DummyFile:
        pass
    file = DummyFile()
    model = ModelIn(
        file=file,
        name="Test",
        version="1.0",
        target_device="CPU",
        precision="FP32",
        format="openvino",
        score=0.9,
        id="abc",
        created_date="2024-01-01",
        size=123,
        origin="geti",
        project_id="pid",
        project_name="pname",
        category="Classification",
        target_device_type="edge",
        overview='{"description": "desc"}',
        optimization_capabilities='{"optimization": "speed"}',
        labels='[{"name": "cat"}]',
        architecture="ResNet"
    )
    assert model.name == "Test"
    assert model.overview == {"description": "desc"}
    assert model.optimization_capabilities == {"optimization": "speed"}
    assert isinstance(model.labels, list)
    assert model.architecture == "ResNet"

def test_updatemodelin_constructor_sets_attributes():
    """Test UpdateModelIn constructor sets attributes correctly."""
    model = UpdateModelIn(
        name="Test",
        version="1.0",
        target_device="CPU",
        precision="FP32",
        format="openvino",
        score=0.9,
        created_date="2024-01-01",
        size=123,
        origin="geti",
        project_id="pid",
        project_name="pname",
        category="Classification",
        target_device_type="edge",
        overview='{"description": "desc"}',
        optimization_capabilities='{"optimization": "speed"}',
        labels='[{"name": "cat"}]',
        architecture="ResNet"
    )
    assert model.name == "Test"
    assert model.overview == {"description": "desc"}
    assert model.optimization_capabilities == {"optimization": "speed"}
    assert isinstance(model.labels, list)
    assert model.architecture == "ResNet"
