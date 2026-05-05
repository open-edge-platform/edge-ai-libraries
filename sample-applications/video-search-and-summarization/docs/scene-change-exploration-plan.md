# Exploration Plan: Intelligent Frame Selection via Scene Change Detection

> **Status**: Exploration Phase  
> **Jira Reference**: [ITEP-90890](https://jira.devtools.intel.com/browse/ITEP-90890) <br>
> **Last Updated**: 2026-04-29

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Current Architecture](#current-architecture)
- [Zero-Copy Architecture Constraint](#zero-copy-architecture-constraint)
- [Exploration Options](#exploration-options)
  - [Option 1: GStreamer scenechange Element](#option-1-gstreamer-scenechange-element)
  - [Option 2: PySceneDetect](#option-2-pyscenedetect)
  - [Option 3: FFmpeg Scene Detection Filter](#option-3-ffmpeg-scene-detection-filter)
  - [Option 4: OpenCV Custom Implementation](#option-4-opencv-custom-implementation)
  - [Option 5: TransNetV2 (Deep Learning)](#option-5-transnetv2-deep-learning)
  - [Option 6: DLSPS UDFLoader Plugin](#option-6-dlsps-udfloader-plugin)
- [Architecture Design: Scene-Aware Summarization](#architecture-design-scene-aware-summarization)
  - [Dual-Mode Frame Selection](#dual-mode-frame-selection)
  - [Scene-as-Semantic-Unit Strategy](#scene-as-semantic-unit-strategy)
  - [Frame Extraction Policy](#frame-extraction-policy)
  - [1 Scene = 1 Chunk = 1 VLM Call](#1-scene--1-chunk--1-vlm-call)
  - [multiFrame as Per-Scene Cap](#multiframe-as-per-scene-cap)
  - [Audio Transcript Alignment](#audio-transcript-alignment)
  - [Pipeline Rate Adjustment](#pipeline-rate-adjustment)
  - [Architectural Changes Summary](#architectural-changes-summary)
- [Evaluation Criteria](#evaluation-criteria)
- [Exploration Phases](#exploration-phases)
- [Jira Ticket](#jira-ticket)
- [References & Resources](#references--resources)
- [Notes & Considerations](#notes--considerations)

---

## Problem Statement

The VSS application currently uses **uniform interval-based frame sampling** during video ingestion. Frames are extracted at a constant rate defined by `samplingFrame / chunkDuration` (e.g., 2 frames per 10 seconds). This approach is simple and predictable but has significant limitations:

| Limitation | Impact |
|-----------|--------|
| **Wastes resources on static scenes** | Surveillance of an empty room extracts identical frames |
| **Misses important content** | Fast cuts, action sequences may fall between sampling intervals |
| **Suboptimal VLM summaries** | Frames don't represent meaningful visual transitions |
| **No content awareness** | Same frame rate regardless of video complexity |

**Goal**: Introduce an **alternative frame selection mode** based on scene change detection, offered alongside existing uniform sampling as an opt-in enhancement. The existing uniform sampling remains the **default mode** — scene change detection is enabled by the user when content-aware frame selection is desired.

---

## Current Architecture

### Frame Selection Pipeline

```
User Input (samplingFrame=2, chunkDuration=10)
    → EVAM Service (startChunkingStub)
    → GStreamer Pipeline:
        {source} ! decodebin ! videorate ! videoconvertscale !
        video/x-raw,framerate={frame}/{chunk_duration},format=BGR,
        width=[1,{frame_width}] ! gvapython(Publisher) ! fakesink
    → Publisher.process() saves frames to Minio + publishes chunks to RabbitMQ
    → Pipeline Manager receives chunks → batches frames (multiFrame=12) → VLM inference
```

### Key Files

| Component | File | Purpose |
|-----------|------|---------|
| GStreamer pipeline config | `video-ingestion/resources/conf/config.json` | Pipeline template + parameter definitions |
| Frame publisher | `video-ingestion/src/publish.py` | Python GVA extension — frame extraction, Minio upload, RabbitMQ publish |
| EVAM service | `pipeline-manager/src/evam/services/evam.service.ts` | Constructs EVAM/DLSPS pipeline requests |
| Frame batching | `pipeline-manager/src/state-manager/queues/chunking.service.ts` | Sliding window batching for VLM (multiFrame=12) |
| CLI configs | `cli/config/{generic,traffic,retail}.yaml` | User-facing parameter defaults |
| Pipeline config | `pipeline-manager/src/config/configuration.ts` | System defaults (multiFrame, frameOverlap) |

### Current Parameters

| Parameter | Range | Default | Purpose |
|-----------|-------|---------|---------|
| `samplingFrame` | 1-64 | 2 (generic) / 6 (traffic) | Frames per chunk |
| `chunkDuration` | 2-60s | 20 (generic) / 3 (traffic) | Seconds per chunk |
| `frame_width` | 160-800 | 480 | Resize width |
| `multiFrame` | 1-∞ | 12 | Frames batched for VLM |
| `frameOverlap` | 0-multiFrame | 0 | Overlap in VLM batching |

**Effective Frame Rate**: `fps = samplingFrame / chunkDuration`

---

## Zero-Copy Architecture Constraint

### DLSPS Zero-Copy Pipeline

DLSPS maintains a **zero-copy buffer pipeline** where GStreamer buffers flow through elements without unnecessary memory copies. This is a critical architectural property — any scene change detection solution must respect it.

**DLSPS supports three memory paths:**

| Memory Type | Path | Used When |
|-------------|------|-----------|
| `memory:VAMemory` | Intel GPU VA surfaces | GPU decode + GPU inference pipeline |
| `memory:DMABuf` | Cross-device DMA buffers | Cross-device zero-copy |
| System Memory (CPU) | Standard CPU buffers | Software decode (current VSS default) |

### Current VSS Pipeline Memory Flow

```
Video File
    ↓ decodebin (software H.264 decode)
System Memory (raw YUV420)
    ↓ videorate (passes through, no copy)
System Memory (YUV420 @ target framerate)
    ↓ videoconvertscale (resize + BGR conversion) ← ONLY MEMORY COPY POINT
System Memory (BGR @ frame_width resolution)
    ↓ gvapython: frame.data() maps buffer to numpy array (no additional copy)
Publisher.process(frame) receives numpy array
    ↓ cv2/PIL operations + JPEG encode (all on same buffer)
    ↓ Upload to Minio (network I/O)
```

**Key insight**: By the time `Publisher.process()` is called, the frame is **already in CPU memory as a BGR numpy array** via `frame.data()`. The `videoconvertscale` element is the single memory copy point — this already exists and cannot be avoided (needed for format conversion + resize).

### Where Scene Detection Can Fit Without Overhead

The `frame.data()` context manager in `Publisher.process()` already maps the GStreamer buffer to a numpy array for JPEG encoding. Scene detection can **reuse this same mapped buffer** — computing histogram scores or pixel differences on an array already in memory adds **compute time but zero memory copy overhead**.

```python
# Current flow in Publisher.process():
with frame.data() as image:          # numpy array already mapped
    self.save_image(image, ...)       # already reads this buffer for JPEG
    # ↑ Scene detection can compute on this SAME 'image' array
    # No new GStreamer element needed, no buffer copy added
```

### Zero-Copy Compatibility Assessment

| Option | Zero-Copy Compatible? | Why |
|--------|----------------------|-----|
| **GStreamer `scenechange`** | ✅ Yes | Passthrough filter, doesn't modify buffer. Insert before `videoconvertscale` on raw YUV. |
| **Inline in `Publisher.process()` (OpenCV/custom)** | ✅ Yes — **best fit** | Reuses `frame.data()` numpy array already mapped for JPEG encoding. Zero new elements. |
| **PySceneDetect in `Publisher.process()`** | ✅ Yes | Same as above — runs on existing numpy array. |
| **FFmpeg pre-processing** | ⚠️ N/A | Separate framework, separate pass — doesn't touch DLSPS pipeline. |
| **TransNetV2 batch** | ⚠️ N/A | Separate inference pass — doesn't touch DLSPS pipeline. |
| **DLSPS UDFLoader** | ⚠️ Adds element | Inserts a new GStreamer element with Python callback — adds per-frame overhead even if buffer isn't copied. |

### Recommended Integration Point

**Insert scene detection logic directly inside `Publisher.process()`** — this is the zero-overhead path:

- **Files to modify**: `video-ingestion/src/publish.py`, `video-ingestion/resources/conf/config.json`
- **Memory overhead**: None (reuses existing `frame.data()` mapping)
- **Compute overhead**: ~0.5–1ms/frame (histogram) or ~2–5ms/frame (PySceneDetect)
- **Pipeline changes**: None (no new GStreamer elements)
- **The `prev_frame` reference** needs a single `.copy()` (~0.1ms for 480px-wide frame) — same cost as existing JPEG encoding

---

## Exploration Options

### Option 1: GStreamer `scenechange` Element

**Category**: Native GStreamer Plugin (Real-time, Inline)

**Source**: `gst-plugins-bad/gst/videofilters/gstscenechange.c`

#### How It Works

The `scenechange` element is a GStreamer video filter in the "bad" plugins package. It computes the Sum of Absolute Differences (SAD) between consecutive frames and uses an adaptive threshold to detect scene changes.

**Algorithm**:
1. Compute SAD between current and previous frame (SIMD-optimized via ORC)
2. Maintain sliding window of 5 frame difference scores
3. Calculate adaptive threshold: `threshold = 1.8 × score_max − 0.8 × score_min`
4. Apply multi-criteria detection:

```
if score < 5                              → no change (too similar)
if score / threshold < 1.0                → no change (below threshold)
if score > 30 AND score / prev_score > 1.4 → SCENE CHANGE (significant jump)
if score / threshold > 2.3               → SCENE CHANGE (well above threshold)
if score > 50                            → SCENE CHANGE (absolute high difference)
```

5. On detection: send `GstForceKeyUnit` event downstream

**Supported formats**: I420, Y42B, Y41B, Y444 (YUV planar only)

**Example pipeline**:
```bash
gst-launch-1.0 -v filesrc location=video.mp4 ! decodebin ! \
  videoconvert ! video/x-raw,format=I420 ! scenechange ! \
  gvapython class=Publisher module=publish.py ! fakesink
```

#### Integration Approach

- Insert `scenechange` element into the GStreamer pipeline template in `config.json`
- Modify `Publisher.process()` to detect ForceKeyUnit events via pad probes
- Only emit frames when scene change is detected
- Requires `videoconvert` to convert to I420 before scenechange element

#### Zero-Copy Impact

> **✅ Compatible** — `scenechange` is a passthrough video filter. It reads buffer data for SAD computation but does not modify the buffer contents. The buffer flows through unchanged.
>
> **⚠️ Caveat**: Must be inserted **before** `videoconvertscale` in the pipeline (operates on YUV, not BGR). Since it's a passthrough filter operating on raw YUV that's already in system memory after `decodebin`, it adds no memory copy. However, it does require a specific YUV format (I420/Y42B/Y41B/Y444) — if the decoder outputs a different format, a `videoconvert` may be needed which could introduce a copy.
>
> **Pipeline placement**:
> ```
> {source} ! decodebin ! videorate ! videoconvert ! video/x-raw,format=I420 !
>     scenechange ! videoconvertscale ! video/x-raw,format=BGR ! gvapython ! fakesink
> ```

#### Evaluation

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Detection Accuracy | ⭐⭐⭐ | ~95% on hard cuts; poor on fades/dissolves |
| Performance | ⭐⭐⭐⭐⭐ | SIMD-optimized, sub-millisecond per frame |
| Integration Effort | ⭐⭐⭐⭐ | Single element addition, but needs pad probe for event detection |
| Configurability | ⭐ | No tunable properties (all hardcoded) |
| Dependencies | ⭐⭐⭐⭐⭐ | Already in gst-plugins-bad |
| Intel HW Optimization | ⭐⭐⭐ | ORC SIMD (SSE2/AVX) |
| Zero-Copy | ✅ | Passthrough filter; but may need format negotiation |

#### Exploration Tasks

1. Verify `scenechange` element availability in DLSPS Docker image: `gst-inspect-1.0 scenechange`
2. Build test pipeline with sample videos
3. Measure latency impact on ingestion pipeline
4. Evaluate detection quality — count false positives/negatives
5. Test with different video types (surveillance, action, interview)

#### References

- **GStreamer Documentation**: https://gstreamer.freedesktop.org/documentation/videofiltersbad/scenechange.html
- **Source Code**: `gstreamer/subprojects/gst-plugins-bad/gst/videofilters/gstscenechange.c`
- **ORC Optimization**: `gstreamer/subprojects/gst-plugins-bad/gst/videofilters/gstscenechangeorc.orc`
- **Plugin Registration**: `gstreamer/subprojects/gst-plugins-bad/gst/videofilters/gstvideofiltersbad.c`
- **GStreamer Video Events API**: https://gstreamer.freedesktop.org/documentation/video/gstvideoevent.html

---

### Option 2: PySceneDetect

**Category**: Python Library (Real-time or Batch)

**Library**: [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) — `pip install scenedetect[opencv]`

#### How It Works

PySceneDetect is a Python library and CLI tool for detecting scene changes in video files. It provides multiple detection algorithms:

| Detector | Algorithm | Best For | Key Params |
|----------|-----------|----------|------------|
| **ContentDetector** | HSV color histogram + luminance + edge differences | General purpose, hard cuts | `threshold=27.0`, component weights (hue/sat/lum/edges) |
| **AdaptiveDetector** | Rolling average with adaptive window (extends ContentDetector) | Videos with camera motion, variable lighting | `adaptive_threshold=3.0`, `window_width=2`, `min_content_val=15.0` |
| **ThresholdDetector** | Average pixel intensity thresholding (RGB mean) | Fade in/out detection (to black/white) | `threshold=12`, `method=FLOOR/CEILING`, `fade_bias` |
| **HistogramDetector** | Y-channel (YUV) histogram correlation | Fast luminance-based cut detection | `threshold=0.05`, `bins=256` |
| **HashDetector** | Perceptual hash (DCT + lowpass + binary threshold), Hamming distance | Near-duplicate detection, compression artifacts | `threshold=0.395`, `size=16`, `lowpass=2` |
| **TransNetV2Detector** | ONNX neural network (CNN), 100-frame batch windows | All transition types (SOTA accuracy) | `threshold`, `model_path`, `onnx_providers` |

**Planned** (not yet implemented): `DissolveDetector` (slow fades via HSV), `MotionDetector` (background subtraction)

All detectors share a common interface:
- `process_frame(timecode, frame_img: numpy.ndarray)` — accepts BGR numpy array (compatible with `frame.data()`)
- `min_scene_len` parameter — enforces minimum scene length (frames, seconds, or timecode string)
- `FlashFilter` — provides MERGE and SUPPRESS modes for handling flash frames

#### Integration Approaches

**Real-time (inline) — inside existing `Publisher.process()`**:
```python
# Inside gvapython Publisher callback — reuses frame.data() numpy array
from scenedetect import ContentDetector

class SceneAwarePublisher:
    def __init__(self):
        self.detector = ContentDetector(threshold=27.0)
        self.prev_frame = None

    def process(self, frame):
        with frame.data() as image:  # already mapped, no new copy
            score = self._compute_score(image)
            if score > self.detector.threshold:
                self._emit_frame(frame)
```

**Batch (offline)**:
```python
from scenedetect import detect, ContentDetector

scene_list = detect("video.mp4", ContentDetector())
# Returns: [(FrameTimecode(start), FrameTimecode(end)), ...]
```

#### Zero-Copy Impact

> **✅ Compatible** — when used inside `Publisher.process()`, PySceneDetect operates on the same `frame.data()` numpy array already mapped for JPEG encoding. No new GStreamer elements, no buffer copies.
>
> The real-time inline approach is the recommended path. Batch mode is also available but runs outside the pipeline.

#### Evaluation

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Detection Accuracy | ⭐⭐⭐⭐ | Good on hard cuts and fades; multiple algorithms |
| Performance | ⭐⭐⭐ | ~2-5ms per frame (Python/OpenCV) |
| Integration Effort | ⭐⭐⭐⭐ | pip install + Python integration |
| Configurability | ⭐⭐⭐⭐⭐ | Threshold, weights, algorithm selection |
| Dependencies | ⭐⭐⭐ | Adds scenedetect + numpy/opencv |
| Intel HW Optimization | ⭐⭐ | OpenCV backend (MKL possible) |
| Zero-Copy | ✅ | Reuses existing `frame.data()` mapping — no new elements |

#### Exploration Tasks

1. Install PySceneDetect in VSS Docker environment
2. Test all 4 detectors on sample videos — compare results
3. Benchmark per-frame processing time (ContentDetector vs AdaptiveDetector)
4. Prototype real-time integration via `gvapython` callback in `publish.py`
5. Test batch mode: generate scene list → extract frames at boundaries
6. Tune threshold values for different video types

#### References

- **GitHub Repository**: https://github.com/Breakthrough/PySceneDetect
- **Documentation**: https://www.scenedetect.com/
- **API Reference**: https://www.scenedetect.com/docs/latest/api.html
- **ContentDetector Docs**: https://www.scenedetect.com/docs/latest/api/detectors.html#scenedetect.detectors.content_detector.ContentDetector
- **AdaptiveDetector Docs**: https://www.scenedetect.com/docs/latest/api/detectors.html#scenedetect.detectors.adaptive_detector.AdaptiveDetector
- **PyPI**: https://pypi.org/project/scenedetect/
- **Comparison Blog**: https://www.scenedetect.com/docs/latest/cli/detectors.html

---

### Option 3: FFmpeg Scene Detection Filter

**Category**: CLI Tool / Pre-processing (Batch)

**Tool**: FFmpeg `select` filter with `scene` variable

#### How It Works

FFmpeg's `select` filter provides a `scene` variable (0.0–1.0) that measures the difference between consecutive frames using SAD. Frames can be selected/rejected based on this score.

**Usage examples**:
```bash
# Extract frames at scene changes (threshold 0.4)
ffmpeg -i video.mp4 -vf "select='gt(scene,0.4)',showinfo" -vsync vfr out_%04d.png

# Get scene change timestamps
ffmpeg -i video.mp4 -vf "select='gt(scene,0.3)',showinfo" -f null - 2>&1 | \
  grep "showinfo" | grep -oP 'pts_time:\K[0-9.]+'

# Combine with scene detection and metadata output
ffprobe -v quiet -show_frames -of json video.mp4 | \
  python -c "import json,sys; [print(f['pkt_pts_time']) for f in json.load(sys.stdin)['frames'] if float(f.get('scene_score',0))>0.4]"
```

**How `scene` score is computed**:
- FFmpeg's `select` filter calculates per-frame SAD internally
- Normalized to 0.0–1.0 range
- Lower values = similar frames; higher values = scene change
- Typical thresholds: 0.3 (sensitive) to 0.5 (conservative)

#### Integration Approach

**Two-pass architecture**:
1. **Pass 1**: Run FFmpeg to extract scene change timestamps
2. **Pass 2**: Feed timestamps to GStreamer pipeline for targeted frame extraction

```python
# Pre-processing step
timestamps = run_ffmpeg_scene_detect("video.mp4", threshold=0.4)
# → [0.0, 12.5, 23.1, 45.8, ...]

# Modified GStreamer pipeline seeks to each timestamp
for ts in timestamps:
    extract_frame_at(pipeline, ts)
```

#### Zero-Copy Impact

> **⚠️ N/A** — FFmpeg runs as a separate process outside the DLSPS/GStreamer pipeline. It does not interact with the zero-copy buffer chain. Useful as a pre-processing step but adds architectural complexity (two-pass workflow).

#### Evaluation

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Detection Accuracy | ⭐⭐⭐ | SAD-based; similar to GStreamer scenechange |
| Performance | ⭐⭐⭐⭐ | Fast C implementation, HW accel support |
| Integration Effort | ⭐⭐ | Requires two-pass architecture |
| Configurability | ⭐⭐⭐⭐ | Threshold 0.0-1.0, filter expressions |
| Dependencies | ⭐⭐⭐ | FFmpeg binary needed alongside GStreamer |
| Intel HW Optimization | ⭐⭐⭐⭐ | VAAPI, QSV decoding acceleration |
| Zero-Copy | ⚠️ N/A | Runs outside DLSPS pipeline |

#### References

- **FFmpeg select filter**: https://ffmpeg.org/ffmpeg-filters.html#select_002c-aselect
- **FFmpeg scene detection guide**: https://ffmpeg.org/ffmpeg-filters.html#select_002c-aselect (search for `scene`)
- **FFmpeg hardware acceleration**: https://trac.ffmpeg.org/wiki/HWAccelIntro
- **Intel QSV with FFmpeg**: https://www.intel.com/content/www/us/en/developer/articles/technical/using-ffmpeg-with-intel-media-sdk.html
- **VAAPI with FFmpeg**: https://trac.ffmpeg.org/wiki/Hardware/VAAPI

---

### Option 4: OpenCV Custom Implementation

**Category**: Custom Python (Real-time or Batch)

**Library**: OpenCV (`cv2`) — likely already in DLSPS Docker image

#### Algorithms to Explore

| Algorithm | Method | Sensitivity | Speed |
|-----------|--------|-------------|-------|
| **Histogram Comparison** | Compare color histograms (Chi-Square, Bhattacharyya, Correlation) | Medium | Fast |
| **SSIM** | Structural Similarity Index between frames | High | Medium |
| **Optical Flow** | Lucas-Kanade or Farneback motion estimation | High | Slow |
| **Edge Detection** | Compare Canny/Sobel edge maps | Medium | Fast |
| **Feature Matching** | ORB/SIFT keypoint comparison | High | Slow |
| **Mean Pixel Diff** | Average absolute pixel difference | Low | Very Fast |

#### Prototype Implementation (inside `Publisher.process()`)

```python
import cv2
import numpy as np

class OpenCVSceneDetector:
    """Designed to run inside Publisher.process() on the existing frame.data() numpy array."""
    def __init__(self, method="histogram", threshold=0.5):
        self.method = method
        self.threshold = threshold
        self.prev_hist = None

    def detect(self, image):
        """Takes the BGR numpy array from frame.data() — no copy needed.
        Returns True if scene change detected."""
        if self.method == "histogram":
            return self._histogram_detect(image)
        elif self.method == "ssim":
            return self._ssim_detect(image)

    def _histogram_detect(self, image):
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)

        if self.prev_hist is None:
            self.prev_hist = hist
            return True  # First frame is always a scene boundary

        score = cv2.compareHist(self.prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)
        self.prev_hist = hist
        return score > self.threshold

    def _ssim_detect(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if not hasattr(self, 'prev_gray') or self.prev_gray is None:
            self.prev_gray = gray
            return True

        score = cv2.quality.QualitySSIM_compute(self.prev_gray, gray)
        self.prev_gray = gray
        return score[0] < self.threshold  # Low SSIM = different scenes
```

**Usage in `Publisher.process()`:**
```python
def process(self, frame):
    with frame.data() as image:       # numpy array already mapped
        if self.scene_detector.detect(image):   # compute on same buffer
            # ... existing frame save + publish logic ...
```

#### Zero-Copy Impact

> **✅ Best fit** — OpenCV operations run directly on the `frame.data()` numpy array already mapped for JPEG encoding. This is the **zero-overhead integration path**:
> - No new GStreamer elements added to the pipeline
> - No additional buffer copies
> - Histogram computation: ~0.5ms (cv2.calcHist + cv2.compareHist)
> - Only cost: `prev_hist` storage (tiny — a histogram array, not a full frame)
> - OpenCV is likely already available in the DLSPS Docker image

#### Evaluation

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Detection Accuracy | ⭐⭐⭐ | Depends on algorithm choice and tuning |
| Performance | ⭐⭐⭐⭐ | OpenCV is optimized; histogram is very fast |
| Integration Effort | ⭐⭐⭐ | Custom code needed; but simple Python |
| Configurability | ⭐⭐⭐⭐⭐ | Full control over algorithm and thresholds |
| Dependencies | ⭐⭐⭐⭐⭐ | OpenCV likely already available |
| Intel HW Optimization | ⭐⭐⭐ | OpenCV with Intel MKL/IPP, OpenVINO backend |
| Zero-Copy | ✅ | **Best fit** — reuses `frame.data()`, no new elements |

#### Exploration Tasks

1. Prototype histogram comparison (Bhattacharyya distance) detector
2. Prototype SSIM-based detector
3. Test both on sample videos — compare detection accuracy
4. Benchmark per-frame processing time
5. Compare accuracy against GStreamer scenechange baseline
6. Test OpenCV GPU acceleration (cv2.cuda if available)

#### References

- **OpenCV Histogram Comparison**: https://docs.opencv.org/4.x/d8/dc8/tutorial_histogram_comparison.html
- **OpenCV SSIM**: https://docs.opencv.org/4.x/d5/dc4/tutorial_video_input_psnr_ssim.html
- **OpenCV Optical Flow**: https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html
- **OpenCV Feature Matching**: https://docs.opencv.org/4.x/dc/dc3/tutorial_py_matcher.html
- **OpenCV calcHist**: https://docs.opencv.org/4.x/d6/dc7/group__imgproc__hist.html
- **OpenCV with Intel IPP**: https://www.intel.com/content/www/us/en/developer/articles/technical/opencv-ipp-integration.html
- **OpenCV with OpenVINO**: https://docs.openvino.ai/latest/openvino_docs_OV_UG_Integrate_OV_with_your_application.html

---

### Option 5: TransNetV2 (Deep Learning)

**Category**: Deep Learning Model (Batch Processing)

**Paper**: "TransNet V2: An effective deep network architecture for fast shot transition detection" (2020)

**Repository**: [github.com/soCzech/TransNetV2](https://github.com/soCzech/TransNetV2)

#### How It Works

TransNetV2 is a CNN-based model specifically designed for shot boundary detection:

1. **Input**: Sequence of video frames (typically 100-frame windows)
2. **Architecture**: 3D convolutions → frame-level predictions
3. **Output**: Per-frame probability of being a scene boundary (0.0–1.0)
4. **Post-processing**: Threshold + peak detection for final boundaries

**Key capabilities**:
- Detects **hard cuts** (abrupt transitions)
- Detects **gradual transitions** (fades, dissolves, wipes)
- Trained on large-scale datasets (ClipShots, BBC Earth)
- State-of-the-art F1 score > 0.95

#### Integration Approach

```python
# Batch pre-processing
from transnetv2 import TransNetV2

model = TransNetV2()  # or load OpenVINO IR model
video_frames, single_frame_preds, all_frame_preds = model.predict_video("video.mp4")

# Get scene boundaries
scenes = model.predictions_to_scenes(single_frame_preds)
# → [(0, 120), (121, 350), (351, 500), ...]

# Extract frames at scene boundaries for VSS pipeline
for start, end in scenes:
    representative_frame = video_frames[(start + end) // 2]
    # ... send to Minio/RabbitMQ
```

**OpenVINO conversion**:
```bash
# Convert TensorFlow model to OpenVINO IR
mo --input_model transnetv2.pb --output_dir ./openvino_model/
# Use with: from openvino.runtime import Core
```

#### Zero-Copy Impact

> **⚠️ N/A** — TransNetV2 runs as a separate batch inference pass outside the DLSPS pipeline. It processes the entire video independently and produces scene boundary timestamps. Does not interact with the GStreamer buffer chain.

#### Evaluation

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Detection Accuracy | ⭐⭐⭐⭐⭐ | SOTA: F1>0.95, handles all transition types |
| Performance | ⭐⭐ | ~50-100ms per 100 frames (GPU); slower on CPU |
| Integration Effort | ⭐⭐ | Model download, conversion, batch pipeline |
| Configurability | ⭐⭐⭐ | Threshold tuning, window size |
| Dependencies | ⭐ | TensorFlow/OpenVINO, model files (~10MB) |
| Intel HW Optimization | ⭐⭐⭐⭐⭐ | OpenVINO IR for CPU/GPU/VPU |
| Zero-Copy | ⚠️ N/A | Runs outside DLSPS pipeline |

#### Exploration Tasks

1. Clone TransNetV2 repository and download pretrained weights
2. Test inference on sample videos — evaluate detection quality
3. Convert model to OpenVINO IR format
4. Benchmark inference on Intel hardware: CPU (Xeon), iGPU, dGPU
5. Compare accuracy against SAD-based methods (GStreamer, FFmpeg)
6. Evaluate model size and Docker image impact
7. Design batch architecture: TransNetV2 pre-process → frame extraction

#### References

- **GitHub Repository**: https://github.com/soCzech/TransNetV2
- **Paper (arXiv)**: https://arxiv.org/abs/2008.04838
- **OpenVINO Model Optimizer**: https://docs.openvino.ai/latest/openvino_docs_MO_DG_prepare_model_convert_model_Convert_Model_From_TensorFlow.html
- **OpenVINO Runtime**: https://docs.openvino.ai/latest/openvino_docs_OV_UG_OV_Runtime_User_Guide.html
- **Intel OpenVINO Toolkit**: https://www.intel.com/content/www/us/en/developer/tools/openvino-toolkit/overview.html
- **Shot Boundary Detection Survey**: https://arxiv.org/abs/2106.11517
- **ClipShots Dataset**: https://github.com/Tangshitao/ClipShots

---

### Option 6: DLSPS UDFLoader Plugin

**Category**: DLSPS Extension Mechanism (Real-time, Inline)

**Source**: `dlstreamer-pipeline-server/plugins/gst-udf-loader/`

#### How It Works

DLSPS provides a `udfloader` GStreamer element that executes User-Defined Functions (UDFs) per frame. UDFs can be Python or native (C/C++) code.

**Architecture**:
```
GStreamer Pipeline:
  ... ! udfloader config="/path/to/udf_config.json" ! ...

UDF Config (JSON):
{
  "udfs": [
    {
      "name": "python.scene_detector",
      "type": "python",
      "config": { "threshold": 0.5 }
    }
  ]
}
```

**UDF receives**: GStreamer buffer + metadata
**UDF outputs**: Attached GVAJSONMeta on the buffer

#### Integration Approach

1. Implement scene detection algorithm as a Python UDF
2. UDF attaches `{"scene_change": true/false, "score": 0.73}` metadata to frames
3. Modify `Publisher.process()` to check frame metadata
4. Only emit frames with `scene_change: true`

```python
# scene_detector_udf.py
import cv2
import numpy as np

class SceneDetectorUDF:
    def __init__(self, config):
        self.threshold = config.get("threshold", 0.5)
        self.prev_hist = None

    def process(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)

        is_scene_change = False
        score = 0.0

        if self.prev_hist is not None:
            score = cv2.compareHist(self.prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)
            is_scene_change = score > self.threshold

        self.prev_hist = hist
        return {"scene_change": is_scene_change, "score": float(score)}
```

#### Zero-Copy Impact

> **⚠️ Adds element overhead** — UDFLoader inserts a new GStreamer element into the pipeline. While the UDF itself can read the buffer without copying, the element introduces per-frame Python callback overhead and an additional GStreamer element in the chain. Since `Publisher.process()` already provides the same callback mechanism via `gvapython`, using UDFLoader for scene detection is **redundant** — it duplicates the gvapython pattern without benefit.
>
> **Recommendation**: Prefer implementing scene detection directly in `Publisher.process()` (Options 2/4) instead of adding a separate UDFLoader element.

#### Evaluation

| Criterion | Rating | Notes |
|-----------|--------|-------|
| Detection Accuracy | ⭐⭐⭐ | Depends on chosen algorithm |
| Performance | ⭐⭐⭐ | Python overhead per frame (~2-5ms) |
| Integration Effort | ⭐⭐⭐⭐ | Native DLSPS mechanism |
| Configurability | ⭐⭐⭐⭐⭐ | Full Python flexibility |
| Dependencies | ⭐⭐⭐ | UDFLoader plugin must be in Docker image |
| Intel HW Optimization | ⭐⭐⭐ | Can use OpenVINO inside UDF |
| Zero-Copy | ⚠️ | Adds element — redundant with existing gvapython |

#### Exploration Tasks

1. Verify UDFLoader availability in VSS Docker image
2. Create a minimal "hello world" UDF and test pipeline integration
3. Implement histogram-based scene detection UDF
4. Measure per-frame UDF execution overhead
5. Test metadata propagation to Publisher element
6. Verify UDF config loading and parameter passing

#### References

- **UDFLoader Source**: `dlstreamer-pipeline-server/plugins/gst-udf-loader/`
- **DLSPS Pipeline Configuration**: `dlstreamer-pipeline-server/configs/`
- **DLSPS Pipeline Server Docs**: `dlstreamer-pipeline-server/README.md`
- **GVA Python Element**: https://dlstreamer.github.io/elements/gvapython.html
- **DL Streamer Documentation**: https://dlstreamer.github.io/

---

## Architecture Design: Scene-Aware Summarization

This section describes the proposed architectural design for scene-change-based frame selection. It was developed after analyzing the VSS pipeline, DLSPS zero-copy constraints, PySceneDetect algorithms, and the pipeline-manager batching/audio alignment logic.

### Dual-Mode Frame Selection

Scene change detection is introduced as an **opt-in enhancement**, not a replacement. The existing uniform sampling remains the **default mode**.

```
┌─────────────────────────────────────────────────┐
│  Frame Selection Mode (user-configurable)        │
│                                                   │
│  Mode: "uniform" (DEFAULT)                        │
│    → Current behavior, no changes                 │
│    → videorate decimates to samplingFrame/chunk    │
│    → All frames emitted, batched by multiFrame    │
│                                                   │
│  Mode: "scene_change" (OPT-IN)                    │
│    → Scene detection in Publisher.process()        │
│    → Only scene-representative frames emitted     │
│    → 1 scene = 1 chunk for VLM captioning         │
│    → Audio aligned via scene timestamps           │
└─────────────────────────────────────────────────┘
```

**Configuration surface** (proposed):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `frameSelectionMode` | `"uniform"` | Frame selection strategy: `"uniform"` or `"scene_change"` |
| `sceneChangeDetector` | `"content"` | Algorithm: `"content"`, `"adaptive"`, `"histogram"`, `"hash"`, `"threshold"` |
| `sceneChangeThreshold` | (per-detector default) | Detection sensitivity threshold |
| `minSampleInterval` | `30` | Floor rate in seconds — ensures at least 1 frame per N seconds even in long static scenes |

When `frameSelectionMode = "uniform"`, all scene-change parameters are ignored and the pipeline operates exactly as it does today.

### Scene-as-Semantic-Unit Strategy

The core insight: **a scene is the natural semantic unit for video summarization**.

Current uniform sampling is content-blind — it may send the VLM 12 nearly identical frames from a static shot while missing a brief important event between intervals. Scene change detection aligns frame selection with actual content boundaries.

```
Video timeline:
|====Scene 1 (0:00-0:45)====|==Sc2 (0:45-0:48)==|====Scene 3 (0:48-2:30)====|==Sc4==|

Uniform sampling (1f/10s):
  F@0:00  F@0:10  F@0:20  F@0:30  F@0:40  F@0:50  F@1:00 ...
  ▲──── all same desk shot ────▲    MISSED!   ▲─── whiteboard ───▲

Scene-aware sampling:
  F@0:22 (rep)     F@0:46 (rep)     F@1:30 (rep)     F@2:30 (rep)
  ▲ 1 is enough ▲  ▲ caught it! ▲   ▲ 1 is enough ▲  ▲ caught it! ▲
```

**Why this is best for summarization:**
- **No redundancy**: Static content = 1 scene = 1 frame. No wasted VLM tokens on duplicate content.
- **No missed content**: Every visual change gets a representative frame.
- **Coherent captions**: VLM sees frames from ONE visual context → focused, accurate captions.
- **Precise audio alignment**: Scene timestamps give exact time ranges → better transcript matching.
- **Natural narrative**: Summary structure mirrors video structure (scene-by-scene).

### Frame Extraction Policy

Scene change detection tells us **where** boundaries are. We still need a policy for **how many** frames to extract per scene.

**Adaptive per-scene sampling** (recommended):

```
frames_for_scene = max(1, floor(scene_duration / min_sample_interval))
```

| Scene Duration | min_sample_interval=30s | Frames Extracted |
|---------------|------------------------|------------------|
| < 30s (short) | — | 1 (representative frame) |
| 30s–60s | 30s | 1–2 |
| 2 min | 30s | 4 |
| 5 min | 30s | 10 |
| 10 min | 30s | 20 (may be capped by multiFrame) |

This ensures:
- Every scene gets at least 1 representative frame
- Long static scenes get proportional coverage (not over- or under-represented)
- Short scenes aren't inflated with redundant frames

### 1 Scene = 1 Chunk = 1 VLM Call

Each scene maps to exactly **one VLM captioning call**. This is critical for summary quality.

**Why NOT batch multiple scenes into one VLM call:**

If Scene 1 is "person at desk" and Scene 2 is "cut to whiteboard", mixing them into one VLM call produces a diluted caption:
> *"The video shows a person at a desk, then transitions to a whiteboard with diagrams"*

That's a **cross-scene summary** — the final LLM summary's job, not the per-chunk caption's job.

**Correct flow:**
```
Scene 1 (0:00-0:45) → 1-3 representative frames → VLM
  Caption: "A person sits at a desk reviewing documents, occasionally looking at their laptop"

Scene 2 (0:45-0:48) → 1 frame → VLM
  Caption: "A whiteboard showing a system architecture diagram with three connected components"

Scene 3 (0:48-2:30) → 3 frames → VLM
  Caption: "Two people discuss the architecture diagram, pointing at different components"

Final Summary (LLM composes all scene captions + audio transcripts):
  "The video begins with a person at a desk reviewing documents. They then present
   a system architecture diagram on a whiteboard, followed by a discussion with
   a colleague about the diagram's components..."
```

Each VLM caption is **focused and precise** because it only sees one visual context.

### multiFrame as Per-Scene Cap

In scene-change mode, `multiFrame` changes role from "cross-scene batch size" to **per-scene frame cap**:

```
┌─────────────────────────────────────────────────────┐
│  UNIFORM MODE (current):                             │
│    multiFrame = batch size across consecutive frames  │
│    Batch 1: [F1, F2, ..., F12] (from multiple chunks)│
│                                                       │
│  SCENE_CHANGE MODE (new):                             │
│    multiFrame = max frames per scene sent to VLM      │
│    Scene X (short):  [F1]              → 1 VLM call   │
│    Scene Y (medium): [F1, F2, F3]      → 1 VLM call   │
│    Scene Z (long):   [F1, F2, ..., F12]→ 1 VLM call   │
│    Scene W (v.long): [F1...F12] + [F13...F20] → 2 calls│
└─────────────────────────────────────────────────────┘
```

**Edge cases:**

| Scenario | Frames Extracted | multiFrame=12 | Result |
|----------|-----------------|---------------|--------|
| Short scene (2s) | 1 frame | 1 < 12 | 1 VLM call, 1 frame |
| Medium scene (45s) | 2 frames | 2 < 12 | 1 VLM call, 2 frames |
| Long scene (5 min) | 10 frames | 10 < 12 | 1 VLM call, 10 frames |
| Very long scene (10 min) | 20 frames | 20 > 12 | 2 VLM calls (12 + 8), same scene |
| 200 short scenes (trailer) | 200 frames | 1 each | 200 VLM calls (parallelizable) |

For very long scenes exceeding multiFrame, the scene is split into sub-batches — but all sub-batches are from the **same visual context**, so each VLM call remains semantically coherent.

### Audio Transcript Alignment

**Key property**: Scenes are contiguous partitions of the video timeline — there are no gaps. Every second of audio maps to exactly one scene.

```
Video:  |====Scene 1====|==Scene 2==|=======Scene 3=======|==Scene 4==|
Time:   0:00           0:45       0:48                   2:30       5:00
Audio:  [────────────────────────────────────────────────────────────────]
         ↑ all covered ↑  ↑ covered ↑  ↑    all covered    ↑ ↑covered↑
```

**No audio is ever dropped**, because every part of the video lies in some scene.

**Current audio alignment (uniform mode)**:
```typescript
// Computed from frame IDs — indirect, assumes uniform distribution
const startChunk = Math.floor((firstFrame - 1) / sampleFrames);
const startTime = startChunk * chunkDuration;
const endTime = (endChunk + 1) * chunkDuration;
```

**Scene-aware audio alignment (new)**:
```typescript
// Read directly from frame metadata — exact, no assumptions
const startTime = firstFrameMetadata.scene_start_time;
const endTime = lastFrameMetadata.scene_end_time;
```

| | Uniform Mode (current) | Scene-Change Mode (new) |
|---|---|---|
| Audio mapping | Computed from `frameId / samplingFrame × chunkDuration` | Exact from `scene.start_time` / `scene.end_time` |
| Coverage | Complete (tiles evenly) | Complete (scenes are contiguous) |
| Alignment precision | Approximate (frame may not be near paired audio) | Exact (scene timestamp defines audio window) |
| Continuity | Guaranteed | Guaranteed (no gaps between scenes) |

### Pipeline Rate Adjustment

Scene change detection requires frames at a **higher rate** than the current uniform decimation, so that short scenes aren't missed.

**Current pipeline rate**: `fps = samplingFrame / chunkDuration` (e.g., 2/10 = 0.2 fps — 1 frame per 5 seconds)

At 0.2 fps, any scene shorter than 5 seconds is invisible to the detector. The pipeline rate must be increased for detection, while only **emitting** the representative frames.

**Proposed approach**:
```
UNIFORM MODE (no change):
  videorate @ samplingFrame/chunkDuration fps → all frames emitted

SCENE_CHANGE MODE:
  videorate @ detection_fps (e.g., 2-5 fps) → scene detector sees all frames
  Publisher.process() → runs detector on each frame (~0.5-2ms overhead)
                      → only emits representative frames (much fewer than input)
                      → attaches scene metadata (scene_id, start_time, end_time)
```

The extra frames are only used for scene detection math — they are **never saved to Minio** or published to RabbitMQ. The per-frame overhead is compute only (histogram/pixel diff on the already-mapped `frame.data()` numpy array).

**Detection fps trade-off**:
| Detection FPS | Scene Resolution | Per-second Compute | Recommended For |
|--------------|------------------|-------------------|-----------------|
| 1 fps | Misses scenes < 1s | Low (~1ms) | Surveillance, lectures |
| 2 fps | Catches scenes > 0.5s | Moderate (~2ms) | General purpose |
| 5 fps | Catches scenes > 0.2s | Higher (~5ms) | Fast-cut content |

### Architectural Changes Summary

| Component | Uniform Mode (unchanged) | Scene-Change Mode (new) |
|-----------|-------------------------|------------------------|
| **GStreamer pipeline** (`config.json`) | `framerate={frame}/{chunk_duration}` | `framerate={detection_fps}/1` (higher fps for detection) |
| **Publisher** (`publish.py`) | Emit every frame | Run scene detector, emit only representative frames + scene metadata |
| **Frame metadata** (`FrameMetadata`) | `frame_timestamp`, `image_format` | + `scene_id`, `scene_start_time`, `scene_end_time`, `scene_change_score` |
| **Chunk formation** (`publish.py`) | `chunk_id = frame_id // frames_per_chunk` | `chunk_id = scene_id` |
| **prepareFrames()** (`chunking.service.ts`) | Sliding window of multiFrame across all frames | 1 scene = 1 chunk; multiFrame caps frames per scene |
| **getAudioTranscripts()** (`chunking.service.ts`) | Computed from `frameId / samplingFrame × chunkDuration` | Read from frame metadata: `scene_start_time` / `scene_end_time` |
| **EVAM service** (`evam.service.ts`) | Sends `samplingFrame`, `chunkDuration` | Sends `detection_fps`, `sceneChangeDetector`, `sceneChangeThreshold`, `minSampleInterval` |
| **Configuration** | `samplingFrame`, `chunkDuration` | + `frameSelectionMode`, `sceneChangeDetector`, `sceneChangeThreshold`, `minSampleInterval` |

---

## Evaluation Criteria

The following criteria will be used to compare options in the evaluation phase:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Detection Accuracy** | High | Ability to detect hard cuts, gradual transitions, fades, and dissolves accurately |
| **Performance** | High | Per-frame processing latency, throughput, real-time capability |
| **Zero-Copy Compatibility** | High | Must not introduce additional memory copies in the DLSPS pipeline |
| **Integration Effort** | Medium | Lines of code, architectural changes needed, time to implement |
| **Configurability** | Medium | Adjustable thresholds, sensitivity tuning, algorithm selection |
| **Dependencies** | Medium | Additional libraries, models, Docker image size impact |
| **Intel HW Optimization** | Medium | OpenVINO, VAAPI, QSV, MKL/IPP acceleration potential |
| **Maintainability** | Low | Long-term maintenance burden, community support |

### Comparison Matrix Template

| Option | Accuracy | Latency/frame | Real-time? | Zero-Copy? | Integration LOC | Dependencies | HW Accel |
|--------|----------|---------------|------------|------------|----------------|--------------|----------|
| GStreamer scenechange | TBD | TBD | ✅ | ✅ (passthrough) | TBD | None | ORC SIMD |
| PySceneDetect (inline) | TBD | TBD | ✅ | ✅ (reuses frame.data) | TBD | scenedetect | MKL |
| FFmpeg scene | TBD | TBD | ❌ | ⚠️ N/A (external) | TBD | ffmpeg | VAAPI/QSV |
| OpenCV custom (inline) | TBD | TBD | ✅ | ✅ **best fit** | TBD | cv2 (likely present) | IPP/MKL |
| TransNetV2 | TBD | TBD | ❌ | ⚠️ N/A (external) | TBD | TF/OpenVINO | OpenVINO |
| DLSPS UDFLoader | TBD | TBD | ✅ | ⚠️ adds element | TBD | UDF plugin | Flexible |

---

## Exploration Phases

### Phase 1: Environment & Baseline Setup

| # | Task | Description |
|---|------|-------------|
| 1 | **env-setup** | Verify GStreamer plugin availability, install test dependencies, collect sample videos (3+ types: static, moderate, fast-cut) |
| 2 | **baseline-metrics** | Process sample videos with current uniform sampling at various settings. Document frame counts and content coverage as baseline |

### Phase 2: Option Exploration (parallelizable)

| # | Task | Description |
|---|------|-------------|
| 3 | **explore-gst-scenechange** | Test element availability, build test pipeline, evaluate detection quality on sample videos |
| 4 | **explore-pyscenedetect** | Install, test all detectors, benchmark per-frame performance, prototype gvapython integration |
| 5 | **explore-ffmpeg** | Test `select=gt(scene,X)` with various thresholds, compare timestamps, measure processing time |
| 6 | **explore-opencv** | Prototype histogram + SSIM detector, compare accuracy and performance |
| 7 | **explore-transnetv2** | Download model, convert to OpenVINO IR, benchmark on Intel hardware, evaluate accuracy |
| 8 | **explore-udfloader** | Verify availability, create minimal UDF, test integration path |

### Phase 3: Results Documentation

| # | Task | Description |
|---|------|-------------|
| 9 | **comparison-matrix** | Compile comparison table: accuracy, performance, integration effort, dependencies |
| 10 | **recommendation-doc** | Write recommendation document with pros/cons analysis and suggested approach |

### Dependency Graph

```
env-setup
  ├── baseline-metrics
  ├── explore-gst-scenechange ──┐
  ├── explore-pyscenedetect ────┤
  ├── explore-ffmpeg ───────────┤
  ├── explore-opencv ───────────┼── comparison-matrix ── recommendation-doc
  ├── explore-transnetv2 ───────┤
  └── explore-udfloader ────────┘
```

---

## Jira Ticket

**Project**: ITEP (same as reference ITEP-90890)  
**Issue Type**: Story  
**Summary**: Introduce Intelligent Frame Selection Using Scene Change Detection in VSS Application

### Description

```
h2. Background
The VSS (Video Search and Summarization) application currently uses uniform interval-based
frame sampling during video ingestion. Frames are extracted at a constant rate
(samplingFrame / chunkDuration), which is simple but not content-aware. This leads to:
* Redundant frames in static scenes
* Missed content during rapid scene changes
* Suboptimal VLM summaries

h2. Objective
Introduce an alternative frame selection mode based on scene change detection. This will be
offered alongside the existing uniform sampling — users choose the strategy at ingestion time.

h2. Scope (Exploration Phase)
This ticket covers the exploration and evaluation of scene change detection options:

# *GStreamer scenechange element* — Native C/ORC SAD-based detection in gst-plugins-bad
# *PySceneDetect* — Python library with Content, Adaptive, Threshold, Hash detectors
# *FFmpeg scene filter* — select=gt(scene,X) filter with configurable threshold
# *OpenCV custom implementation* — Histogram comparison, SSIM, optical flow
# *TransNetV2* — Deep learning shot boundary detection (with OpenVINO optimization)
# *DLSPS UDFLoader* — Native DLSPS extension mechanism for custom Python/native UDFs

h2. Acceptance Criteria
* Each option tested with at least 3 sample videos (static, moderate, fast-cut)
* Per-option metrics documented: detection accuracy, false positive rate, per-frame latency,
  memory usage
* Comparison matrix compiled across all options
* Integration complexity assessed for each option (LOC, dependencies, architectural impact)
* Intel hardware optimization potential evaluated (OpenVINO, VAAPI, QSV)
* Recommendation document produced with clear pros/cons and suggested approach

h2. Technical Context
* Current pipeline: GStreamer → videorate → gvapython (Publisher) → Minio + RabbitMQ
* DLSPS integration via EVAM service
* Key files: video-ingestion/src/publish.py, video-ingestion/resources/conf/config.json
* Reference: GStreamer scenechange docs:
  https://gstreamer.freedesktop.org/documentation/videofiltersbad/scenechange.html
```

**Priority**: Medium  
**Labels**: `vss`, `frame-selection`, `scene-change`, `exploration`, `video-ingestion`  
**Components**: Video Search and Summarization  
**Story Points**: 8  
**Sprint**: (assign to current sprint)  
**Linked Issues**: Related to ITEP-90890
**Assignee**: (assign to yourself)

---

## References & Resources

### GStreamer

| Resource | URL |
|----------|-----|
| GStreamer scenechange element docs | https://gstreamer.freedesktop.org/documentation/videofiltersbad/scenechange.html |
| GStreamer Video Events API | https://gstreamer.freedesktop.org/documentation/video/gstvideoevent.html |
| GStreamer Plugins Bad | https://gstreamer.freedesktop.org/documentation/plugins_doc.html?gi-language=c#702883_gst-plugins-bad |
| GStreamer videorate element | https://gstreamer.freedesktop.org/documentation/videorate/index.html |
| Local source: scenechange.c | `gstreamer/subprojects/gst-plugins-bad/gst/videofilters/gstscenechange.c` |

### PySceneDetect

| Resource | URL |
|----------|-----|
| GitHub Repository | https://github.com/Breakthrough/PySceneDetect |
| Documentation | https://www.scenedetect.com/ |
| API Reference | https://www.scenedetect.com/docs/latest/api.html |
| PyPI Package | https://pypi.org/project/scenedetect/ |

### FFmpeg

| Resource | URL |
|----------|-----|
| FFmpeg select filter docs | https://ffmpeg.org/ffmpeg-filters.html#select_002c-aselect |
| FFmpeg Hardware Acceleration | https://trac.ffmpeg.org/wiki/HWAccelIntro |
| Intel QSV with FFmpeg | https://www.intel.com/content/www/us/en/developer/articles/technical/using-ffmpeg-with-intel-media-sdk.html |

### Deep Learning / TransNetV2

| Resource | URL |
|----------|-----|
| TransNetV2 GitHub | https://github.com/soCzech/TransNetV2 |
| TransNetV2 Paper (arXiv) | https://arxiv.org/abs/2008.04838 |
| Shot Boundary Detection Survey | https://arxiv.org/abs/2106.11517 |
| Intel OpenVINO Toolkit | https://www.intel.com/content/www/us/en/developer/tools/openvino-toolkit/overview.html |
| OpenVINO Model Optimizer | https://docs.openvino.ai/latest/openvino_docs_MO_DG_prepare_model_convert_model_Convert_Model_From_TensorFlow.html |

### OpenCV

| Resource | URL |
|----------|-----|
| Histogram Comparison Tutorial | https://docs.opencv.org/4.x/d8/dc8/tutorial_histogram_comparison.html |
| SSIM Tutorial | https://docs.opencv.org/4.x/d5/dc4/tutorial_video_input_psnr_ssim.html |
| Optical Flow Tutorial | https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html |
| OpenCV with Intel IPP | https://www.intel.com/content/www/us/en/developer/articles/technical/opencv-ipp-integration.html |

### DLSPS / DL Streamer

| Resource | URL |
|----------|-----|
| DL Streamer Documentation | https://dlstreamer.github.io/ |
| GVA Python Element | https://dlstreamer.github.io/elements/gvapython.html |
| Local source: UDFLoader | `dlstreamer-pipeline-server/plugins/gst-udf-loader/` |
| Local source: Pipeline Server | `dlstreamer-pipeline-server/src/server/gstreamer_pipeline.py` |

### Academic / Background

| Resource | Description |
|----------|-------------|
| [Scene Change Detection Algorithms](https://en.wikipedia.org/wiki/Shot_transition_detection) | Wikipedia overview of shot transition detection methods |
| [Video Shot Boundary Detection: A Review](https://arxiv.org/abs/2106.11517) | Comprehensive survey of SBD methods |
| [Easterbrook's Scene Detector](http://jim.easterbrook.me.uk/work/) | Original algorithm that inspired GStreamer's scenechange |

---

## Notes & Considerations

1. **Dual-mode design**: The existing uniform sampling is retained as the **default mode**. Scene change detection is an opt-in enhancement enabled by setting `frameSelectionMode: "scene_change"`. When disabled, the pipeline operates exactly as it does today — no code path changes for uniform mode.

2. **Zero-copy constraint**: DLSPS maintains a zero-copy buffer pipeline. The current VSS pipeline has a single memory copy point at `videoconvertscale` (format conversion + resize). Scene detection must **not** introduce additional copies. The recommended path is computing inside `Publisher.process()` on the existing `frame.data()` numpy array.

3. **1 scene = 1 chunk**: In scene-change mode, each detected scene maps to one VLM captioning call. This produces focused, semantically coherent captions (VLM only sees frames from one visual context). The final LLM summary composes these scene-level captions into a coherent narrative. `multiFrame` acts as a per-scene frame cap rather than a cross-scene batch size.

4. **Frame extraction policy**: Adaptive per-scene sampling: `max(1, floor(scene_duration / min_sample_interval))`. Short scenes get 1 frame; long scenes get proportional coverage capped at `multiFrame`. The `min_sample_interval` (default: 30s) ensures long static scenes still get periodic representation.

5. **Audio transcript continuity**: Scenes are contiguous partitions of the video timeline — there are no gaps. Every second of audio maps to exactly one scene. Audio alignment in scene-change mode uses exact scene timestamps from frame metadata instead of computed positions, which is more precise than the current uniform approach.

6. **Pipeline rate increase**: Scene-change mode requires a higher pipeline frame rate (2-5 fps) for detection accuracy. The extra frames are only used for detection computation — they are never saved to Minio. This increases CPU compute in `Publisher.process()` but not I/O or storage.

7. **Throughput consideration**: A video with many scene changes (e.g., 200 scenes in a trailer) produces many VLM calls. This can be mitigated by parallelizing VLM calls (scenes are independent) and by merging very short adjacent scenes below a configurable threshold.

8. **Docker image dependencies**: Any solution must fit within the existing DLSPS/VSS Docker images or justify additional image size.

9. **Testing strategy**: Use diverse video types for evaluation:
   - Static surveillance footage (few/no scene changes)
   - News broadcast (frequent hard cuts)
   - Movie trailers (fast cuts, transitions, effects)
   - Lectures/interviews (occasional scene changes)
   - Sports footage (continuous motion with replays)
