#!/bin/bash
# ==============================================================================
# Copyright (C) 2025 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================

# Test examples for multi-branch latency tracer
# These examples demonstrate how to test the enhanced latency tracer with multiple branches

echo "Multi-Branch Latency Tracer Test Examples"
echo "=========================================="
echo ""
echo "These examples require GStreamer 1.0 and the latency_tracer plugin to be installed."
echo ""

# Example 1: Single source with tee to multiple sinks
example1() {
    echo "Example 1: Single source with tee to multiple sinks"
    echo "Expected: Tracking filesrc0 -> fakesink0 and filesrc0 -> fakesink1"
    echo ""
    GST_DEBUG="GST_TRACER:7" GST_TRACERS="latency_tracer" gst-launch-1.0 \
        videotestsrc num-buffers=50 name=src ! video/x-raw,width=640,height=480,framerate=30/1 ! tee name=t \
        t. ! queue ! videoconvert ! fakesink name=sink1 sync=false \
        t. ! queue ! videoconvert ! fakesink name=sink2 sync=false
}

# Example 2: Multiple independent sources
example2() {
    echo "Example 2: Multiple independent sources and sinks"
    echo "Expected: Tracking src1 -> sink1, src2 -> sink2, and src3 -> sink3"
    echo ""
    GST_DEBUG="GST_TRACER:7" GST_TRACERS="latency_tracer" gst-launch-1.0 \
        videotestsrc num-buffers=50 name=src1 pattern=0 ! video/x-raw,width=320,height=240 ! videoconvert ! fakesink name=sink1 sync=false \
        videotestsrc num-buffers=50 name=src2 pattern=1 ! video/x-raw,width=320,height=240 ! videoconvert ! fakesink name=sink2 sync=false \
        videotestsrc num-buffers=50 name=src3 pattern=2 ! video/x-raw,width=320,height=240 ! videoconvert ! fakesink name=sink3 sync=false
}

# Example 3: Complex multi-branch with different frame rates
example3() {
    echo "Example 3: Multiple sources with different frame rates"
    echo "Expected: Different latency statistics for each branch"
    echo ""
    GST_DEBUG="GST_TRACER:7" GST_TRACERS="latency_tracer(flags=pipeline,interval=1000)" gst-launch-1.0 \
        videotestsrc num-buffers=60 name=fast_src ! video/x-raw,width=640,height=480,framerate=60/1 ! videoconvert ! fakesink name=fast_sink sync=false \
        videotestsrc num-buffers=30 name=slow_src ! video/x-raw,width=640,height=480,framerate=30/1 ! videoconvert ! fakesink name=slow_sink sync=false
}

# Example 4: Pipeline-only mode for cleaner output
example4() {
    echo "Example 4: Pipeline latency only (cleaner output)"
    echo "Expected: Only pipeline latency logs with source->sink identification"
    echo ""
    GST_DEBUG="GST_TRACER:7" GST_TRACERS="latency_tracer(flags=pipeline)" gst-launch-1.0 \
        videotestsrc num-buffers=100 name=src ! video/x-raw,width=640,height=480 ! tee name=t \
        t. ! queue ! videoconvert ! fakesink name=sink1 sync=false \
        t. ! queue ! videoconvert ! fakesink name=sink2 sync=false
}

# Example 5: With interval reporting
example5() {
    echo "Example 5: Multi-branch with interval reporting"
    echo "Expected: Periodic summary statistics for each branch"
    echo ""
    GST_DEBUG="GST_TRACER:7" GST_TRACERS="latency_tracer(flags=pipeline,interval=2000)" gst-launch-1.0 \
        videotestsrc num-buffers=200 name=src1 ! video/x-raw,width=640,height=480,framerate=30/1 ! videoconvert ! fakesink name=sink1 sync=false \
        videotestsrc num-buffers=200 name=src2 ! video/x-raw,width=640,height=480,framerate=30/1 ! videoconvert ! fakesink name=sink2 sync=false
}

# Show menu
show_menu() {
    echo "Select an example to run:"
    echo "1) Single source with tee to multiple sinks"
    echo "2) Multiple independent sources and sinks"
    echo "3) Multiple sources with different frame rates"
    echo "4) Pipeline latency only (cleaner output)"
    echo "5) Multi-branch with interval reporting"
    echo "6) Run all examples"
    echo "0) Exit"
    echo ""
}

# Main menu loop
while true; do
    show_menu
    read -p "Enter your choice: " choice
    echo ""
    
    case $choice in
        1) example1 ;;
        2) example2 ;;
        3) example3 ;;
        4) example4 ;;
        5) example5 ;;
        6) 
            example1
            echo ""
            read -p "Press Enter to continue to next example..."
            example2
            echo ""
            read -p "Press Enter to continue to next example..."
            example3
            echo ""
            read -p "Press Enter to continue to next example..."
            example4
            echo ""
            read -p "Press Enter to continue to next example..."
            example5
            ;;
        0) 
            echo "Exiting..."
            exit 0
            ;;
        *) 
            echo "Invalid choice. Please try again."
            echo ""
            ;;
    esac
    
    echo ""
    echo "Example completed."
    echo ""
    read -p "Press Enter to return to menu..."
    echo ""
done
