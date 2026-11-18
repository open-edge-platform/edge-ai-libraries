#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Probe motion ROIs from gvaopticalflow track-motion-rois (gvatrack prior).

Usage::

  export GST_PLUGIN_PATH=.../integrations/gvaopticalflow/build
  export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
  python3 examples/flow_track_consumer.py
"""

from __future__ import annotations

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
from gi.repository import Gst, GstVideo  # noqa: E402

Gst.init(None)


def count_rois(buf: Gst.Buffer) -> int:
    n = 0
    # Prefer id-based getter when available (walk ids until None).
    try:
        idx = 0
        while True:
            meta = GstVideo.buffer_get_video_region_of_interest_meta_id(buf, idx)
            if meta is None:
                break
            n += 1
            idx += 1
            if idx > 10000:
                break
        if n:
            return n
    except Exception:
        pass

    # Fallback: foreach_meta filtered by ROI API GType.
    try:
        api = GstVideo.video_region_of_interest_meta_api_get_type()

        def _cb(_buffer, meta, _user):
            nonlocal n
            if meta.info.api == api:
                n += 1
            return True

        buf.foreach_meta(_cb)
    except Exception:
        return 0
    return n


def on_buffer(_pad, info, stats):
    buf = info.get_buffer()
    if buf is None:
        return Gst.PadProbeReturn.OK
    stats["frames"] += 1
    n = count_rois(buf)
    if n:
        stats["with_roi"] += 1
        stats["roi_total"] += n
    return Gst.PadProbeReturn.OK


def main() -> int:
    stats = {"frames": 0, "with_roi": 0, "roi_total": 0}
    pipe = Gst.parse_launch(
        "videotestsrc num-buffers=40 pattern=ball ! "
        "video/x-raw,format=NV12,width=320,height=240,framerate=30/1 ! "
        "gvaopticalflow preset=fast device=GPU "
        "track-motion-rois=true roi-block=16 roi-mag-threshold=0.1 name=of ! "
        "identity name=id ! fakesink sync=false"
    )
    identity = pipe.get_by_name("id")
    sinkpad = identity.get_static_pad("sink")
    sinkpad.add_probe(Gst.PadProbeType.BUFFER, on_buffer, stats)

    pipe.set_state(Gst.State.PLAYING)
    bus = pipe.get_bus()
    msg = bus.timed_pop_filtered(Gst.CLOCK_TIME_NONE, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    pipe.set_state(Gst.State.NULL)

    if msg and msg.type == Gst.MessageType.ERROR:
        err, dbg = msg.parse_error()
        print("ERROR:", err, dbg)
        return 1

    print(
        f"frames={stats['frames']} buffers_with_motion_roi={stats['with_roi']} "
        f"roi_total={stats['roi_total']}"
    )
    print(
        "Contract: roi_type=optical-flow-motion + detection{confidence,label_id,...} "
        "+ optional object_id{id}"
    )
    print(
        "Full DL Streamer: ... ! gvaopticalflow emit-motion-rois=true ! "
        "gvatrack tracking-type=zero-term-imageless ! ..."
    )
    return 0 if stats["with_roi"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
