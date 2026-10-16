# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the ``gvaproximitytrigger_py`` custom GStreamer element."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# The plugin lives under ``vippet/gst_plugins/python/`` and is loaded at
# runtime by the GStreamer Python plugin loader, so it is not on sys.path
# by default. Prepend it here so we can import it directly for testing.
_PLUGIN_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        os.pardir,
        os.pardir,
        "gst_plugins",
        "python",
    )
)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

try:
    import gi  # type: ignore[import]

    gi.require_version("Gst", "1.0")
    gi.require_version("GstBase", "1.0")
    gi.require_version("GstAnalytics", "1.0")
    from gi.repository import Gst, GstAnalytics  # type: ignore[import]  # noqa: E402

    # ``proximity_trigger`` calls ``Gst.init_python()`` at import time, which
    # requires GStreamer to be initialized first (normally done by the Python
    # plugin loader). Do it explicitly here so the module can be imported
    # standalone from tests.
    Gst.init(None)

    import proximity_trigger  # noqa: E402

    _GST_AVAILABLE = True
except (ImportError, ValueError):
    _GST_AVAILABLE = False


def _make_odmtd(
    label: str, x: float, y: float, w: float, h: float, success: bool = True
):
    """Create a MagicMock that passes ``isinstance(_, GstAnalytics.ODMtd)``.

    ``get_obj_type()`` returns the label directly (a stand-in for the quark),
    which pairs with a patched ``GLib.quark_to_string`` that acts as identity.
    """
    m = MagicMock(spec=GstAnalytics.ODMtd)
    m.get_obj_type.return_value = label
    m.get_location.return_value = (success, x, y, w, h, 0.0)
    return m


@unittest.skipUnless(_GST_AVAILABLE, "GStreamer + GstAnalytics bindings required")
class TestGetCenter(unittest.TestCase):
    """Smoke tests for the ``_get_center`` bounding-box helper."""

    def test_returns_center_of_bounding_box(self):
        cx, cy = proximity_trigger.ProximityTrigger._get_center(10.0, 20.0, 40.0, 60.0)
        self.assertAlmostEqual(cx, 30.0)
        self.assertAlmostEqual(cy, 50.0)

    def test_zero_sized_box_returns_top_left(self):
        cx, cy = proximity_trigger.ProximityTrigger._get_center(5.0, 7.0, 0.0, 0.0)
        self.assertAlmostEqual(cx, 5.0)
        self.assertAlmostEqual(cy, 7.0)


@unittest.skipUnless(_GST_AVAILABLE, "GStreamer + GstAnalytics bindings required")
class TestCheckProximity(unittest.TestCase):
    """Tests for the core proximity-detection logic."""

    def setUp(self):
        self.trigger = proximity_trigger.ProximityTrigger()
        self.trigger._class_a = "person"
        self.trigger._class_b = "bicycle"
        self.trigger._distance = 30

    def _run(self, metas):
        # In tests ``get_obj_type()`` returns the label string directly, so
        # ``quark_to_string`` can be treated as identity.
        with patch.object(
            proximity_trigger.GLib,
            "quark_to_string",
            side_effect=lambda q: q,
        ):
            return self.trigger._check_proximity(metas)

    def test_returns_false_when_no_metadata(self):
        self.assertFalse(self._run([]))

    def test_returns_false_when_objects_are_far_apart(self):
        metas = [
            _make_odmtd("person", 0.0, 0.0, 20.0, 20.0),
            _make_odmtd("bicycle", 500.0, 500.0, 20.0, 20.0),
        ]
        self.assertFalse(self._run(metas))

    def test_returns_true_when_objects_are_within_distance(self):
        # Centers (110, 110) and (120, 120) → distance ≈ 14.14 px ≤ 30
        metas = [
            _make_odmtd("person", 100.0, 100.0, 20.0, 20.0),
            _make_odmtd("bicycle", 110.0, 110.0, 20.0, 20.0),
        ]
        self.assertTrue(self._run(metas))

    def test_returns_false_when_only_class_a_present(self):
        metas = [
            _make_odmtd("person", 0.0, 0.0, 20.0, 20.0),
            _make_odmtd("person", 5.0, 5.0, 20.0, 20.0),
        ]
        self.assertFalse(self._run(metas))

    def test_returns_false_when_classes_not_configured(self):
        self.trigger._class_a = ""
        self.trigger._class_b = ""
        metas = [
            _make_odmtd("person", 0.0, 0.0, 20.0, 20.0),
            _make_odmtd("bicycle", 5.0, 5.0, 20.0, 20.0),
        ]
        self.assertFalse(self._run(metas))

    def test_skips_meta_with_failed_get_location(self):
        metas = [
            _make_odmtd("person", 100.0, 100.0, 20.0, 20.0),
            _make_odmtd("bicycle", 110.0, 110.0, 20.0, 20.0, success=False),
        ]
        self.assertFalse(self._run(metas))


