#!/usr/bin/env python3
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
"""
Test script for concurrent pipeline support in latency tracer.

This script creates and runs two pipelines concurrently to verify that
the latency tracer can track multiple pipelines running at the same time.

Expected behavior:
- Both pipelines should be tracked simultaneously
- Stats should be logged for both pipelines while they run concurrently
- Each pipeline should have separate statistics

Usage:
    GST_TRACERS="latency_tracer(flags=pipeline)" GST_DEBUG="latency_tracer:5" python3 test_concurrent_pipelines.py
"""

import gi
import os
import sys
import threading
import time

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

class PipelineRunner:
    """Helper class to run a pipeline in its own context."""
    
    def __init__(self, name, num_buffers=100, pattern=0):
        self.name = name
        self.num_buffers = num_buffers
        self.pattern = pattern
        self.pipeline = None
        self.bus = None
        self.loop = None
        self.success = False
        
    def on_message(self, bus, message):
        """Handle bus messages."""
        msg_type = message.type
        
        if msg_type == Gst.MessageType.EOS:
            print(f"\n{self.name}: EOS received - pipeline completed")
            self.success = True
            self.loop.quit()
        elif msg_type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\n{self.name}: ERROR - {err.message}")
            print(f"{self.name}: Debug info - {debug}")
            self.loop.quit()
        elif msg_type == Gst.MessageType.STATE_CHANGED:
            if message.src == self.pipeline:
                old_state, new_state, pending_state = message.parse_state_changed()
                print(f"{self.name}: State changed from {old_state.value_nick} to {new_state.value_nick}")
        
        return True
    
    def run(self):
        """Create and run the pipeline."""
        print(f"\n{self.name}: Starting...")
        
        # Create pipeline
        pipeline_str = (
            f"videotestsrc num-buffers={self.num_buffers} pattern={self.pattern} ! "
            f"video/x-raw,width=320,height=240,framerate=30/1 ! "
            f"queue ! videoconvert ! fakesink sync=false"
        )
        
        self.pipeline = Gst.parse_launch(pipeline_str)
        self.pipeline.set_name(self.name)
        
        # Set up bus
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self.on_message)
        
        # Create main loop
        self.loop = GLib.MainLoop()
        
        # Start pipeline
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print(f"{self.name}: ERROR - Unable to set to PLAYING state")
            return False
        
        print(f"{self.name}: Pipeline set to PLAYING")
        
        # Run main loop
        try:
            self.loop.run()
        except KeyboardInterrupt:
            print(f"\n{self.name}: Interrupted by user")
        
        # Clean up
        self.pipeline.set_state(Gst.State.NULL)
        self.bus.remove_signal_watch()
        
        print(f"{self.name}: Stopped and cleaned up")
        
        return self.success

def run_pipeline_thread(runner):
    """Thread function to run a pipeline."""
    runner.run()

def main():
    """Main test function."""
    print("="*60)
    print("Concurrent Pipeline Test for Latency Tracer")
    print("="*60)
    print("\nThis test verifies that the latency tracer can track")
    print("multiple pipelines running concurrently at the same time.\n")
    
    # Check if latency tracer is enabled
    tracers = os.environ.get('GST_TRACERS', '')
    if 'latency_tracer' not in tracers:
        print("WARNING: GST_TRACERS does not include latency_tracer")
        print("Set GST_TRACERS='latency_tracer(flags=pipeline)' to enable tracking\n")
    
    # Initialize GStreamer
    Gst.init(None)
    
    # Create pipeline runners
    runner1 = PipelineRunner("pipeline1", num_buffers=100, pattern=0)
    runner2 = PipelineRunner("pipeline2", num_buffers=100, pattern=1)
    
    # Create threads for each pipeline
    thread1 = threading.Thread(target=run_pipeline_thread, args=(runner1,))
    thread2 = threading.Thread(target=run_pipeline_thread, args=(runner2,))
    
    # Start both pipelines
    print("\nStarting concurrent pipelines...")
    thread1.start()
    time.sleep(0.5)  # Small delay to stagger starts
    thread2.start()
    
    # Wait for both to complete
    print("\nWaiting for pipelines to complete...")
    thread1.join()
    thread2.join()
    
    # Check results
    print("\n" + "="*60)
    if runner1.success and runner2.success:
        print("Test completed successfully!")
        print("="*60)
        print("\nExpected results:")
        print("  ✓ Both pipeline1 and pipeline2 tracked concurrently")
        print("  ✓ Separate latency stats for each pipeline")
        print("  ✓ No interference between pipelines")
        print("  ✓ Each pipeline has its own source->sink branch")
        return 0
    else:
        print("Test FAILED - One or more pipelines did not complete successfully")
        print("="*60)
        return 1

if __name__ == '__main__':
    sys.exit(main())
