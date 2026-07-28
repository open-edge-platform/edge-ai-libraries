# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Extract frames from video file with flexible time range and interval control.

This utility takes a video file and extracts images based on:
- Time interval (e.g., every 1 second)
- Specific time range (start time and duration)
- Total number of frames to extract

Usage:
    python generate_images_from_video.py <video_file> [options]

Options:
    --interval SECONDS      Extract every N seconds (default: 1.0)
    --start-time SECONDS    Start extraction from this time (default: 0.0)
    --duration SECONDS      Extract frames for N seconds from start-time
    --total-frames NUMBER   Extract exactly N frames evenly distributed
    --output-dir PATH       Output directory (default: extracted_frames)
"""

import cv2
import sys
from pathlib import Path
from typing import List, Optional, Tuple


def extract_frames_at_interval(
    video_path: str,
    output_dir: str = "extracted_frames",
    interval_seconds: float = 1.0,
    start_time: float = 0.0,
    duration: Optional[float] = None,
) -> List[str]:
    """
    Extract frames from video at regular time intervals within a time range.

    Args:
        video_path: Path to the video file
        output_dir: Directory to save extracted frames
        interval_seconds: Time interval between frames (default: 1.0 second)
        start_time: Start extraction from this time in seconds (default: 0.0)
        duration: Extract frames for this many seconds (None = to end of video)

    Returns:
        List of extracted frame file paths

    Raises:
        FileNotFoundError: If video file not found
        ValueError: If video cannot be opened or is invalid
    """
    video_path = Path(video_path)
    
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Open video file to get properties
    cap = cv2.VideoCapture(str(video_path))
    
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")
    
    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_duration = total_video_frames / fps if fps > 0 else 0
    cap.release()
    
    # Calculate end time based on duration parameter
    end_time = video_duration  # Default: to end of video
    if duration is not None:
        end_time = min(start_time + duration, video_duration)
    
    print(f"Video Information:")
    print(f"  File: {video_path.name}")
    print(f"  FPS: {fps:.2f}")
    print(f"  Total Frames: {total_video_frames}")
    print(f"  Duration: {video_duration:.2f}s")
    print(f"  Extraction Range: {start_time:.2f}s to {end_time:.2f}s")
    print()
    
    # Calculate frame boundaries
    start_frame = int(start_time * fps)
    end_frame = int(end_time * fps)
    extraction_frames = end_frame - start_frame
    
    # Calculate frame interval based on interval_seconds
    frame_interval = max(1, int(interval_seconds * fps))
    actual_frames = extraction_frames // frame_interval
    
    print(f"Extracting {actual_frames} frames from {extraction_frames} available frames...")
    print(f"  Frame interval: every {frame_interval} frames ({interval_seconds:.1f}s apart)")
    print()
    
    # Open video again for extraction
    cap = cv2.VideoCapture(str(video_path))
    
    extracted_frames = []
    frame_count = 0
    extracted_count = 0
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            break
        
        # Skip frames before start_frame
        if frame_count < start_frame:
            frame_count += 1
            continue
        
        # Stop after end_frame
        if frame_count >= end_frame:
            break
        
        # Extract frame at calculated interval
        if (frame_count - start_frame) % frame_interval == 0:
            time_elapsed = frame_count / fps
            frame_num = extracted_count
            time_str = f"{time_elapsed:.1f}s"
            
            # Save frame
            frame_path = output_path / f"frame_{frame_num:03d}_{time_str}.jpg"
            cv2.imwrite(str(frame_path), frame)
            extracted_frames.append(str(frame_path))
            
            print(f"  Frame {frame_num:3d}: {frame_path.name} ({time_elapsed:.2f}s)")
            extracted_count += 1
        
        frame_count += 1
    
    cap.release()
    
    print()
    print(f"✅ Extraction complete!")
    print(f"  Extracted: {extracted_count} frames")
    print(f"  Output directory: {output_path}")
    print()
    
    return extracted_frames


def extract_frames_total_count(
    video_path: str,
    total_frames: int = 20,
    output_dir: str = "extracted_frames",
    start_time: float = 0.0,
    duration: Optional[float] = None,
) -> List[str]:
    """
    Extract a specific total number of frames evenly distributed across video or time range.

    Args:
        video_path: Path to the video file
        total_frames: Number of frames to extract
        output_dir: Directory to save extracted frames
        start_time: Start extraction from this time in seconds
        duration: Extract frames for this many seconds (None = to end of video)

    Returns:
        List of extracted frame file paths
    """
    video_path = Path(video_path)
    
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Open video file to get properties
    cap = cv2.VideoCapture(str(video_path))
    
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")
    
    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_duration = total_video_frames / fps if fps > 0 else 0
    cap.release()
    
    # Calculate end time based on duration parameter
    end_time = video_duration  # Default: to end of video
    if duration is not None:
        end_time = min(start_time + duration, video_duration)
    
    print(f"Video Information:")
    print(f"  File: {video_path.name}")
    print(f"  FPS: {fps:.2f}")
    print(f"  Total Frames: {total_video_frames}")
    print(f"  Duration: {video_duration:.2f}s")
    print(f"  Extraction Range: {start_time:.2f}s to {end_time:.2f}s")
    print(f"  Target Frame Count: {total_frames}")
    print()
    
    # Calculate frame boundaries
    start_frame = int(start_time * fps)
    end_frame = int(end_time * fps)
    extraction_frames = end_frame - start_frame
    
    # Calculate frame interval for even distribution
    frame_interval = max(1, extraction_frames // total_frames)
    actual_frames = extraction_frames // frame_interval
    
    print(f"Extracting {actual_frames} frames from {extraction_frames} available frames...")
    print(f"  Frame interval: every {frame_interval} frames")
    print()
    
    # Open video again for extraction
    cap = cv2.VideoCapture(str(video_path))
    
    extracted_frames = []
    frame_count = 0
    extracted_count = 0
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            break
        
        # Skip frames before start_frame
        if frame_count < start_frame:
            frame_count += 1
            continue
        
        # Stop after end_frame
        if frame_count >= end_frame:
            break
        
        # Extract frame at calculated interval
        if (frame_count - start_frame) % frame_interval == 0:
            time_elapsed = frame_count / fps
            frame_num = extracted_count
            time_str = f"{time_elapsed:.1f}s"
            
            # Save frame
            frame_path = output_path / f"frame_{frame_num:03d}_{time_str}.jpg"
            cv2.imwrite(str(frame_path), frame)
            extracted_frames.append(str(frame_path))
            
            print(f"  Frame {frame_num:3d}: {frame_path.name} ({time_elapsed:.2f}s)")
            extracted_count += 1
        
        frame_count += 1
    
    cap.release()
    
    print()
    print(f"✅ Extraction complete!")
    print(f"  Extracted: {extracted_count} frames")
    print(f"  Output directory: {output_path}")
    print()
    
    return extracted_frames


def main():
    """Command-line interface for frame extraction."""
    if len(sys.argv) < 2:
        print("Usage: python generate_images_from_video.py <video_file> [options]")
        print()
        print("Options:")
        print("  --interval SECONDS      Extract every N seconds (default: 1.0)")
        print("  --start-time SECONDS    Start extraction from this time (default: 0.0)")
        print("  --duration SECONDS      Extract frames for N seconds from start-time")
        print("  --total-frames NUMBER   Extract exactly N frames evenly distributed")
        print("  --output-dir PATH       Output directory (default: extracted_frames)")
        print()
        print("Examples:")
        print("  # Extract frames every 1 second from entire video")
        print("  python generate_images_from_video.py test_video.mp4")
        print()
        print("  # Extract frames every 2 seconds")
        print("  python generate_images_from_video.py test_video.mp4 --interval 2.0")
        print()
        print("  # Extract 20 frames evenly from 5s to 15s (10 second duration)")
        print("  python generate_images_from_video.py test_video.mp4 --start-time 5.0 --duration 10.0 --total-frames 20")
        print()
        print("  # Extract frames from 8s to 18s with custom output directory")
        print("  python generate_images_from_video.py test_video.mp4 --start-time 8.0 --duration 10.0 --output-dir my_frames/")
        print()
        sys.exit(1)
    
    video_file = sys.argv[1]
    output_dir = "extracted_frames"
    interval_seconds = 1.0
    start_time = 0.0
    duration = None
    total_frames = None
    
    # Parse command-line arguments
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        
        if arg == "--interval" and i + 1 < len(sys.argv):
            interval_seconds = float(sys.argv[i + 1])
            i += 2
        elif arg == "--start-time" and i + 1 < len(sys.argv):
            start_time = float(sys.argv[i + 1])
            i += 2
        elif arg == "--duration" and i + 1 < len(sys.argv):
            duration = float(sys.argv[i + 1])
            i += 2
        elif arg == "--total-frames" and i + 1 < len(sys.argv):
            total_frames = int(sys.argv[i + 1])
            i += 2
        elif arg == "--output-dir" and i + 1 < len(sys.argv):
            output_dir = sys.argv[i + 1]
            i += 2
        else:
            print(f"Unknown option: {arg}")
            sys.exit(1)
    
    try:
        print("=" * 80)
        print("Video Frame Extraction Tool")
        print("=" * 80)
        print()
        
        if total_frames:
            # Extract specific number of frames evenly distributed
            frames = extract_frames_total_count(
                video_path=video_file,
                total_frames=total_frames,
                output_dir=output_dir,
                start_time=start_time,
                duration=duration,
            )
        else:
            # Extract frames at regular intervals
            frames = extract_frames_at_interval(
                video_path=video_file,
                output_dir=output_dir,
                interval_seconds=interval_seconds,
                start_time=start_time,
                duration=duration,
            )
        
        print("Next steps:")
        print(f"  1. Extracted frames are in: {output_dir}/")
        print(f"  2. Use these frames for API testing:")
        print(f"     curl -X POST http://localhost:8080/api/v1/analyze/batch \\")
        print(f"       -F 'entity_id=test_person' \\")
        for i, frame in enumerate(frames[:3]):
            print(f"       -F 'frames=@{frame}'" + (" \\" if i < 2 else ""))
        print()
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
