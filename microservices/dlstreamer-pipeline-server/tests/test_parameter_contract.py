#
# Apache v2 license
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""Conformance tests for the DL Streamer Pipeline Server parameter binding contract.

Each test maps directly to one of the six invariants listed in AGENTS.md and
parameter_contract.md.  No SceneScape-specific fixtures or imports are used.

Invariants tested:
  1. String-form element binding uses the parameter key as the property name.
  2. Object-form element binding uses the explicit 'property' field.
  3. Array-form element binding applies to all listed elements.
  4. format=element-properties fans out key/value pairs as individual set_property calls.
  5. format=json JSON-serializes the value before calling set_property.
  6. Unresolved element name is logged at DEBUG and does not raise an exception.
"""

import json
import pytest
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Helpers — build a minimal GStreamerPipeline instance without a live GStreamer
# ---------------------------------------------------------------------------

def _make_pipeline(mocker, request_params=None, config_params=None):
    """Return a GStreamerPipeline whose internals are mocked enough to exercise
    _get_element_property, _set_element_property, and _set_section_properties.
    """
    # Patch the GStreamer initialisation that runs at class body level.
    mocker.patch("gi.repository.Gst.init")
    mocker.patch("src.server.gstreamer_pipeline.GStreamerPipeline._mainloop", None)

    from src.server.gstreamer_pipeline import GStreamerPipeline

    config = {
        "template": "fakesrc name=source ! fakesink name=destination",
        "type": "GStreamer",
        "parameters": {
            "type": "object",
            "properties": config_params or {},
        },
    }
    request = {
        "source": {"type": "uri", "uri": "file://test.mp4"},
        "destination": {"metadata": {"type": "file", "path": "/tmp/out.json"}},
        "parameters": request_params or {},
    }

    mock_options = MagicMock()
    mock_options.enable_rtsp = False
    mock_options.enable_webrtc = False

    gp = GStreamerPipeline.__new__(GStreamerPipeline)
    gp.identifier = "contract-test"
    gp.config = config
    gp.request = request
    gp._options = mock_options
    gp._unset_properties = []
    gp._logger = MagicMock()

    # Attach a mock GStreamer pipeline object.
    gp.pipeline = MagicMock()

    return gp


# ---------------------------------------------------------------------------
# Invariant 1 — String-form binding uses the parameter key as the property name
# ---------------------------------------------------------------------------

class TestStringFormBinding:
    """Invariant 1: 'element': '<name>' → property name == parameter key."""

    def test_property_name_is_parameter_key(self, mocker):
        config_params = {
            "inference-interval": {
                "element": "detection",
                "type": "integer",
                "default": 1,
            }
        }
        request_params = {"inference-interval": 4}
        gp = _make_pipeline(mocker, request_params, config_params)

        mock_element = MagicMock()
        mock_element.list_properties.return_value = [
            MagicMock(name="inference-interval")
        ]
        gp.pipeline.get_by_name.side_effect = lambda name: (
            mock_element if name == "detection" else None
        )

        gp._set_section_properties(["parameters"], ["parameters", "properties"])

        mock_element.set_property.assert_called_once_with("inference-interval", 4)

    def test_element_looked_up_by_string_value(self, mocker):
        config_params = {
            "threshold": {
                "element": "classify",
                "type": "number",
            }
        }
        request_params = {"threshold": 0.8}
        gp = _make_pipeline(mocker, request_params, config_params)

        mock_element = MagicMock()
        mock_element.list_properties.return_value = [MagicMock(name="threshold")]
        gp.pipeline.get_by_name.side_effect = lambda name: (
            mock_element if name == "classify" else None
        )

        gp._set_section_properties(["parameters"], ["parameters", "properties"])

        gp.pipeline.get_by_name.assert_called_with("classify")


# ---------------------------------------------------------------------------
# Invariant 2 — Object-form binding uses the explicit 'property' field
# ---------------------------------------------------------------------------

class TestObjectFormBinding:
    """Invariant 2: element.property overrides the parameter key."""

    def test_explicit_property_name_used(self, mocker):
        config_params = {
            "interval": {
                "element": {
                    "name": "detection",
                    "property": "inference-interval",
                },
                "type": "integer",
                "default": 1,
            }
        }
        request_params = {"interval": 2}
        gp = _make_pipeline(mocker, request_params, config_params)

        mock_element = MagicMock()
        mock_element.list_properties.return_value = [
            MagicMock(name="inference-interval")
        ]
        gp.pipeline.get_by_name.return_value = mock_element

        gp._set_section_properties(["parameters"], ["parameters", "properties"])

        mock_element.set_property.assert_called_once_with("inference-interval", 2)

    def test_get_element_property_returns_name_and_property(self, mocker):
        mocker.patch("gi.repository.Gst.init")
        from src.server.gstreamer_pipeline import GStreamerPipeline

        gp = GStreamerPipeline.__new__(GStreamerPipeline)
        element_spec = {"name": "detection", "property": "inference-interval"}
        result = gp._get_element_property(element_spec, "interval")
        assert result == ("detection", "inference-interval", None)

    def test_get_element_property_defaults_property_to_none_when_absent(self, mocker):
        mocker.patch("gi.repository.Gst.init")
        from src.server.gstreamer_pipeline import GStreamerPipeline

        gp = GStreamerPipeline.__new__(GStreamerPipeline)
        element_spec = {"name": "detection"}
        result = gp._get_element_property(element_spec, "my-param")
        assert result == ("detection", None, None)


# ---------------------------------------------------------------------------
# Invariant 3 — Array-form binding applies to all listed elements
# ---------------------------------------------------------------------------

class TestArrayFormBinding:
    """Invariant 3: array element → every listed element receives the value."""

    def test_value_set_on_all_listed_elements(self, mocker):
        config_params = {
            "interval": {
                "element": [
                    {"name": "detection",     "property": "inference-interval"},
                    {"name": "classification","property": "inference-interval"},
                ],
                "type": "integer",
                "default": 1,
            }
        }
        request_params = {"interval": 3}
        gp = _make_pipeline(mocker, request_params, config_params)

        mock_det = MagicMock()
        mock_det.list_properties.return_value = [MagicMock(name="inference-interval")]
        mock_cls = MagicMock()
        mock_cls.list_properties.return_value = [MagicMock(name="inference-interval")]

        def get_by_name(name):
            return {"detection": mock_det, "classification": mock_cls}.get(name)

        gp.pipeline.get_by_name.side_effect = get_by_name

        gp._set_section_properties(["parameters"], ["parameters", "properties"])

        mock_det.set_property.assert_called_once_with("inference-interval", 3)
        mock_cls.set_property.assert_called_once_with("inference-interval", 3)

    def test_array_with_three_elements(self, mocker):
        config_params = {
            "device": {
                "element": [
                    {"name": "a", "property": "device"},
                    {"name": "b", "property": "device"},
                    {"name": "c", "property": "device"},
                ],
                "type": "string",
            }
        }
        request_params = {"device": "GPU"}
        gp = _make_pipeline(mocker, request_params, config_params)

        elements = {n: MagicMock() for n in ("a", "b", "c")}
        for m in elements.values():
            m.list_properties.return_value = [MagicMock(name="device")]
        gp.pipeline.get_by_name.side_effect = lambda n: elements.get(n)

        gp._set_section_properties(["parameters"], ["parameters", "properties"])

        for name, mock_el in elements.items():
            mock_el.set_property.assert_called_once_with("device", "GPU")


# ---------------------------------------------------------------------------
# Invariant 4 — format=element-properties fans out key/value pairs
# ---------------------------------------------------------------------------

class TestElementPropertiesFormat:
    """Invariant 4: each key in the value dict becomes a separate set_property call."""

    def test_each_key_value_applied_individually(self, mocker):
        config_params = {
            "source-properties": {
                "type": "object",
                "element": {
                    "name": "source",
                    "format": "element-properties",
                },
            }
        }
        request_params = {
            "source-properties": {
                "uri": "rtsp://camera/stream",
                "latency": 100,
            }
        }
        gp = _make_pipeline(mocker, request_params, config_params)

        mock_source = MagicMock()
        mock_source.list_properties.return_value = [
            MagicMock(name="uri"),
            MagicMock(name="latency"),
        ]
        gp.pipeline.get_by_name.return_value = mock_source

        gp._set_section_properties(["parameters"], ["parameters", "properties"])

        assert mock_source.set_property.call_count == 2
        calls = {c.args[0]: c.args[1] for c in mock_source.set_property.call_args_list}
        assert calls["uri"] == "rtsp://camera/stream"
        assert calls["latency"] == 100

    def test_single_key_in_element_properties_value(self, mocker):
        config_params = {
            "props": {
                "type": "object",
                "element": {"name": "detect", "format": "element-properties"},
            }
        }
        request_params = {"props": {"threshold": 0.5}}
        gp = _make_pipeline(mocker, request_params, config_params)

        mock_el = MagicMock()
        mock_el.list_properties.return_value = [MagicMock(name="threshold")]
        gp.pipeline.get_by_name.return_value = mock_el

        gp._set_section_properties(["parameters"], ["parameters", "properties"])

        mock_el.set_property.assert_called_once_with("threshold", 0.5)


# ---------------------------------------------------------------------------
# Invariant 5 — format=json serializes value before set_property
# ---------------------------------------------------------------------------

class TestJsonFormat:
    """Invariant 5: format=json → json.dumps applied before set_property."""

    def test_dict_value_is_json_serialized(self, mocker):
        mocker.patch("gi.repository.Gst.init")
        from src.server.gstreamer_pipeline import GStreamerPipeline

        gp = GStreamerPipeline.__new__(GStreamerPipeline)
        gp._logger = MagicMock()
        gp._unset_properties = []

        mock_element = MagicMock()
        prop_name = MagicMock(name="tags")
        mock_element.list_properties.return_value = [prop_name]

        gp._set_element_property(
            mock_element, "tags", {"location": "building-1"}, format_type="json"
        )

        expected = json.dumps({"location": "building-1"})
        mock_element.set_property.assert_called_once_with("tags", expected)

    def test_list_value_is_json_serialized(self, mocker):
        mocker.patch("gi.repository.Gst.init")
        from src.server.gstreamer_pipeline import GStreamerPipeline

        gp = GStreamerPipeline.__new__(GStreamerPipeline)
        gp._logger = MagicMock()
        gp._unset_properties = []

        mock_element = MagicMock()
        prop_name = MagicMock(name="labels")
        mock_element.list_properties.return_value = [prop_name]

        gp._set_element_property(
            mock_element, "labels", ["cat", "dog"], format_type="json"
        )

        mock_element.set_property.assert_called_once_with("labels", '["cat", "dog"]')

    def test_no_format_passes_value_directly(self, mocker):
        mocker.patch("gi.repository.Gst.init")
        from src.server.gstreamer_pipeline import GStreamerPipeline

        gp = GStreamerPipeline.__new__(GStreamerPipeline)
        gp._logger = MagicMock()
        gp._unset_properties = []

        mock_element = MagicMock()
        prop_name = MagicMock(name="threshold")
        mock_element.list_properties.return_value = [prop_name]

        gp._set_element_property(mock_element, "threshold", 0.75)

        mock_element.set_property.assert_called_once_with("threshold", 0.75)


# ---------------------------------------------------------------------------
# Invariant 6 — Unresolved element name: logged, no exception raised
# ---------------------------------------------------------------------------

class TestUnresolvedElementBehavior:
    """Invariant 6: missing element → DEBUG log, no exception, pipeline continues."""

    def test_unresolved_element_does_not_raise(self, mocker):
        config_params = {
            "inference-interval": {
                "element": "nonexistent",
                "type": "integer",
                "default": 1,
            }
        }
        request_params = {"inference-interval": 1}
        gp = _make_pipeline(mocker, request_params, config_params)
        gp.pipeline.get_by_name.return_value = None  # element not in pipeline

        # Must not raise.
        gp._set_section_properties(["parameters"], ["parameters", "properties"])

    def test_unresolved_element_emits_debug_log(self, mocker):
        config_params = {
            "threshold": {
                "element": "ghost-element",
                "type": "number",
            }
        }
        request_params = {"threshold": 0.5}
        gp = _make_pipeline(mocker, request_params, config_params)
        gp.pipeline.get_by_name.return_value = None

        gp._set_section_properties(["parameters"], ["parameters", "properties"])

        gp._logger.debug.assert_called()

    def test_unresolved_property_does_not_raise(self, mocker):
        """Element exists but property is not in its list → log, no raise."""
        mocker.patch("gi.repository.Gst.init")
        from src.server.gstreamer_pipeline import GStreamerPipeline

        gp = GStreamerPipeline.__new__(GStreamerPipeline)
        gp._logger = MagicMock()
        gp._unset_properties = []

        mock_element = MagicMock()
        mock_element.list_properties.return_value = []  # property not present

        # Must not raise.
        gp._set_element_property(mock_element, "unknown-prop", 42)

        mock_element.set_property.assert_not_called()
        assert len(gp._unset_properties) == 1

    def test_unresolved_property_appended_to_unset_list(self, mocker):
        mocker.patch("gi.repository.Gst.init")
        from src.server.gstreamer_pipeline import GStreamerPipeline

        gp = GStreamerPipeline.__new__(GStreamerPipeline)
        gp._logger = MagicMock()
        gp._unset_properties = []

        mock_element = MagicMock()
        mock_element.__gtype__ = MagicMock()
        mock_element.__gtype__.name = "GstFakeDetect"
        mock_element.list_properties.return_value = []

        gp._set_element_property(mock_element, "no-such-prop", "value")

        assert gp._unset_properties == [["GstFakeDetect", "no-such-prop", "value"]]
