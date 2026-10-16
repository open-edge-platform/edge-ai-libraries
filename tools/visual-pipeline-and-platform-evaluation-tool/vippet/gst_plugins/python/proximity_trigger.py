# SPDX-License-Identifier: Apache-2.0

"""Custom GStreamer element: Proximity Trigger for VLM inference.

Monitors object detection metadata for proximity between two object classes.
When objects of ``class-a`` and ``class-b`` are within ``distance`` pixels
(center-to-center) for ``frames`` consecutive frames, passes exactly one frame
downstream so a heavy element (e.g. a VLM) can process it. All other frames
are dropped, which keeps the downstream branch idle whenever proximity does
not hold. When the downstream sink pad cannot accept a new buffer (e.g. its
queue is full and ``leaky=downstream`` is configured upstream), the buffer
that was about to be forwarded is naturally dropped by the queue as well.
"""

import math

import gi  # pyright: ignore[reportMissingImports]

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")
gi.require_version("GstAnalytics", "1.0")
from gi.repository import (  # noqa: E402 # pyright: ignore[reportMissingImports]
    GLib,
    GObject,
    Gst,
    GstAnalytics,
    GstBase,
)

Gst.init_python()

# BaseTransform returns CUSTOM_SUCCESS from transform_ip to indicate that the
# buffer must be dropped without treating it as an error.
GST_BASE_TRANSFORM_FLOW_DROPPED = Gst.FlowReturn.CUSTOM_SUCCESS

# Name of the element-message structure ViPPET's gst_runner forwards to the
# parent process as a live pipeline event (shown under the live preview).
PIPELINE_EVENT_STRUCTURE = "vippet-event"


class ProximityTrigger(GstBase.BaseTransform):
    """Drop every frame unless two object classes are close for N frames."""

    __gstmetadata__ = (
        "GVA Proximity Trigger",
        "Transform",
        "Passes one frame when objects of two classes are in proximity for "
        "N consecutive frames",
        "Intel DLStreamer",
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

    @GObject.Property(
        type=str,
        nick="class-a",
        blurb="First object class to monitor",
        default="person",
    )
    def class_a(self):
        return self._class_a

    @class_a.setter
    def class_a(self, value):
        self._class_a = value

    @GObject.Property(
        type=str,
        nick="class-b",
        blurb="Second object class to monitor",
        default="bicycle",
    )
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

    def __init__(self):
        super().__init__()
        self._consecutive_count = 0
        self._last_distance: float | None = None

    @staticmethod
    def _get_center(x: float, y: float, w: float, h: float) -> tuple[float, float]:
        return (x + w / 2.0, y + h / 2.0)

    def _check_proximity(self, rmeta) -> bool:
        """Return True if any class-a object is within distance of a class-b object."""
        if not self._class_a or not self._class_b:
            return False

        class_a_centers: list[tuple[float, float]] = []
        class_b_centers: list[tuple[float, float]] = []

        for mtd in rmeta:
            if not isinstance(mtd, GstAnalytics.ODMtd):
                continue
            label = GLib.quark_to_string(mtd.get_obj_type())
            if label is None:
                continue
            success, x, y, w, h, _ = mtd.get_location()
            if not success:
                continue
            center = self._get_center(x, y, w, h)

            if label == self._class_a:
                class_a_centers.append(center)
            elif label == self._class_b:
                class_b_centers.append(center)

        self._last_distance = min(
            (
                math.hypot(ca[0] - cb[0], ca[1] - cb[1])
                for ca in class_a_centers
                for cb in class_b_centers
            ),
            default=None,
        )
        return self._last_distance is not None and self._last_distance <= self._distance

    def _post_trigger_event(self, pts_sec: float) -> None:
        """Post an element message describing the fired trigger on the bus."""
        closest = (
            f"{self._last_distance:.0f} px \u2264 "
            if self._last_distance is not None
            else "\u2264 "
        )
        text = (
            f"Trigger fired at {pts_sec:.2f}s: {self._class_a} near {self._class_b} "
            f"({closest}{self._distance} px) for {self._frames} consecutive frames"
        )
        structure = Gst.Structure.new_empty(PIPELINE_EVENT_STRUCTURE)
        structure.set_value("source", "proximity-trigger")
        structure.set_value("text", text)
        structure.set_value("pts-seconds", float(pts_sec))
        self.post_message(Gst.Message.new_element(self, structure))

    def do_transform_ip(self, buffer):
        rmeta = GstAnalytics.buffer_get_analytics_relation_meta(buffer)
        if not rmeta:
            self._consecutive_count = 0
            return GST_BASE_TRANSFORM_FLOW_DROPPED

        if self._check_proximity(rmeta):
            self._consecutive_count += 1
        else:
            self._consecutive_count = 0
            return GST_BASE_TRANSFORM_FLOW_DROPPED

        if self._consecutive_count >= self._frames:
            self._consecutive_count = 0
            pts_sec = (
                buffer.pts / Gst.SECOND if buffer.pts != Gst.CLOCK_TIME_NONE else 0
            )
            Gst.info(
                f"[proximity] Trigger fired at {pts_sec:.2f}s - "
                f"{self._class_a} near {self._class_b} for {self._frames} frames"
            )
            self._post_trigger_event(pts_sec)
            return Gst.FlowReturn.OK

        return GST_BASE_TRANSFORM_FLOW_DROPPED


GObject.type_register(ProximityTrigger)
__gstelementfactory__ = ("gvaproximitytrigger_py", Gst.Rank.NONE, ProximityTrigger)
