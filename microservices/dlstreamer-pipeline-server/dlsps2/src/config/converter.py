# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Converts a :class:`~config.models.PipelineConfig` into a concrete GStreamer
pipeline description string suitable for :meth:`~core.pipeline_manager.PipelineManager.start`.

Supported parameter formats
----------------------------
``element-properties``
    Injects ``property=value`` tokens directly into the pipeline string by
    locating the element whose ``name=<element_name>`` attribute appears in
    the string, then appending the property token before the next ``!``
    separator (or end-of-string).

Note
----
Source substitution (``{auto_source}``) and destination/publisher injection
(MQTT, OPC-UA, InfluxDB, S3, RTSP) are handled separately by
:mod:`config.compat` via :func:`~config.compat.apply_source` and
:func:`~config.compat.apply_destination`.
"""

from __future__ import annotations

import re
from typing import Any

from config.models import PipelineConfig

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

            element = prop_def.element

            if element.format == "element-properties":
                if isinstance(param_value, dict):
                    # Dict value: each entry becomes a separate element property.
                    # e.g. "detection-properties": {"model": "...", "device": "CPU"}
                    # → injects model=... device=CPU into the named element.
                    for prop, val in param_value.items():
                        pipeline = _inject_element_property(
                            pipeline,
                            element_name=element.name,
                            prop=prop,
                            value=val,
                        )
                else:
                    # Scalar value: inject as param_name=value.
                    pipeline = _inject_element_property(
                        pipeline,
                        element_name=element.name,
                        prop=param_name,
                        value=param_value,
                    )
            # Other formats (e.g. "element-name", direct substitution) can be
            # added here as additional elif branches.

    return pipeline
