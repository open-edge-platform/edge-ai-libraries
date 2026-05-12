# Changelog

All notable changes to this project will be documented in this file.

## [2026.1] - June 2026

### Added
- Added optional CPU core-pinning support via `CORE_PINNING` environment variable using a new `run.sh` entrypoint and `detect-cores.sh` script. ([#2087])
- Added `/udfs/package` API endpoint to upload and extract UDF deployment packages (tar archives) via HTTP. ([#2067])

### Changed
- Updated Kapacitor version. ([#2140])
- Updated Intel GPU drivers to support WCL (compute-runtime/IGC `26.14.37833`). ([#2145]) ([#2128])
- Replaced `pkill`-based Kapacitor shutdown with a `/proc`-based process discovery approach to terminate the Kapacitor daemon. ([#2104])
- Switched UDF package upload format from `.zip` to `.tar` archives across endpoint, functional tests, and documentation. ([#2100])
- Changed base Docker image from `kapacitor:<version>` to `python:<version>-slim` with Kapacitor installed via `.deb`. ([#2098])
- Renamed Helm chart from `time-series-analytics-microservice` to `ia-time-series-analytics-microservice` to align with Docker Hub namespace. ([#1830])
- Updated third-party programs file with latest dependency versions. ([#2046])
- Bumped `requests` dependency version. ([#2062])

### Fixed
- Fixed security vulnerability by bumping `python-multipart`, `pytest`, `pytest-cov`, `pytest-asyncio`, and `pytest-html` dependency versions. ([#2151])
- Fixed OPC UA alert sending failures by adding server hostname resolution, improved connection-state tracking, and more resilient re-initialization logic. ([#2124])
- Fixed config update handler to remove the `alerts` key from in-memory configuration when the incoming payload omits alerts. ([#2099])

### Documentation
- Reviewed and updated Time Series Analytics documentation. ([#2153])
- Updated simulator setup steps to use a Python virtual environment. ([#1830])
- Fixed release notes article structure and consolidated release notes navigation. ([#1908])
- Updated release notes links and references. ([#1916])
- Updated reference links across documentation (ref sweep). ([#2038])
- Fixed documentation links and references (pass 2). ([#1971])

---

[#2153]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2153
[#2151]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2151
[#2145]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2145
[#2140]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2140
[#2128]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2128
[#2124]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2124
[#2104]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2104
[#2100]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2100
[#2099]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2099
[#2098]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2098
[#2087]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2087
[#2067]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2067
[#2062]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2062
[#2046]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2046
[#2038]: https://github.com/open-edge-platform/edge-ai-libraries/pull/2038
[#1971]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1971
[#1916]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1916
[#1908]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1908
[#1830]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1830

## [2026.0] - March 2026

### Added
- Added check to validate UDF availability before updating config. ([#1954])

### Changed
- Updated Kapacitor base image from v1.8.2 to v1.8.3. ([#1946])
- Updated Python library dependency versions. ([#1901])
- Updated Time Series Analytics image versioning and standardized tag format across Docker Compose and Helm configurations. ([#1727])
- Updated Helm chart versioning scheme to include `-helm` suffix and aligned chart metadata/docs. ([#1814])
- Removed Model Registry references from Time Series Analytics documentation/content. ([#1766])
- Updated production-usage guidance for Ubuntu-based prebuilt images to direct users toward self-built production images. ([#1635])

### Fixed
- Fixed PTL GPU access issue by pinning specific Intel compute runtime and graphics compiler package versions. ([#1603])
- Fixed functionality issues in `rest_api_utils.py` and `test_docker.py`. ([#1625])
- Fixed unit test issues in Time Series Analytics. ([#1598])
- Bumped `protobuf` from `6.31.1` to `6.33.5`. ([#1771])

### Documentation
- Updated release branch references and documentation links. ([#1993], [#1974], [#1955], [#1867])
- Fixed release notes documentation for 2026.0. ([#1961], [#1909], [#1837])
- Updated step to run simulator in virtual environment. ([#1829])
- Added missing documentation reference links from release-2025.2 branch. ([#1582])
- Reorganized AI Libraries component documentation. ([#1797])
- Reorganized Time Series Analytics toctree/navigation. ([#1712])
- Fixed Time Series Analytics toctree issues. ([#1634])
- Added docs link blocks and index updates for markdown docs. ([#1624])

---

[#1993]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1993
[#1974]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1974
[#1961]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1961
[#1955]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1955
[#1954]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1954
[#1946]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1946
[#1909]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1909
[#1901]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1901
[#1867]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1867
[#1837]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1837
[#1829]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1829
[#1814]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1814
[#1797]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1797
[#1771]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1771
[#1766]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1766
[#1727]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1727
[#1712]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1712
[#1635]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1635
[#1634]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1634
[#1625]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1625
[#1624]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1624
[#1603]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1603
[#1598]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1598
[#1582]: https://github.com/open-edge-platform/edge-ai-libraries/pull/1582

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
