# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Pydantic models for the legacy DL Streamer Pipeline Server config.json format.

Config file structure
---------------------
{
    "config": {
        "pipelines": [ <PipelineConfig>, ... ]
    },
    "interfaces": { ... }   # optional
}

Each PipelineConfig maps to one named pipeline that can be started via
  POST /pipelines/{name}/{version}
where {version} == pipeline.name (the config field).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Publisher sub-configs
# ---------------------------------------------------------------------------


class MqttPublisherConfig(BaseModel):
    topic: str = "dlstreamer_pipeline_results"
    publish_frame: bool = False
    qos: int = 0

    model_config = {"extra": "allow"}


class OpcuaPublisherConfig(BaseModel):
    variable: str
    publish_frame: bool = False

    model_config = {"extra": "allow"}


class InfluxWriteConfig(BaseModel):
    bucket: str
    org: str
    measurement: str = "dlsps"

    model_config = {"extra": "allow"}


class S3WriteConfig(BaseModel):
    bucket: str
    folder_prefix: str
    block: bool = False

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Pipeline parameter schema (JSON-Schema fragment embedded in config)
# ---------------------------------------------------------------------------


class PipelineParameterElement(BaseModel):
    """Describes how a parameter maps to a GStreamer element property.

    ``property`` lets the request/parameter key differ from the actual
    GStreamer property name being set (e.g. request key ``path`` mapping to
    the ``file-path`` property). If omitted, the parameter key itself is
    used as the property name. It is ignored when ``format`` is
    ``"element-properties"``, since in that case each key of the parameter
    value dict is itself already a literal property name.
    """

    name: str
    property: str | None = None
    format: str = "element-properties"

    model_config = {"extra": "allow"}


class PipelineParameterProperty(BaseModel):
    """One entry in ``parameters.properties``.

    ``element`` may be a single mapping or a list of mappings so that one
    request parameter can fan out and set a property on multiple elements
    at once (e.g. a ``device`` parameter applied to both a ``source`` and a
    ``metaconvert`` element).
    """

    element: PipelineParameterElement | list[PipelineParameterElement] | None = None

    model_config = {"extra": "allow"}


class PipelineParameters(BaseModel):
    """Subset of JSON Schema used to declare pipeline parameters."""

    type: str = "object"
    properties: dict[str, PipelineParameterProperty] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Per-pipeline config entry
# ---------------------------------------------------------------------------


class PipelineConfig(BaseModel):
    """One entry in the ``config.pipelines`` list."""

    name: str
    source: Literal["gstreamer", "image_ingestor"] = "gstreamer"
    queue_maxsize: int = 50
    pipeline: str  # GStreamer launch string (may contain {auto_source} placeholder)
    parameters: PipelineParameters | None = None
    auto_start: bool = False
    # Default REST request body (source/destination/parameters/tags) used to
    # start this pipeline when auto_start is true. Lets a pipeline template
    # with placeholders (e.g. {auto_source}) still be auto-started, by
    # supplying the same body that would otherwise be sent to
    # POST /pipelines/{name}/{version}. Ignored if auto_start is false.
    payload: dict[str, Any] | None = None

    # Optional publisher integrations
    mqtt_publisher: MqttPublisherConfig | None = None
    opcua_publisher: OpcuaPublisherConfig | None = None
    influx_write: InfluxWriteConfig | None = None
    s3_write: S3WriteConfig | None = None

    # Catch any unknown top-level keys in a pipeline entry
    model_config = {"extra": "allow"}

    @property
    def publishers(self) -> dict[str, Any]:
        """Return a dict of {publisher_type: config} for all enabled publishers."""
        result: dict[str, Any] = {}
        if self.mqtt_publisher is not None:
            result["mqtt"] = self.mqtt_publisher
        if self.opcua_publisher is not None:
            result["opcua"] = self.opcua_publisher
        if self.influx_write is not None:
            result["influx"] = self.influx_write
        if self.s3_write is not None:
            result["s3"] = self.s3_write
        return result


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


class AppConfig(BaseModel):
    """Contents of the ``config`` key in config.json."""

    pipelines: list[PipelineConfig] = Field(default_factory=list)
    mqtt_publisher: list[MqttPublisherConfig] | None = None  # global-level publishers

    model_config = {"extra": "allow"}


class LegacyConfig(BaseModel):
    """Root model matching the full config.json file."""

    config: AppConfig
    interfaces: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @property
    def pipelines(self) -> list[PipelineConfig]:
        return self.config.pipelines

    def get_pipeline(self, name: str) -> PipelineConfig | None:
        """Look up a pipeline by its ``name`` field (used as the version segment in the URL)."""
        for p in self.config.pipelines:
            if p.name == name:
                return p
        return None