@unittest.skipUnless(_GST_AVAILABLE, "GStreamer + GstAnalytics bindings required")
class TestDoTransformIp(unittest.TestCase):
    """Tests for the frame-gating logic in ``do_transform_ip``."""

    def setUp(self):
        self.trigger = proximity_trigger.ProximityTrigger()
        self.trigger._class_a = "person"
        self.trigger._class_b = "bicycle"
        self.trigger._distance = 30
        self.trigger._frames = 3
        self._dropped = proximity_trigger.GST_BASE_TRANSFORM_FLOW_DROPPED

    def _run(self, has_rmeta: bool, proximity: bool):
        rmeta = MagicMock() if has_rmeta else None
        with (
            patch.object(
                proximity_trigger.GstAnalytics,
                "buffer_get_analytics_relation_meta",
                return_value=rmeta,
            ),
            patch.object(self.trigger, "_check_proximity", return_value=proximity),
        ):
            buffer = MagicMock()
            buffer.pts = Gst.CLOCK_TIME_NONE
            return self.trigger.do_transform_ip(buffer)

    def test_drops_and_resets_counter_when_no_metadata(self):
        self.trigger._consecutive_count = 2
        result = self._run(has_rmeta=False, proximity=False)
        self.assertEqual(result, self._dropped)
        self.assertEqual(self.trigger._consecutive_count, 0)

    def test_drops_and_resets_counter_when_no_proximity(self):
        self.trigger._consecutive_count = 2
        result = self._run(has_rmeta=True, proximity=False)
        self.assertEqual(result, self._dropped)
        self.assertEqual(self.trigger._consecutive_count, 0)

    def test_drops_but_increments_counter_below_threshold(self):
        self.trigger._consecutive_count = 0
        result = self._run(has_rmeta=True, proximity=True)
        self.assertEqual(result, self._dropped)
        self.assertEqual(self.trigger._consecutive_count, 1)

    def test_passes_frame_and_resets_counter_at_threshold(self):
        # After (_frames - 1) proximity hits we are one below the threshold;
        # the next proximity frame must be forwarded and the counter reset.
        self.trigger._consecutive_count = self.trigger._frames - 1
        result = self._run(has_rmeta=True, proximity=True)
        self.assertEqual(result, Gst.FlowReturn.OK)
        self.assertEqual(self.trigger._consecutive_count, 0)

    def test_posts_event_message_when_trigger_fires(self):
        self.trigger._consecutive_count = self.trigger._frames - 1
        self.trigger._last_distance = 12.3
        with patch.object(self.trigger, "post_message") as post_message:
            self._run(has_rmeta=True, proximity=True)

        post_message.assert_called_once()
        structure = post_message.call_args[0][0].get_structure()
        self.assertEqual(
            structure.get_name(), proximity_trigger.PIPELINE_EVENT_STRUCTURE
        )
        self.assertEqual(structure.get_value("source"), "proximity-trigger")
        self.assertIn("person near bicycle", structure.get_value("text"))
        self.assertIn("12 px", structure.get_value("text"))
        self.assertIn("3 consecutive frames", structure.get_value("text"))

    def test_does_not_post_event_below_threshold(self):
        with patch.object(self.trigger, "post_message") as post_message:
            self._run(has_rmeta=True, proximity=True)
        post_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
