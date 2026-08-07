# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Compressor type registry + factory + config-schema introspection.

Public API (re-exported at package top level):
  - ``create_compressor(type, **kwargs) -> BaseCompressor`` — construct by type name.
  - ``available_compressor_types() -> list[str]`` — known type names.
  - ``config_schema(type) -> dict`` — JSON Schema of the type's constructor params.

Type names are the compressor classes' own ``.name`` values ("harness",
"tool"). Compressor classes are imported **lazily** (only the requested type),
so ``import adaptive_token_compressor`` stays light and does not pull in the
subpackages' heavy / optional dependencies (e.g. llmlingua). This is distinct
from ``CompressionManager.register_compressor``, which attaches an *already
built* instance to metrics/cache — the factory only constructs.
"""

from __future__ import annotations

import importlib
import inspect
import typing
from typing import Any

from .base import BaseCompressor
from .exceptions import ConfigError

# Type name -> (relative module, class name). Adding a new compressor type = one
# line here. The key MUST equal the class's ``.name`` attribute (asserted in
# tests). Modules are imported lazily by ``_resolve`` so this registry itself is
# cheap to import.
_REGISTRY: dict[str, tuple[str, str]] = {
    "harness": ("..harness.compressor", "HarnessCompressor"),
    "tool": ("..tool.compressor", "ToolCompressor"),
}

# Python type -> JSON Schema primitive. ``bool`` is a distinct key from ``int``
# (dict lookup is by exact type), so bools map to "boolean" not "integer".
_JSON_TYPES: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _resolve(name: str) -> type[BaseCompressor]:
    """Import and return the compressor class for ``name`` (lazy)."""
    try:
        module_path, cls_name = _REGISTRY[name]
    except KeyError:
        raise ConfigError(
            f"unknown compressor type {name!r}; known: {sorted(_REGISTRY)}"
        ) from None
    module = importlib.import_module(module_path, package=__package__)
    return getattr(module, cls_name)


def available_compressor_types() -> list[str]:
    """Sorted list of registered compressor type names."""
    return sorted(_REGISTRY)


def create_compressor(type: str, **kwargs: Any) -> BaseCompressor:
    """Construct a compressor of ``type`` with keyword args.

    Raises ``ConfigError`` for an unknown type. The class validates its own
    kwargs; unexpected/missing kwargs raise ``TypeError`` (constructors are
    keyword-only).
    """
    cls = _resolve(type)
    return cls(**kwargs)


def _annotation_to_schema(annotation: Any) -> dict:
    """Map a resolved type annotation to a JSON Schema fragment (best-effort).

    Unknown annotations yield ``{}`` (no constraint) rather than raising, so new
    parameter types never break schema generation.
    """
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        choices = list(typing.get_args(annotation))
        fragment: dict = {"enum": choices}
        pytypes = {type(c) for c in choices}
        if len(pytypes) == 1:
            json_type = _JSON_TYPES.get(next(iter(pytypes)))
            if json_type is not None:
                fragment["type"] = json_type
        return fragment
    json_type = _JSON_TYPES.get(annotation)
    if json_type is not None:
        return {"type": json_type}
    return {}


def config_schema(type: str) -> dict:
    """JSON Schema describing the constructor parameters of ``type``.

    Built by introspecting the class ``__init__`` signature (``inspect`` +
    ``typing.get_type_hints`` to resolve the modules' stringized annotations),
    so the schema stays in sync with the signature and new types are free.
    Covers constructor params only — router-only fields (cache_size, metrics,
    extra_config) are merged by the caller, not here.
    """
    cls = _resolve(type)
    hints = typing.get_type_hints(cls.__init__)
    signature = inspect.signature(cls.__init__)

    properties: dict[str, dict] = {}
    required: list[str] = []
    for param_name, param in signature.parameters.items():
        if param_name == "self":
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        annotation = hints.get(param_name)
        fragment = _annotation_to_schema(annotation) if annotation is not None else {}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        else:
            fragment = {**fragment, "default": param.default}
        properties[param_name] = fragment

    schema: dict = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema
