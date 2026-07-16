# Release Notes

## Current Release

**Version**: 2026.2

This release moves the pipeline to **on-device AI services** and adds runtime-extensible prompt tasks and subtitle-aware summarization.

**New in this release**

- **On-device AI Services**: vLLM-IPEX-serving and multilevel-video-understanding run locally on a single Intel PTL 358H host with shared system RAM — no discrete accelerator or remote inference cluster. A single `Qwen3.5-35B-A3B` model serves both the VLM (captioning) and LLM (aggregation) roles from one OpenAI-compatible endpoint.
- **Dynamic prompt tasks**: register/update/delete custom summarization tasks at runtime via the `/v1/tasks` API. Two built-in tasks ship by default — `summary` (English) and `summary_zh` (Chinese); everything else is user-registered.
- **Subtitle-aware summarization**: pass subtitles alongside a video for extra per-chunk context, or run **caption-only** mode (`video: "none"` + subtitles) to summarize a pre-built event log without any VLM inference.
- **Single env file**: all deployment variables consolidated in `docker/set_env.sh`, with a default 64 GB / 32 GB-swap on-device profile.

**HW used for validation**:

- Intel® Core™ Ultra (Panther Lake, PTL 358H) with integrated GPU sharing system RAM
- 64 GB system RAM + 32 GB swap

## Previous Releases

**Version**: 2025.2

This is the first release for multilevel video understanding. This microservice implements a novel multi-level framework designed specifically for video summarization, with specialized capabilities for processing long-form video content.

**Features**

- Process video from local files or http(s) links.
- Containerization with Docker.
- RESTful API with FastAPI with support for concurrent requests.
- Support specify video chunking method in user requests.
- Support specify multi-level settings in user requests.
- Support specify temporal enhancement settings in user requests.
- Designed to work effortlessly with GenAI model servings that provide OpenAI-compatible APIs.

**HW used for validation**:

- Intel® Xeon™ GOLD 6530
- Intel® Arc™ Pro B60 Graphics * 4
