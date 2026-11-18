"""Flat public configuration and immutable internal capability groups."""
import inspect
import json
from dataclasses import MISSING, FrozenInstanceError, fields

import pytest

from adaptive_token_compressor import CompressionManager, config_schema, create_compressor
from adaptive_token_compressor.context import ContextCompressor
from adaptive_token_compressor.core.exceptions import ConfigError


def test_flat_constructor_factory_and_manager_share_configuration():
    comp = ContextCompressor(
        protect_recent_tool_turns=2, excluded_tools=["read"],
        large_result_stub=True, large_result_stub_guidance="recovery",
        compression_mode="backend_only", compress_rate=0.4,
    )
    copied = create_compressor("context", **comp.effective_config)
    assert copied.effective_config == comp.effective_config
    assert json.loads(json.dumps(comp.effective_config)) == comp.effective_config
    assert CompressionManager().register_compressor("context", copied).inner is copied
    assert len(comp.effective_config) == 19
    assert not any(isinstance(value, dict) for value in comp.effective_config.values())
    assert comp._window.protect_recent_tool_turns == 2
    assert comp._policy.large_result_stub.guidance == "recovery"
    assert comp._policy.compression.compress_backend.rate == 0.4
    assert comp._rules is comp._policy.rules


def test_internal_groups_require_values_instead_of_defining_defaults():
    comp = ContextCompressor()
    groups = (
        comp._window, comp._policy, comp._rules, comp._policy.large_result_stub,
        comp._policy.compression, comp._policy.compression.compress_backend,
    )
    for group in groups:
        assert all(
            field.default is MISSING and field.default_factory is MISSING
            for field in fields(group)
        )


def test_config_does_not_alias_inputs_or_serialized_output():
    names = ["read"]
    comp = ContextCompressor(excluded_tools=names, compress_rate=0.4)
    names.append("exec")
    output = comp.effective_config
    output["excluded_tools"].append("edit")
    output["compress_rate"] = 0.9
    assert comp.effective_config["excluded_tools"] == ["read"]
    assert comp.effective_config["compress_rate"] == 0.4
    assert comp._policy.excluded_tools == ("read",)
    with pytest.raises(FrozenInstanceError):
        comp._window.protect_recent_tool_turns = 0
    with pytest.raises(FrozenInstanceError):
        comp._policy.rules.enabled = False


@pytest.mark.parametrize("names", [[], (), ["read"], ("read",)])
def test_exclusion_lists_and_tuples_have_same_json_representation(names):
    comp = ContextCompressor(excluded_tools=names)
    assert comp.effective_config["excluded_tools"] == list(names)


@pytest.mark.parametrize("name,invalid", [
    ("protect_recent_tool_turns", -1),
    ("compress_stride_tool_turns", 0),
    ("compress_min_chars", -1),
    ("compression_mode", "backend"),
    ("compression_mode", None),
    ("compress_rate", 0),
    ("compress_rate", 1.1),
    ("timeout", 0),
    ("large_result_min_tokens", 0),
    ("large_result_keep_tool_turns", 0),
    ("large_result_stub_guidance", "Recovery"),
    ("excluded_tools", None),
    ("excluded_tools", "read"),
    ("excluded_tools", [" read"]),
    ("excluded_tools", [1]),
])
def test_invalid_fields_fail_even_in_disabled_capabilities(name, invalid):
    with pytest.raises(ConfigError, match=name):
        ContextCompressor(tool_results=False, **{name: invalid})


@pytest.mark.parametrize("name", [
    "window", "tool_result_policy", "rules", "compression", "compress_backend",
    "compress_timeout", "compress_mode", "enable_claw_compactor", "lossy_tool_results",
])
def test_unsupported_parameters_are_rejected(name):
    with pytest.raises(TypeError, match=name):
        create_compressor("context", **{name: {}})


def test_schema_has_exactly_the_flat_signature_and_complete_defaults():
    schema = config_schema("context")
    props = schema["properties"]
    signature = inspect.signature(ContextCompressor)
    defaults = ContextCompressor().effective_config
    assert set(props) == set(signature.parameters) == set(defaults)
    assert {name: fragment["default"] for name, fragment in props.items()} == defaults
    assert schema["additionalProperties"] is False
    assert not any(fragment.get("type") == "object" for fragment in props.values())
    assert props["compression_mode"]["enum"] == [
        "none", "backend_only", "claw_only", "claw_with_backend",
    ]
    assert props["large_result_stub_guidance"]["enum"] == ["legacy", "recovery"]
    assert props["excluded_tools"] == {
        "type": "array", "items": {"type": "string"}, "default": [],
    }
    assert props["compress_rate"] == {"type": "number", "default": 0.6}
    assert props["timeout"] == {"type": "number", "default": 30.0}
    assert props["large_result_keep_tool_turns"]["default"] == 6
    for name in (
        "protect_recent_tool_turns", "compress_stride_tool_turns",
        "large_result_min_tokens", "large_result_keep_tool_turns", "compress_min_chars",
    ):
        assert props[name]["type"] == "integer"
    json.dumps(schema)


def test_local_checks_accept_valid_boundaries():
    comp = create_compressor(
        "context", protect_recent_tool_turns=0, compress_stride_tool_turns=1,
        compress_min_chars=0, compress_rate=1, timeout=1,
        large_result_min_tokens=1, large_result_keep_tool_turns=1,
    )
    assert comp._window.protect_recent_tool_turns == 0
    assert comp._policy.compression.compress_backend.rate == 1
    assert comp.effective_config["timeout"] == 1
