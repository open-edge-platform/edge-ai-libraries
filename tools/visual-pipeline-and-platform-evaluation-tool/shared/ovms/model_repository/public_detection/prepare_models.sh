#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

download() {
    local url="$1"
    local path="$2"
    local checksum="$3"

    mkdir -p "$(dirname "${path}")"
    curl --fail --location --proto '=https' --retry 3 --tlsv1.2 "${url}" --output "${path}"
    test -s "${path}"
    printf '%s  %s\n' "${checksum}" "${path}" | sha256sum --check --status
}

download \
    "https://storage.googleapis.com/mediapipe-assets/ssdlite_object_detection.tflite" \
    "models/ssdlite_object_detection/1/ssdlite_object_detection.tflite" \
    "8e10a2e2f5db85d8f90628f00752a89ff241c5b2ca82f3b92fc496c7bda122ef"
download \
    "https://storage.googleapis.com/mediapipe-assets/ssdlite_object_detection_labelmap.txt" \
    "ssdlite_object_detection_labelmap.txt" \
    "c7e79c855f73cbba9f33d649d60e1676eb0a974021a41696d1ac0d4b7f7e0211"