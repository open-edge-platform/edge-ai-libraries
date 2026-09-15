# System Requirements

This page lists the hardware, software, and platform requirements for running the Agentic Predictive Maintenance (APM) blueprint.

## Hardware Platforms Used for Validation

- Intel® Xeon® processor: Fourth and fifth generation
- Intel® Arc™ GPU (A-series and B-series) with compatible Intel® Xeon® or Intel® Core™ processor
- Intel® Core™ Ultra processors with integrated GPU (suitable for smaller pipelines and fallback mode)

GPU support is required only for **LLM mode**. The **fallback mode** (rule-based) runs on CPU alone.

## Operating Systems Used for Validation

- Ubuntu 22.04 LTS for CPU-only configurations
- Ubuntu 24.04 LTS when using discrete GPU hardware
- Refer to the [Intel GPU driver documentation](https://dgpu-docs.intel.com/devices/hardware-table.html) for specific kernel requirements per GPU model.

## Minimum Hardware Configuration

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 16 GB | 32 GB |
| Storage | 50 GB | 100 GB |
| CPU | Any Intel® Xeon® or Core™ | Intel® Xeon® 4th Gen or later |
| GPU | Not required (fallback mode) | Intel® Arc™ for LLM mode |

## Software Requirements

| Software | Version |
|----------|---------|
| Docker | ≥ 24.0 |
| Docker Compose | ≥ 2.20 |
| Python | ≥ 3.10 (for data preparation only) |

## Compatibility Notes

**Known Limitations**:

- NPU inference is available as an experimental option for the LLM service but is not validated for all model and configuration combinations.
- Intel® Core™ Ultra 2 and 3 with integrated GPU can run the application but model selection significantly affects performance.

## Validation

Ensure Docker and Docker Compose are installed and running before following the [Get Started](../get-started.md) guide.
