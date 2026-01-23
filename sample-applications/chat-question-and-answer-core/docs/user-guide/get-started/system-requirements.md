# System Requirements

This page provides detailed hardware, software, and platform requirements to help you set up and run the application efficiently.

## Hardware Platforms used for validation

- Intel® Xeon®: Fourth generation and fifth generation.
- Intel® Arc&trade; B580 GPU with following Xeon® processor configurations:
  - Intel® Xeon® Platinum 8490H
  - Intel® Xeon® Platinum 8468V
  - Intel® Xeon® Platinum 8580
- Intel® Arc&trade; A770 GPU with following Core&trade; configurations:
  - Intel® Core&trade; Ultra 7 265K
  - Intel® Core&trade; Ultra 9 285K
- Intel® Core&trade; Ultra 7 256V
- Intel® Core&trade; Ultra 7 165H

## Operating Systems used for validation

- Ubuntu 22.04.2 LTS for Xeon® only configurations.
- If GPU is available, refer to the official [documentation](https://dgpu-docs.intel.com/devices/hardware-table.html) for details on required kernel version. For the listed hardware platforms, the kernel requirement translates to Ubuntu 24.04 or Ubuntu 24.10 depending on the GPU used.

## Minimum Configuration

The recommended minimum configuration for memory is 16GB and storage is 64 GB. Further requirements is dependent on the specific configuration of the application like KV cache, context size etc. Any changes to the default parameters of the sample application should be assessed for memory and storage implications.

## Software Requirements

The software requirements to install the sample application are provided in other documentation pages and is not repeated here.

## Compatibility Notes

**Known Limitations**:

- None

## Validation

- Ensure all dependencies are installed and configured before proceeding to [Get Started](./get-started.md).
