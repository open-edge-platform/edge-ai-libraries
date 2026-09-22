# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Converts a :class:`~config.models.PipelineConfig` into a concrete GStreamer
pipeline description string suitable for :meth:`~core.pipeline_manager.PipelineManager.start`.

Supported parameter formats (``config.parameters.properties.<key>.element.format``)
------------------------------------------------------------------------------------
``element-properties`` (default)
    If the runtime parameter value is a ``dict``, each of its keys is
    injected as a literal ``property=value`` token (the ``element.property``
    remap, if any, is ignored since the dict keys are themselves already
    literal property names). If the value is a scalar, it is injected as
    ``<element.property or param_name>=value``.
``json``
    The runtime parameter value (scalar or ``dict``) is JSON-encoded and
    injected as a single ``<element.property or param_name>=<json>`` token.
    Mirrors DLSPS 1.0's ``format: json`` (e.g. a ``kwarg`` property on a
    ``gvapython`` element).
(anything else, including no format)
    The runtime parameter value is injected as-is as a single
    ``<element.property or param_name>=value`` token (direct substitution).

``element`` may also be a list of the mappings described above, in which
case the same runtime parameter value is applied to every element in the
list (e.g. one ``device`` parameter setting a property on both a ``source``
and a ``metaconvert`` element).

Property injection locates the element whose ``name=<element_name>``
attribute appears in the pipeline string, then appends the property token
before the next ``!`` separator (or end-of-string).

Note
----
Source substitution (``{auto_source}``) and destination/publisher injection
(MQTT, OPC-UA, InfluxDB, S3, RTSP) are handled separately by
:mod:`config.compat` via :func:`~config.compat.apply_source` and
:func:`~config.compat.apply_destination`.
"""

from __future__ import annotations

import json
import re
from typing import Any

from config.models import PipelineConfig, PipelineParameterElement

# Matches the end of a named element's token block, i.e. the ``!`` that follows
# the element whose ``name=<target>`` attribute we just found, or end-of-string.
# Group 1 captures everything from the start of the element up to (but not
# including) the trailing ``!`` / end.
_ELEMENT_BLOCK_RE = re.compile(
    r"((?:^|(?<=!))\s*\S[^!]*?\bname\s*=\s*{name}\b[^!]*?)(\s*!|\s*$)",
    re.DOTALL,
)


def _inject_element_property(pipeline: str, element_name: str, prop: str, value: Any) -> str:
    """Return *pipeline* with ``prop=value`` injected into the named element block.

    If the element is not found, the pipeline string is returned unchanged and
    no error is raised (the property will be silently ignored).
    """
    pattern = re.compile(
        r"((?:^|(?<=!))\s*\S[^!]*?\bname\s*=\s*" + re.escape(element_name) + r"\b[^!]*)(\s*!|\s*$)",
        re.DOTALL,
    )
    match = pattern.search(pipeline)
    if not match:
        return pipeline

    insertion_point = match.end(1)
    prop_token = f" {prop}={value}"
    # Strip any trailing whitespace already present at the insertion point so
    # we don't accumulate double spaces before the next "!" separator.
    trimmed = pipeline[:insertion_point].rstrip()
    return trimmed + prop_token + " " + pipeline[insertion_point:].lstrip()


def _apply_parameter_to_element(
    pipeline: str,
    element: PipelineParameterElement,
    param_name: str,
    param_value: Any,
) -> str:
    """Inject one runtime parameter value into one target element.

    Honors ``element.format`` (``element-properties`` / ``json`` / direct
    substitution) and ``element.property`` (remaps the request's parameter
    name to a different literal GStreamer property name; ignored for
    ``element-properties`` dict values, whose own keys are already literal
    property names).
    """
    if element.format == "element-properties" and isinstance(param_value, dict):
        for prop, val in param_value.items():
            pipeline = _inject_element_property(
                pipeline, element_name=element.name, prop=prop, value=val
            )
        return pipeline

    prop_name = element.property or param_name

    if element.format == "json":
        pipeline = _inject_element_property(
            pipeline, element_name=element.name, prop=prop_name, value=json.dumps(param_value)
        )
    else:
        # Covers "element-properties" with a scalar value, plus any other
        # (or unset) format: inject the value as-is under prop_name.
        pipeline = _inject_element_property(
            pipeline, element_name=element.name, prop=prop_name, value=param_value
        )
    return pipeline


def build_pipeline_string(
    config: PipelineConfig,
    parameters: dict[str, Any] | None = None,
) -> str:
    """Build a GStreamer launch string from a :class:`PipelineConfig`.

    Args:
        config:     A validated pipeline configuration entry.
        parameters: Optional runtime parameter overrides.  Keys must match
                    parameter names declared in ``config.parameters.properties``.
                    Unknown keys are ignored.

    Returns:
        A GStreamer pipeline description string ready to pass to
        ``gst-launch-1.0`` or :func:`Gst.parse_launch`.

    Note:
        Source substitution and destination injection are not performed here.
        Call :func:`~config.compat.apply_source` and
        :func:`~config.compat.apply_destination` after this function.
    """
    pipeline = config.pipeline

    if parameters and config.parameters and config.parameters.properties:
        for param_name, param_value in parameters.items():
            prop_def = config.parameters.properties.get(param_name)
            if prop_def is None or prop_def.element is None:
                continue

            elements = (
                prop_def.element
                if isinstance(prop_def.element, list)
                else [prop_def.element]
            )
            for element in elements:
                pipeline = _apply_parameter_to_element(pipeline, element, param_name, param_value)

    return pipeline
