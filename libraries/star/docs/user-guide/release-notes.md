# Release Notes: Semantic Compression Toolbox with Adaptive Rate

## Version 2026.3.0

**Release Date:** December 7, 2026

This is the initial release of the Semantic Compression Toolbox with Adaptive Rate.

**New**:

- **Semantic image compression pipeline**: Decomposes each frame into semantic objects and a
  background, encodes each part with the cheapest codec that meets a byte budget, and
  reconstructs a composite image on the receiving side.
- **Four integration modes**: Supports a direct file-transfer path, an external streaming source
  plugged in through the in-memory `SemanticCodecBridge` API, an HTTP-based service, and a
  TCP-based service.
- **Adaptive pipeline manager**: Re-plans the encoding strategy for every frame based on queue
  backlog, with graceful degradation tiers, hysteresis, and adaptive compression-rate tuning.
- **Two compression levels**: Provides separate scaling ranges, target rates, and codec sets for
  each level. You can include, exclude, and reorder codecs for the background and objects.
- **Multiple codecs with byte-budget-driven fallback**: Supports AV1 Image File Format (AVIF),
  low-bit, mask-aware, structure-aware, and symbolic codecs, which the encoder tries in the
  configured order until the target payload size is met.
- **Tiled YOLO object detection**: Supports tiled inference with cross-tile non-maximum
  suppression for large imagery, and OpenVINO™ INT8 models. You can run inference on a CPU or a
  Neural Processing Unit (NPU), or use Deep Learning Streamer Pipeline Server (DL Streamer
  Pipeline Server) as the detector backend.
- **Flexible detection input**: Allows skipping object detection entirely or reusing
  pre-computed annotations from a JSON file or a directory of YOLO-style labels.
- **Multi-directory input catalogs**: Reads images from several directories listed in a YAML
  catalog, with uniform or proportional sampling.
- **Input data rate and run duration limiting**: Emulates a bandwidth-constrained image source
  and enables bounded benchmark runs.
- **Dockerized deployment**: Runs the encoder and decoder in containers on one machine or on
  separate machines, or locally in Python. Containers provide health check endpoints.
- **Structured logging and evaluation tools**: Provides Newline-Delimited JSON (NDJSON) logs,
  the `summarize_logs` offline summarizer with plots, semantic and cosine similarity metrics,
  and side-by-side composite viewers.
- **Detector fine-tuning helpers**: Provides dataset split and remap utilities for fine-tuning
  the object detector.

