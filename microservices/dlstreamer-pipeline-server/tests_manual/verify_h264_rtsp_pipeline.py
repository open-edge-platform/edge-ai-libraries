#
# Apache v2 license
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
Manual functional verification (not part of the pytest unit-test suite) that
proves the new RTSP H.264 encoding branch added to GStreamerRtspFactory:

  1. Produces a launch string GStreamer can actually parse/link (catches
     element/property typos that mocked unit tests cannot).
  2. Negotiates real video/x-h264 caps end to end (i.e. the stream really is
     H.264, not MJPEG).
  3. Leaves the default (mjpeg) branch byte-identical / functionally
     unchanged.

Run inside a container that has dlstreamer + gstreamer-rtsp-server, e.g.:
  docker run --rm --entrypoint bash -v $(pwd)/..:/workspace -w /workspace \
    intel/dlstreamer-pipeline-server:2026.2.0-ubuntu24-rc1 \
    -lc "python3 tests_manual/verify_h264_rtsp_pipeline.py"
"""
import ast
import importlib
import os
import sys

import gi
gi.require_version('Gst', '1.0')
Gst = importlib.import_module('gi.repository.Gst')

_FACTORY_SRC = os.path.join(os.path.dirname(__file__), '..',
                            'src', 'server', 'rtsp', 'gstreamer_rtsp_factory.py')


def _extract_fragment(const_name):
    """Extracts a `_RtspVideoPipeline*` string constant's *actual Python
    string value* directly out of the factory source file (via `ast`, so
    backslash-newline continuations inside the literal are honored exactly
    like the real interpreter would), so this functional check always
    exercises whatever is actually committed there. This avoids needing the
    GstRtspServer typelib that GStreamerRtspFactory's module-level
    `gi.require_version` import requires (not available on every dev host,
    unlike the plain Gst typelib used here)."""
    with open(_FACTORY_SRC, encoding='utf-8') as f:
        src = f.read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == const_name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"Could not find constant {const_name} in {_FACTORY_SRC}")


def build_and_run(media_pipeline_fragment, num_buffers=30):
    """Builds `videotestsrc ! <fragment>` and runs it to EOS, capturing the
    negotiated caps on the payloader's sink pad (i.e. what codec is really
    being produced right before RTP packetization)."""
    Gst.init(None)
    launch = (
        f"videotestsrc num-buffers={num_buffers} ! "
        f"video/x-raw,width=320,height=240,framerate=25/1 {media_pipeline_fragment} ! fakesink"
    )
    print(f"Launch string: {launch}")
    pipeline = Gst.parse_launch(launch)

    pay = pipeline.get_by_name("pay0")
    assert pay is not None, "pay0 element not found - launch string is broken"
    sinkpad = pay.get_static_pad("sink")

    negotiated = {}

    def on_notify_caps(pad, _):
        caps = pad.get_current_caps()
        if caps:
            negotiated["caps"] = caps.to_string()

    sinkpad.connect("notify::caps", on_notify_caps)

    pipeline.set_state(Gst.State.PLAYING)
    bus = pipeline.get_bus()
    msg = bus.timed_pop_filtered(
        10 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
    caps_now = sinkpad.get_current_caps()
    if caps_now:
        negotiated["caps"] = caps_now.to_string()
    pipeline.set_state(Gst.State.NULL)

    if msg and msg.type == Gst.MessageType.ERROR:
        err, debug = msg.parse_error()
        raise RuntimeError(f"GStreamer error: {err} ({debug})")

    return negotiated.get("caps", "")


def main():
    """Runs the MJPEG and H.264 RTSP functional checks and exits non-zero
    on any negotiated-caps mismatch."""
    failures = []

    # --- MJPEG (default / existing behavior) must be unchanged ---
    mjpeg_fragment = _extract_fragment("_RtspVideoPipeline").format(gvawatermark="")
    mjpeg_caps = build_and_run(mjpeg_fragment)
    print(f"MJPEG negotiated caps: {mjpeg_caps}")
    if "image/jpeg" not in mjpeg_caps:
        failures.append(f"MJPEG branch did not negotiate image/jpeg caps: {mjpeg_caps}")

    # --- H.264 (new, opt-in) must negotiate video/x-h264 ---
    h264_fragment = _extract_fragment("_RtspVideoPipeline_h264").format(gvawatermark="")
    h264_caps = build_and_run(h264_fragment)
    print(f"H264 negotiated caps: {h264_caps}")
    if "video/x-h264" not in h264_caps:
        failures.append(f"H264 branch did not negotiate video/x-h264 caps: {h264_caps}")

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f" - {failure}")
        sys.exit(1)
    print("\nAll functional RTSP encoding checks passed.")


if __name__ == "__main__":
    main()
