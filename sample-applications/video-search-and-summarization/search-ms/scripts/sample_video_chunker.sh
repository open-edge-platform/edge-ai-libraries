#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

chunk_duration=10
input_video="<input_video_path>.mp4"
output_dir="<output dir path>"

mkdir -p "$output_dir"

video_duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$input_video")
echo $video_duration

start_time=0

while (( $(echo "$start_time < $video_duration" | bc -l) )); do
    end_time=$(echo "$start_time + $chunk_duration" | bc)
    
    # Ensure the end time does not exceed the video duration
    if (( $(echo "$end_time > $video_duration" | bc -l) )); then
        end_time=$video_duration
    fi

    # Convert start_time and end_time to integers for the output file name
    rounded_start_time=$(printf "%d" "$start_time")
    rounded_end_time=$(printf "%d" "$end_time")
    output_file="$output_dir/chunk_${rounded_start_time}_${rounded_end_time}.mp4"

    # Enforce constant frame rate (e.g., 30 FPS) and re-encode using libx264
    ffmpeg -y -ss "$start_time" -i "$input_video" -t $(echo "$end_time - $start_time" | bc) -vf "fps=30" -c:v libx264 -preset fast -crf 23 -c:a copy -map_metadata 0 -movflags +faststart "$output_file" < /dev/null

    start_time=$end_time
done

echo "Video chunking completed."
