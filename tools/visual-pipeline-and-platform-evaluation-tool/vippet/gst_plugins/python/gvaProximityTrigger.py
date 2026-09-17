# SPDX-License-Identifier: Apache-2.0
#
# Mock stand-in for the ``gvaproximitytrigger_py`` custom DLStreamer element
# introduced in https://github.com/open-edge-platform/dlstreamer/pull/978.
#
# The real element inspects GstAnalytics detection metadata and drops
# frames unless two object classes stay in proximity for N consecutive
# frames. Until ViPPET adopts the upstream implementation, this mock
# accepts the same properties and simply forwards every buffer so that
# pipelines referencing ``gvaproximitytrigger_py`` are parseable and
# runnable.

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
from gi.repository import Gst, GstBase, GObject  # noqa: E402  pylint: disable=no-name-in-module,wrong-import-position

Gst.init(None)


class ProximityTrigger(GstBase.BaseTransform):
    """Passthrough placeholder for the upstream proximity-trigger element."""

    __gstmetadata__ = (
        "GVA Proximity Trigger (ViPPET mock)",
        "Transform",
        "Passthrough placeholder for the upstream gvaproximitytrigger_py element",
        "ViPPET",
    )

    __gsttemplates__ = (
        Gst.PadTemplate.new(
            "src", Gst.PadDirection.SRC, Gst.PadPresence.ALWAYS, Gst.Caps.new_any()
        ),
        Gst.PadTemplate.new(
            "sink", Gst.PadDirection.SINK, Gst.PadPresence.ALWAYS, Gst.Caps.new_any()
        ),
    )

    _class_a = "person"
    _class_b = "bicycle"
    _distance = 30
    _frames = 10

    @GObject.Property(type=str, nick="class-a", blurb="First object class to monitor")
    def class_a(self):
        return self._class_a

    @class_a.setter
    def class_a(self, value):
        self._class_a = value

    @GObject.Property(type=str, nick="class-b", blurb="Second object class to monitor")
    def class_b(self):
        return self._class_b

    @class_b.setter
    def class_b(self, value):
        self._class_b = value

    @GObject.Property(
        type=int,
        nick="distance",
        blurb="Maximum center-to-center distance in pixels to trigger",
        minimum=1,
        maximum=10000,
        default=30,
    )
    def distance(self):
        return self._distance

    @distance.setter
    def distance(self, value):
        self._distance = value

    @GObject.Property(
        type=int,
        nick="frames",
        blurb="Number of consecutive frames proximity must hold before trigger",
        minimum=1,
        maximum=10000,
        default=10,
    )
    def frames(self):
        return self._frames

    @frames.setter
    def frames(self, value):
        self._frames = value

    def do_transform_ip(self, _buffer):
        # Mock: forward every buffer. The real element decides whether to
        # drop or pass frames based on detection metadata.
        return Gst.FlowReturn.OK


GObject.type_register(ProximityTrigger)
__gstelementfactory__ = ("gvaproximitytrigger_py", Gst.Rank.NONE, ProximityTrigger)
