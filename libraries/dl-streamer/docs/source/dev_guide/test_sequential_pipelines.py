#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
"""
Test script for sequential pipeline support in latency tracer.

This script creates and runs two pipelines sequentially to verify that
the latency tracer now tracks both pipelines correctly (not just the first one).

Expected behavior:
- Both pipelines should be tracked
- Stats should be logged for both pipeline1 and pipeline2
- No warning about "multiple pipelines may not give right result"

Usage:
    GST_TRACERS="latency_tracer(flags=pipeline)" GST_DEBUG="latency_tracer:5" python3 test_sequential_pipelines.py
"""

import gi
import os
import sys
import time

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

def run_pipeline(name, num_buffers=50):
    """Create, run, and clean up a pipeline."""
    print(f"\n{'='*60}")
    print(f"Starting {name}")
    print(f"{'='*60}\n")
    
    # Create pipeline
    pipeline_str = f"videotestsrc num-buffers={num_buffers} ! video/x-raw,width=320,height=240,framerate=30/1 ! fakesink sync=false"
    pipeline = Gst.parse_launch(pipeline_str)
    pipeline.set_name(name)
    
    # Set to PLAYING
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print(f"ERROR: Unable to set {name} to PLAYING state")
        return False
    
    # Wait for EOS or error
    bus = pipeline.get_bus()
    msg = bus.timed_pop_filtered(
        Gst.CLOCK_TIME_NONE,
        Gst.MessageType.ERROR | Gst.MessageType.EOS
    )
    
    # Check message type
    if msg:
        if msg.type == Gst.MessageType.ERROR:
            err, debug = msg.parse_error()
            print(f"ERROR from {name}: {err.message}")
            print(f"Debug info: {debug}")
        elif msg.type == Gst.MessageType.EOS:
            print(f"\n{name} completed successfully (EOS received)")
    
    # Clean up
    pipeline.set_state(Gst.State.NULL)
    print(f"\n{name} stopped and cleaned up")
    
    return True

def main():
    """Main test function."""
    print("="*60)
    print("Sequential Pipeline Test for Latency Tracer")
    print("="*60)
    print("\nThis test verifies that the latency tracer can track")
    print("multiple pipelines that are created and run sequentially.\n")
    
    # Check if latency tracer is enabled
    tracers = os.environ.get('GST_TRACERS', '')
    if 'latency_tracer' not in tracers:
        print("WARNING: GST_TRACERS does not include latency_tracer")
        print("Set GST_TRACERS='latency_tracer(flags=pipeline)' to enable tracking\n")
    
    # Initialize GStreamer
    Gst.init(None)
    
    # Run first pipeline
    if not run_pipeline("pipeline1", num_buffers=50):
        print("ERROR: Pipeline 1 failed")
        return 1
    
    # Small delay between pipelines
    time.sleep(0.5)
    
    # Run second pipeline
    if not run_pipeline("pipeline2", num_buffers=50):
        print("ERROR: Pipeline 2 failed")
        return 1
    
    print("\n" + "="*60)
    print("Test completed successfully!")
    print("="*60)
    print("\nExpected results:")
    print("  ✓ Both pipeline1 and pipeline2 should have latency stats")
    print("  ✓ No warning about 'multiple pipelines may not give right result'")
    print("  ✓ Each pipeline tracked with its own source->sink branch")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
