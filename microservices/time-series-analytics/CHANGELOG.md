# Changelog

All notable changes to this project will be documented in this file.

## [2025.2] - December 2025

### Added
- time-series-analytics: Comprehensive configuration documentation for UDFs, MQTT alerts, and OPC UA alerts ([#1337](https://github.com/open-edge-platform/edge-ai-libraries/pull/1337))
- time-series-analytics: New "How to Configure" guide with example JSON configuration ([#1337](https://github.com/open-edge-platform/edge-ai-libraries/pull/1337))
- time-series-analytics: DockerHub documentation for Docker images and Helm charts ([#1176](https://github.com/open-edge-platform/edge-ai-libraries/pull/1176))
- time-series-analytics: Device key to config to support "cpu" or "gpu" inference ([#984](https://github.com/open-edge-platform/edge-ai-libraries/pull/984))
- time-series-analytics: Root URL for routing in nginx ([#853](https://github.com/open-edge-platform/edge-ai-libraries/pull/853))
- time-series-analytics: GPU device support with Intel oneAPI integration ([#837](https://github.com/open-edge-platform/edge-ai-libraries/pull/837))

### Changed
- time-series-analytics: Updated third-party license file with updated dependency versions ([#1356](https://github.com/open-edge-platform/edge-ai-libraries/pull/1356))
- time-series-analytics: Upgraded base Docker image from kapacitor 1.7.7 to 1.8.2 ([#1356](https://github.com/open-edge-platform/edge-ai-libraries/pull/1356))
- time-series-analytics: Updated Python dependency versions across multiple licenses ([#1356](https://github.com/open-edge-platform/edge-ai-libraries/pull/1356))
- time-series-analytics: Updated helm deployment link in helm/README.md ([#1353](https://github.com/open-edge-platform/edge-ai-libraries/pull/1353))
- time-series-analytics: Removed unnecessary values from helm/values.yaml ([#1353](https://github.com/open-edge-platform/edge-ai-libraries/pull/1353))
- time-series-analytics: Updated version tag from rc1 to rc2 ([#1286](https://github.com/open-edge-platform/edge-ai-libraries/pull/1286))
- time-series-analytics: Updated to use rc1 references instead of weekly builds ([#1221](https://github.com/open-edge-platform/edge-ai-libraries/pull/1221))
- time-series-analytics: Updated image suffix from "weekly" to "rc1" in deployment configurations ([#1221](https://github.com/open-edge-platform/edge-ai-libraries/pull/1221))
- time-series-analytics: Updated minimum processor requirement documentation ([#1221](https://github.com/open-edge-platform/edge-ai-libraries/pull/1221))
- time-series-analytics: Updated helm chart version ([#1232](https://github.com/open-edge-platform/edge-ai-libraries/pull/1232))
- time-series-analytics: Updated Kapacitor version from 1.7.7 to 1.8.2 ([#1166](https://github.com/open-edge-platform/edge-ai-libraries/pull/1166))
- time-series-analytics: Adapted temperature classifier UDF for Kapacitor 1.8.2 API changes ([#1166](https://github.com/open-edge-platform/edge-ai-libraries/pull/1166))
- helm: Updated chart version from 1.0.0 to 1.1.0-weekly ([#1102](https://github.com/open-edge-platform/edge-ai-libraries/pull/1102))
- helm: Updated appVersion from "1.0.0" to "1.1.0-weekly" ([#1102](https://github.com/open-edge-platform/edge-ai-libraries/pull/1102))
- time-series-analytics: Updated architecture diagram ([#1056](https://github.com/open-edge-platform/edge-ai-libraries/pull/1056))
- time-series-analytics: Added weekly as the default image suffix ([#948](https://github.com/open-edge-platform/edge-ai-libraries/pull/948))
- time-series-analytics: Modified UDF directory naming logic to use SAMPLE_APP environment variable ([#880](https://github.com/open-edge-platform/edge-ai-libraries/pull/880))
- time-series-analytics: Added model path configuration to Kapacitor environment variables ([#880](https://github.com/open-edge-platform/edge-ai-libraries/pull/880))
- time-series-analytics: Enabled multistage Docker builds for improved efficiency and security ([#846](https://github.com/open-edge-platform/edge-ai-libraries/pull/846))
- time-series-analytics: Updated all logging to use parameterized format strings ([#846](https://github.com/open-edge-platform/edge-ai-libraries/pull/846))
- time-series-analytics: Reduced Docker image size and removed oneAPI toolkit ([#845](https://github.com/open-edge-platform/edge-ai-libraries/pull/845))
- time-series-analytics: Standardized logging format throughout codebase ([#845](https://github.com/open-edge-platform/edge-ai-libraries/pull/845))

### Fixed
- time-series-analytics: Fixed OPC UA alert error code handling to properly propagate HTTPException ([#1331](https://github.com/open-edge-platform/edge-ai-libraries/pull/1331))
- time-series-analytics: Fixed HTTP status codes for better semantic alignment ([#1284](https://github.com/open-edge-platform/edge-ai-libraries/pull/1284))
- time-series-analytics: Fixed documentation links and references in high-level architecture guide ([#1270](https://github.com/open-edge-platform/edge-ai-libraries/pull/1270))
- time-series-analytics: Fixed bandit vulnerability for usage of tmp directory ([3f9162d](https://github.com/open-edge-platform/edge-ai-libraries/commit/3f9162d312aa902b1dc40efc8c0667d024fe123b))
- time-series-analytics: Updated OPC UA server certificate name for secure mode connection ([7094004](https://github.com/open-edge-platform/edge-ai-libraries/commit/7094004f2b900d99176db0167b5747cbdaaf0a98))
- time-series-analytics: Fixed Trivy security vulnerabilities by updating FastAPI and Kubernetes security configurations ([#1175](https://github.com/open-edge-platform/edge-ai-libraries/pull/1175))
- time-series-analytics: Fixed Python linting (pylint) issues ([#839](https://github.com/open-edge-platform/edge-ai-libraries/pull/839))
- time-series-analytics: Updated variable names and removed duplicate imports ([#839](https://github.com/open-edge-platform/edge-ai-libraries/pull/839))
- time-series-analytics: Added comprehensive docstrings ([#839](https://github.com/open-edge-platform/edge-ai-libraries/pull/839))

### Removed
- time-series-analytics: Removed reference to model registry ([#1042](https://github.com/open-edge-platform/edge-ai-libraries/pull/1042))