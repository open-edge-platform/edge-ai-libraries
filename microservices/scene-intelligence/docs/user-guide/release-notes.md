# Release Notes

## Current Release: 1.0.0

**Release Date**: 2025-08-19

### Features

- **Real-time Traffic Analysis**: Comprehensive directional traffic density monitoring with MQTT integration
- **VLM Integration**: Vision Language Model powered traffic scene analysis with sustained traffic detection
- **Sliding Window Analysis**: 15-second sliding window with 3-second sustained threshold for accurate traffic state detection
- **Camera Image Management**: Intelligent camera image retention and coordination between API and VLM services
- **RESTful API**: Complete HTTP API for traffic summaries, intersection monitoring, and VLM analysis retrieval

### Improvements

- **Concurrency Control**: Semaphore-based VLM worker management for optimal resource utilization
  - **Impact**: Prevents VLM service overload and ensures reliable traffic analysis
- **Image Retention Logic**: Camera images persist with VLM analysis for consistent data correlation
  - **Impact**: API responses show actual images analyzed by VLM, improving traceability and debugging
- **Enhanced Error Handling**: Comprehensive error management across MQTT, VLM, and image services
  - **Impact**: Improved service reliability and diagnostic capabilities

### Technical Specifications

- **Supported Languages**: Python 3.10+
- **Architecture**: Microservice with Docker containerization
- **Dependencies**: FastAPI, MQTT client, aiohttp, structlog
- **External Integrations**: MQTT brokers, VLM OpenVINO serving, camera image streams
