#!/usr/bin/env python3
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Full consumer-chain smoke without DL Streamer plugins installed.

Roles covered (see docs/consumers.md):
  * gvaopticalflow track-motion-rois  — detection-shaped ROIs + object_id
    (gvatrack zero-term-imageless prior)
  * watermark probe                   — draw ROI boxes + ids on NV12 luma
    (gvawatermark stand-in)
  * gvamotiondetect                   — complementary frame-diff element;
    intentionally not chained (prefer flow ROIs)

When real DL Streamer plugins are present, use::

  ... ! gvaopticalflow emit-motion-rois=true ! \\
    gvatrack tracking-type=zero-term-imageless ! gvawatermark ! ...

Usage::

  export GST_PLUGIN_PATH=.../integrations/gvaopticalflow/build
  export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
  python3 examples/flow_full_chain.py [--out /tmp/flow_chain.nv12]
"""

from __future__ import annotations

import argparse
import sys

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
from gi.repository import Gst, GstVideo  # noqa: E402

Gst.init(None)


def _iter_rois(buf: Gst.Buffer):
    try:
        idx = 0
        while idx < 10000:
            meta = GstVideo.buffer_get_video_region_of_interest_meta_id(buf, idx)
            if meta is None:
                break
            yield meta
            idx += 1
    except Exception:
        return


def _struct_get_int(st, key):
    for meth in ("get_int", "get_value"):
        if not hasattr(st, meth):
            continue
        try:
            out = getattr(st, meth)(key)
            if isinstance(out, tuple):
                ok, val = out
                return int(val) if ok else None
            return int(out)
        except Exception:
            continue
    return None


def _struct_get_double(st, key):
    for meth in ("get_double", "get_value"):
        if not hasattr(st, meth):
            continue
        try:
            out = getattr(st, meth)(key)
            if isinstance(out, tuple):
                ok, val = out
                return float(val) if ok else None
            return float(out)
        except Exception:
            continue
    return None


def _roi_params(meta) -> tuple[int | None, float]:
    """Return (object_id or None, confidence)."""
    track_id = None
    conf = 0.0
    try:
        oid = meta.get_param("object_id")
        det = meta.get_param("detection")
    except Exception:
        oid, det = None, None
    if oid is not None:
        val = _struct_get_int(oid, "id")
        if val is not None:
            track_id = val
    if det is not None:
        val = _struct_get_double(det, "confidence")
        if val is not None:
            conf = val
    return track_id, conf


def _draw_box_nv12(data: bytearray, w: int, h: int, x0: int, y0: int, x1: int, y1: int) -> None:
    """White rectangle on the Y plane (simple gvawatermark stand-in)."""
    x0 = max(0, min(w - 1, x0))
    x1 = max(0, min(w - 1, x1))
    y0 = max(0, min(h - 1, y0))
    y1 = max(0, min(h - 1, y1))
    if x1 <= x0 or y1 <= y0:
        return
    for x in range(x0, x1 + 1):
        data[y0 * w + x] = 255
        data[y1 * w + x] = 255
    for y in range(y0, y1 + 1):
        data[y * w + x0] = 255
        data[y * w + x1] = 255


def on_buffer(_pad, info, state):
    buf = info.get_buffer()
    if buf is None:
        return Gst.PadProbeReturn.OK
    state["frames"] += 1

    rois = list(_iter_rois(buf))
    if not rois:
        return Gst.PadProbeReturn.OK

    state["with_roi"] += 1
    state["roi_total"] += len(rois)
    ids = set()
    for meta in rois:
        tid, conf = _roi_params(meta)
        if tid is not None:
            ids.add(tid)
        state["conf_sum"] += conf

    if ids:
        state["tracked_frames"] += 1
        state["unique_ids"] |= ids

    # Watermark: copy Y plane, stroke boxes (gvawatermark stand-in).
    w, h = state["width"], state["height"]
    try:
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if ok:
            y_bytes = w * h
            y_plane = bytearray(mapinfo.data[:y_bytes])
            buf.unmap(mapinfo)
            for meta in rois:
                _draw_box_nv12(y_plane, w, h, int(meta.x), int(meta.y), int(meta.x + meta.w),
                               int(meta.y + meta.h))
            state["watermarked"] += 1
            if state["out_fp"] is not None and state["watermarked"] <= 3:
                state["out_fp"].write(y_plane)
    except Exception as ex:
        state["wm_errors"] += 1
        state["last_wm_error"] = str(ex)

    return Gst.PadProbeReturn.OK


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="Optional raw Y dumps (first 3 watermarked frames)")
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=240)
    args = ap.parse_args()

    out_fp = open(args.out, "wb") if args.out else None
    state = {
        "frames": 0,
        "with_roi": 0,
        "roi_total": 0,
        "tracked_frames": 0,
        "unique_ids": set(),
        "conf_sum": 0.0,
        "watermarked": 0,
        "wm_errors": 0,
        "last_wm_error": "",
        "width": args.width,
        "height": args.height,
        "out_fp": out_fp,
    }

    pipe = Gst.parse_launch(
        f"videotestsrc num-buffers={args.frames} pattern=ball ! "
        f"video/x-raw,format=NV12,width={args.width},height={args.height},framerate=30/1 ! "
        "gvaopticalflow preset=fast device=GPU "
        "track-motion-rois=true roi-block=16 roi-mag-threshold=0.1 name=of ! "
        "identity name=id ! fakesink sync=false"
    )
    identity = pipe.get_by_name("id")
    identity.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, on_buffer, state)

    pipe.set_state(Gst.State.PLAYING)
    bus = pipe.get_bus()
    msg = bus.timed_pop_filtered(Gst.CLOCK_TIME_NONE, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    pipe.set_state(Gst.State.NULL)
    if out_fp:
        out_fp.close()

    if msg and msg.type == Gst.MessageType.ERROR:
        err, dbg = msg.parse_error()
        print("ERROR:", err, dbg, file=sys.stderr)
        return 1

    mean_conf = (state["conf_sum"] / state["roi_total"]) if state["roi_total"] else 0.0
    print(
        f"frames={state['frames']} with_roi={state['with_roi']} roi_total={state['roi_total']} "
        f"tracked_frames={state['tracked_frames']} unique_object_ids={len(state['unique_ids'])} "
        f"mean_conf={mean_conf:.3f} watermarked={state['watermarked']}"
    )
    print("chain: gvaopticalflow(track-motion-rois) -> gvatrack-prior(object_id) -> watermark-draw")
    print("gvamotiondetect: not chained (complementary frame-diff; prefer flow ROIs)")
    if state["wm_errors"]:
        print(f"watermark_errors={state['wm_errors']} last={state['last_wm_error']}", file=sys.stderr)

    ok = (
        state["with_roi"] > 0
        and state["tracked_frames"] > 0
        and len(state["unique_ids"]) > 0
        and state["watermarked"] > 0
    )
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
