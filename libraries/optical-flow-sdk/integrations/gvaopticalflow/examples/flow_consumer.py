#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Minimal consumer for gvaopticalflow GstGVATensorMeta (gvapython-style).

Usage (after building the standalone plugin)::

  export GST_PLUGIN_PATH=.../gvaopticalflow-standalone/build
  export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
  gst-launch-1.0 videotestsrc num-buffers=10 ! video/x-raw,format=NV12,width=320,height=240 ! \\
    gvaopticalflow preset=fast device=GPU ! identity name=id silent=true ! fakesink

Or run this script directly (embeds the pipeline).
"""

from __future__ import annotations

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402

Gst.init(None)

# Matches vendor/gva_tensor_meta.h API name.
GVA_TENSOR_META_API = "GstGVATensorMetaAPI"


def _meta_api_type():
    # Registered when the plugin loads.
    return Gst.Meta.get_info(GVA_TENSOR_META_API)  # may be None before plugin load


def on_buffer(_pad, info, stats):
    buf = info.get_buffer()
    if buf is None:
        return Gst.PadProbeReturn.OK
    stats["frames"] += 1
    # Walk metas via C API exposed on Buffer in newer PyGObject; fall back to count.
    try:
        meta = buf.get_meta(GVA_TENSOR_META_API)
        if meta is not None:
            stats["with_meta"] += 1
    except Exception:
        # Buffer.get_meta may take a GType; try foreach via list_metas if present.
        if hasattr(buf, "get_n_meta"):
            n = buf.get_n_meta(Gst.Meta.get_info(GVA_TENSOR_META_API).api) if Gst.Meta.get_info(GVA_TENSOR_META_API) else 0
            if n:
                stats["with_meta"] += 1
    return Gst.PadProbeReturn.OK


def main() -> int:
    stats = {"frames": 0, "with_meta": 0}
    pipe = Gst.parse_launch(
        "videotestsrc num-buffers=12 pattern=ball ! "
        "video/x-raw,format=NV12,width=320,height=240,framerate=30/1 ! "
        "gvaopticalflow preset=fast device=GPU name=of ! "
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

    print(f"frames={stats['frames']} buffers_with_gva_tensor_meta={stats['with_meta']}")
    print("Consumer contract: model_name=optical-flow-sdk layer_name=flow dims=[1,H,W,2] FP32 NHWC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
