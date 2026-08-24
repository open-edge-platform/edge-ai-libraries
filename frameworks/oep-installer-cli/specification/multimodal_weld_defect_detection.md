# Component spec: multimodal_weld_defect_detection

## Purpose

[Multimodal Weld Defect Detection](https://github.com/open-edge-platform/edge-ai-suites/tree/main/manufacturing-ai-suite/industrial-edge-insights-multimodal) is an example to use Open Edge Platform time-series service to defect weld defection during the manufacturing process. 

## Installation order / category

This is a sample application.

## Dependencies

- `git`
- `curl`
- `docker`
- `edge_base`

## Installation steps

**Upstream repository**: `https://github.com/open-edge-platform/edge-ai-suites.git`  
**Version / tag**: `release-2026.2.0`

1. Pull the repository and sparse checkout manufacturing-ai-suite/industrial-edge-insights-multimodal to the workspace
   `$(ensure_project_path)/industrial-edge-insights-multimodal`.  
2. The installation instructions is documented [here](https://github.com/open-edge-platform/edge-ai-suites/blob/main/manufacturing-ai-suite/industrial-edge-insights-multimodal/docs/user-guide/get-started.md). Skip the docker installation instructures as docker is installed by the `docker` dependency. 
3. The installation should include setup steps and pre-pull any docker images such that the sample is ready to start.  

## Verification

1. Verify the sample workspace exists. 
2. Verify that the docker images required to start the sample is downloaded. 

## Start / stop behaviour

See the start/stop instructions under [Getting Started](https://github.com/open-edge-platform/edge-ai-suites/blob/main/manufacturing-ai-suite/industrial-edge-insights-multimodal/docs/user-guide/get-started.md).

| Port  | Protocol | Purpose                        |
|-------|----------|--------------------------------|
| 15443 | TCP      | The grafana port |
| 3478 | TCP      | The coturn port |
| 3478 | UDP      | The coturn port |
| 8200 | TCP      | The model downloader port |
| 8010 | TCP      | The LLM service port |

## Removal

Stop the sample, and remove the sample workspace.

## License requirements

N/A

