#!/usr/bin/env bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Download MPI Sintel training + KITTI 2015 scene flow onto a lab host.
set -euo pipefail

ROOT="${1:-$HOME/datasets/optical-flow}"
mkdir -p "$ROOT"
cd "$ROOT"

echo "Dataset root: $ROOT"

fetch() {
  local url="$1"
  local out="$2"
  if [[ -f "$out" ]]; then
    echo "exists: $out"
    return 0
  fi
  echo "fetching $url -> $out"
  wget -c -O "$out.partial" "$url"
  mv "$out.partial" "$out"
}

# KITTI 2015 scene flow (~1.6 GiB) — includes training/image_2 + flow_occ.
# Sintel complete (~5.3 GiB) — training/{clean,final,flow}. Both unpack a
# top-level training/; subdir names do not collide (image_2 vs clean/flow).
fetch "https://s3.eu-central-1.amazonaws.com/avg-kitti/data_scene_flow.zip" \
  "data_scene_flow.zip"

# Prefer complete archive (images + flow). training_flow.zip is often 404.
if wget --spider -q "https://files.is.tue.mpg.de/sintel/MPI-Sintel-training_flow.zip"; then
  fetch "https://files.is.tue.mpg.de/sintel/MPI-Sintel-training_images.zip" \
    "MPI-Sintel-training_images.zip"
  fetch "https://files.is.tue.mpg.de/sintel/MPI-Sintel-training_flow.zip" \
    "MPI-Sintel-training_flow.zip"
else
  echo "MPI-Sintel-training_flow.zip unavailable; fetching complete archive"
  fetch "https://files.is.tue.mpg.de/sintel/MPI-Sintel-complete.zip" \
    "MPI-Sintel-complete.zip"
fi

extract_if_needed() {
  local zip="$1"
  local marker="$2"
  if [[ -e "$marker" ]]; then
    echo "extracted marker present: $marker"
    return 0
  fi
  echo "extracting $zip"
  unzip -q -n "$zip"
}

extract_if_needed data_scene_flow.zip training/image_2

if [[ -f MPI-Sintel-training_flow.zip ]]; then
  extract_if_needed MPI-Sintel-training_images.zip training/clean
  extract_if_needed MPI-Sintel-training_flow.zip training/flow
elif [[ -f MPI-Sintel-complete.zip ]]; then
  extract_if_needed MPI-Sintel-complete.zip training/flow
fi

echo "done"
find "$ROOT" -maxdepth 3 -type d | head -40
