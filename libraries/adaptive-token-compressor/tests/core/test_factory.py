"""Tests for core/factory.py — compressor type registry, factory, config schema."""
from __future__ import annotations

import inspect
import json
import typing

import pytest
import responses

from adaptive_token_compressor import (
    available_compressor_types,
    config_schema,
    create_compressor,
)
from adaptive_token_compressor.core.backends import TokenPruneBackend
from adaptive_token_compressor.core.base import CompressionContext
from adaptive_token_compressor.core.exceptions import ConfigError
from adaptive_token_compressor.core.factory import _annotation_to_schema

# Minimal offline construction kwargs per type (avoid required args / optional
# extras that need network or uninstalled packages).
_MIN_KWARGS = {
    "harness": {},
    "tool": {"predictor_url": "http://localhost/v1/chat/completions"},
    "context": {},
}

_EXPECTED_CLASS = {
    "harness": "HarnessCompressor",
    "tool": "ToolCompressor",
    "context": "ContextCompressor",
}


# ─────────────────────────────────────────────────────────────────────────────
# available_compressor_types
# ─────────────────────────────────────────────────────────────────────────────


def test_available_types_are_sorted_names():
    assert available_compressor_types() == ["context", "harness", "tool"]


# ─────────────────────────────────────────────────────────────────────────────
# create_compressor
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("type_name", ["harness", "tool", "context"])
def test_create_returns_expected_class(type_name):
    compressor = create_compressor(type_name, **_MIN_KWARGS[type_name])
    assert type(compressor).__name__ == _EXPECTED_CLASS[type_name]


@pytest.mark.parametrize("type_name", ["harness", "tool", "context"])
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
    # Optional: None resolves to a backend-dependent default at construction.
    assert props["score_threshold"] == {"default": None}
    assert props["top_k"] == {"default": None}
    assert props["timeout"] == {"type": "integer", "default": 120}
    assert props["predictor_model"]["default"] == "Qwen/Qwen3.6-35B-A3B"


def test_config_schema_bool_maps_to_boolean():
    # enable_quantum_lock (harness) / assistant_arguments (context) are bools;
    # bool must map to "boolean", not "integer".
    assert config_schema("harness")["properties"]["enable_quantum_lock"] == {
        "type": "boolean",
        "default": False,
    }
    assert config_schema("context")["properties"]["assistant_arguments"] == {
        "type": "boolean",
        "default": False,
    }

def test_context_excluded_tools_schema_and_factory():
    props = config_schema("context")["properties"]
    assert "protect_tool_results" not in props
    assert "large_result_excluded_tools" not in props
    assert props["excluded_tools"] == {
        "type": "array", "items": {"type": "string"}, "default": [],
    }
    comp = create_compressor("context", excluded_tools=["read"])
    assert comp._excluded_tools == frozenset({"read"})


@pytest.mark.parametrize("annotation", [
    list[str], tuple[str, ...], list[str] | tuple[str, ...],
    typing.Union[typing.List[str], typing.Tuple[str, ...]],
])
def test_equivalent_array_annotations_share_schema(annotation):
    assert _annotation_to_schema(annotation) == {
        "type": "array", "items": {"type": "string"},
    }


@pytest.mark.parametrize("annotation", [list[str] | None, typing.Optional[typing.List[str]]])
def test_nullable_list_schema_preserves_original_behavior(annotation):
    assert _annotation_to_schema(annotation) == {
        "type": ["array", "null"], "items": {"type": "string"},
    }


@pytest.mark.parametrize("annotation", [
    int | None, float | None, str | None,
    typing.Optional[typing.Literal["legacy", "recovery"]],
    tuple[str, ...] | None,
    list[str] | tuple[int, ...],
])
def test_other_unions_preserve_unspecified_schema(annotation):
    assert _annotation_to_schema(annotation) == {}


def test_tuple_default_is_an_independent_json_array():
    from adaptive_token_compressor.context import ContextCompressor

    default = config_schema("context")["properties"]["excluded_tools"]["default"]
    assert type(default) is list
    default.append("read")
    assert config_schema("context")["properties"]["excluded_tools"]["default"] == []
    assert inspect.signature(ContextCompressor).parameters["excluded_tools"].default == ()
    assert ContextCompressor().effective_config["excluded_tools"] == []


@pytest.mark.parametrize("type_name", ["harness", "tool", "context"])
def test_config_schema_is_json_serializable(type_name):
    # All constructor defaults must serialize.
    json.dumps(config_schema(type_name))


@pytest.mark.parametrize("type_name,timeout", [("harness", 60.0), ("context", 30.0)])
def test_default_backend_remains_token_prune(type_name, timeout):
    comp = create_compressor(type_name)
    assert isinstance(comp._backend, TokenPruneBackend)
    assert comp._backend.cache_tag == "token_prune"
    assert comp._backend._timeout == timeout


@pytest.mark.parametrize("type_name", ["harness", "context"])
@responses.activate
def test_compress_server_wiring_after_backend_removal(type_name):
    url = "http://compress-server.test/compress"
    responses.post(url, json={"compressed_prompt": "compressed"})
    kwargs = {
        "compress_server_url": url,
        "compress_rate": 0.4,
        "compress_min_chars": 1,
    }
    if type_name == "context":
        kwargs.update(
            protect_recent_tool_turns=0, compression_mode="backend_only", timeout=12.0,
        )
        role = "tool"
    else:
        kwargs.update(timeout=12.0, profile="generic")
        role = "system"
    comp = create_compressor(type_name, **kwargs)
    assert isinstance(comp._backend, TokenPruneBackend)
    assert comp._backend.cache_tag == "token_prune"
    assert comp._backend._timeout == 12.0
    result = comp.compress(CompressionContext(messages=[{
        "role": role, "content": "The original source text to compress. " * 100,
    }]))
    assert result.metrics.error is None
    assert result.metrics.saved_tokens > 0
    assert responses.calls
    for call in responses.calls:
        assert call.request.url == url
        assert json.loads(call.request.body)["rate"] == 0.4
    if type_name == "context":
        assert json.loads(responses.calls[0].request.body)["mode"] == "llmlingua2"


def test_context_stub_guidance_schema_and_factory():
    props = config_schema("context")["properties"]
    assert props["large_result_stub"] == {
        "type": "boolean", "default": True,
    }
    assert props["large_result_stub_guidance"] == {
        "type": "string", "enum": ["legacy", "recovery"], "default": "recovery",
    }
    for guidance in ("legacy", "recovery"):
        comp = create_compressor(
            "context", large_result_stub_guidance=guidance,
        )
        assert comp._large_result_stub_guidance == guidance
    with pytest.raises(ConfigError, match="guidance"):
        create_compressor("context", large_result_stub_guidance="invalid")


@pytest.mark.parametrize("type_name", ["harness", "tool", "context"])
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
            assert props[name]["default"] == json.loads(json.dumps(param.default))
            assert name not in required
