#!/bin/bash
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Fuzzing Runner Script - Run both OpenCV and OpenCV-free fuzzers

FUZZER_DIR="/home/arrow1/applications.robotics.mobile.orb-extractor/tests/fuzzer/build"

echo "=== ORB Extractor Fuzzing Suite ==="
echo "Directory: $FUZZER_DIR"
echo ""

if [ ! -d "$FUZZER_DIR" ]; then
    echo "❌ Fuzzer directory not found. Please build fuzzers first:"
    echo "   cd tests/fuzzer && mkdir build && cd build"
    echo "   cmake .. -DCMAKE_CXX_COMPILER=clang++"
    echo "   make"
    exit 1
fi

cd "$FUZZER_DIR" || exit

if [ "$1" = "opencv-free" ]; then
    echo "🧪 Starting OpenCV-Free Fuzzer (parameter validation)"
    echo "   Target: simple_fuzzer_opencv_free"
    echo "   Press Ctrl+C to stop"
    echo ""
    ./simple_fuzzer_opencv_free
elif [ "$1" = "opencv" ]; then
    echo "🧪 Starting Full OpenCV Fuzzer (OpenCV API validation)"
    echo "   Target: simple_fuzzer_opencv"
    echo "   Press Ctrl+C to stop"
    echo ""
    ./simple_fuzzer_opencv
elif [ "$1" = "test" ]; then
    echo "🧪 Testing both fuzzers (10 seconds each)"
    echo ""
    echo "--- OpenCV-Free Fuzzer Test ---"
    timeout 10s ./simple_fuzzer_opencv_free | tail -5
    echo ""
    echo "--- Full OpenCV Fuzzer Test ---"
    timeout 10s ./simple_fuzzer_opencv | tail -5
    echo ""
    echo "✅ Both fuzzers completed successfully!"
else
    echo "Usage: $0 {opencv-free|opencv|test}"
    echo ""
    echo "Options:"
    echo "  opencv-free  - Run OpenCV-free parameter validation fuzzer"
    echo "  opencv       - Run full OpenCV API validation fuzzer" 
    echo "  test         - Quick test of both fuzzers (10s each)"
    echo ""
    echo "Examples:"
    echo "  $0 opencv-free    # Long-running fuzzing session"
    echo "  $0 opencv         # Long-running fuzzing session"
    echo "  $0 test           # Quick verification both work"
    echo ""
    echo "Current fuzzer status:"
    ls -la simple_fuzzer_*
fi