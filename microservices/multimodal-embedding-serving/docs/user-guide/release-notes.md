# Release Notes: Multimodal Embedding Serving

This microservice supports features based on the requirements of Video Search and Summarization sample application, which uses this microservice. Refer to Video Search and Summarization [release notes](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/video-search-and-summarization/release-notes.html) for release details of this microservice.

## Version 2026.1.0-rc1

**14 May 2026**

**New**

- **Batched sampled-frame video pipeline**: Video embedding requests (URL, base64, local file, RTSP) now process frames through a streaming batched-frame extraction path instead of extracting all frames upfront. Frame selection priority: `frame_indexes` > `extraction_fps` > `num_frames` > `frame_interval`. Set `num_frames: 0` to process all frames in a video.
- **PyAV-based video decoder with shared memory transport**: Replaced `decord` with a custom `PyAV`-based decoder (`decoder.py`) featuring a shared memory pool (`SharedMemoryPool`) for zero-copy frame metadata transport between pipeline stages. Supports file, URL, bytes, and RTSP sources with keyframe and uniform sampling strategies.
- **RTSP multi-stream ingestion**: Multiple parallel decoder instances for concurrent RTSP and file/bytes streams in a single request.
- **Async OpenVINO inference with static shape compilation**: All model handlers now use `AsyncInferQueue`-based batched OV inference. GPU/iGPU models are compiled to a static batch shape at load time for higher hardware utilization; dynamic-size inputs are handled via padding or splitting.
- **Parallel image pre-processing**: New `ParallelImagePreprocessor` applies thread-pool-based preprocessing in parallel while preserving batch order, decoupling preprocessing latency from inference.
- **Inference metrics reporting**: All model handlers expose an optional `metrics_out=True` mode on `encode_image()` that returns timing and throughput metrics for both OV and native PyTorch execution paths.
- **Configurable embedding pipeline via environment variables**: The following variables are now exposed and seeded by `setup.sh`.

**Improvements**

- **PyTorch fallback for all model handlers**: CLIP, SigLIP, MobileCLIP, BLIP2-Transformers, and CN-CLIP handlers transparently fall back to native PyTorch inference when OpenVINO is not configured, controlled via `EMBEDDING_USE_OV`.
- Significant runtime memory reduction (up to 8–10×) and improved end-to-end throughput through the shared memory pipeline and async batched inference.
- GPU deployment defaults are now automatically applied when `EMBEDDING_DEVICE=GPU`: `OV_PERFORMANCE_MODE=THROUGHPUT`, `INFER_BATCH_SIZE=64`, `VIDEO_FRAME_BATCH_SIZE=256`.
- OpenVINO dependency bumped to `2026.1.0`; Intel GPU driver updated to `26.09.37435`.
- Detailed logger format enriched with filename, function name, and line number for easier debugging.
- `get-started.md` updated with full environment variable reference, preset configuration examples (GPU, high-throughput, memory-constrained, debug), and a performance tuning guide.

**Breaking Changes**

- `encode_image()` no longer accepts a pre-processed `torch.Tensor` as input; pass `PIL.Image` or `List[PIL.Image]` instead.
- `decord` has been removed as a dependency; replace any direct `decord` usage with `PyAV` (`av` package).

**Validated configuration**

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU, Intel® Core™ Ultra Processors (Series 2 and 3)
- Vanilla Kubernetes Cluster

## Version 1.3.2

**20 March 2026**

**New**

- Support for Intel® Core™ Ultra Processors (Series 3)
- Provided support for data and time based search queries

**Validated configuration**

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU, Intel® Core™ Ultra Processors (Series 2 and 3)
- Vanilla Kubernetes Cluster

## Previous releases

- [Release notes 2025](./release-notes/release-notes-2025.md)

<!--hide_directive
:::{toctree}
:hidden:

Release Notes 2025 <./release-notes/release-notes-2025.md>

:::
hide_directive-->
