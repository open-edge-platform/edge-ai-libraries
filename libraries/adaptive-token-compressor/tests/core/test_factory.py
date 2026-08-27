"""Tests for core/factory.py — compressor type registry, factory, config schema."""
from __future__ import annotations

import inspect
import json
import typing

import pytest

from adaptive_token_compressor import (
    available_compressor_types,
    config_schema,
    create_compressor,
)
from adaptive_token_compressor.core.exceptions import ConfigError

# Minimal offline construction kwargs per type (avoid required args / optional
# extras that need network or uninstalled packages).
_MIN_KWARGS = {
    "harness": {},
    "tool": {"predictor_url": "http://localhost/v1/chat/completions"},
}

_EXPECTED_CLASS = {
    "harness": "HarnessCompressor",
    "tool": "ToolCompressor",
}


# ─────────────────────────────────────────────────────────────────────────────
# available_compressor_types
# ─────────────────────────────────────────────────────────────────────────────


def test_available_types_are_sorted_names():
    assert available_compressor_types() == ["harness", "tool"]


# ─────────────────────────────────────────────────────────────────────────────
# create_compressor
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("type_name", ["harness", "tool"])
def test_create_returns_expected_class(type_name):
    compressor = create_compressor(type_name, **_MIN_KWARGS[type_name])
    assert type(compressor).__name__ == _EXPECTED_CLASS[type_name]


@pytest.mark.parametrize("type_name", ["harness", "tool"])
def test_registry_key_equals_instance_name(type_name):
    # The registry key must equal the class's own ``.name`` (the contract that
    # lets the key double as the config ``node`` value).
    compressor = create_compressor(type_name, **_MIN_KWARGS[type_name])
    assert compressor.name == type_name


def test_create_unknown_type_raises_config_error():
    with pytest.raises(ConfigError) as exc:
        create_compressor("nope")
    assert "unknown compressor type 'nope'" in str(exc.value)


def test_create_missing_required_kwarg_raises_type_error():
    # ToolCompressor.predictor_url is required and keyword-only.
    with pytest.raises(TypeError):
        create_compressor("tool")


# ─────────────────────────────────────────────────────────────────────────────
# config_schema
# ─────────────────────────────────────────────────────────────────────────────


def test_config_schema_unknown_type_raises_config_error():
    with pytest.raises(ConfigError):
        config_schema("nope")


def test_config_schema_tool_shape():
    schema = config_schema("tool")
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    props = schema["properties"]

    # predictor_url is the only required param (no default).
    assert schema["required"] == ["predictor_url"]
    assert props["predictor_url"] == {"type": "string"}

    # Literal -> enum (+ inferred primitive type).
    assert props["placement"]["enum"] == [
        "schema",
        "user_tail",
        "system_tail",
        "user_inline",
        "user_inline_delta",
    ]
    assert props["placement"]["type"] == "string"
    assert props["prompt_mode"]["enum"] == ["static", "dynamic"]

    # Defaults + primitive type mapping.
    assert props["score_threshold"] == {"type": "number", "default": 2.0}
    assert props["timeout"] == {"type": "integer", "default": 120}
    assert props["predictor_model"]["default"] == "Qwen/Qwen3.6-35B-A3B"


def test_config_schema_bool_maps_to_boolean():
    # enable_quantum_lock (harness) is a bool; bool must map to "boolean", not
    # "integer".
    assert config_schema("harness")["properties"]["enable_quantum_lock"] == {
        "type": "boolean",
        "default": False,
    }


@pytest.mark.parametrize("type_name", ["harness", "tool"])
def test_config_schema_is_json_serializable(type_name):
    # Defaults must serialize.
    json.dumps(config_schema(type_name))


@pytest.mark.parametrize("type_name", ["harness", "tool"])
def test_config_schema_round_trips_against_init_signature(type_name):
    # Every non-var constructor param appears in properties; params with no
    # default are exactly the `required` set; defaults match the signature.
    from adaptive_token_compressor.core.factory import _resolve

    cls = _resolve(type_name)
    signature = inspect.signature(cls.__init__)
    schema = config_schema(type_name)
    props = schema["properties"]
    required = set(schema.get("required", []))

    for name, param in signature.parameters.items():
        if name == "self" or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        assert name in props, f"{type_name}: {name} missing from schema"
        if param.default is inspect.Parameter.empty:
            assert name in required
        else:
            assert props[name]["default"] == param.default
            assert name not in required
