# Release Notes

## Current Release
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
