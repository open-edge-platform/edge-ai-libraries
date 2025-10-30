# System Requirements
This page provides detailed hardware, software, and platform requirements to help you set up and run the application efficiently.

## Hardware Platforms Used for validation
- Intel® Xeon® processor: Fourth generation and fifth generation.
- Intel® Arc™ B580 GPU with the following Intel® Xeon® processor configurations:
    - Intel® Xeon® Platinum processor 8490H
    - Intel® Xeon® Platinum processor 8468V
    - Intel® Xeon® Platinum processor 8580
- Intel® Arc™ A770 GPU with the following Intel® Core™ processor configurations:
    - Intel® Core™ Ultra 7 processor 265K
    - Intel® Core™ Ultra 9 processor 285K

## Operating Systems Used for validation
- Ubuntu OS version 22.04.2 LTS for Intel® Xeon® processor-only configurations.
- If GPU is available, refer to the official [documentation](https://dgpu-docs.intel.com/devices/hardware-table.html) for details on the required kernel version. For the listed hardware platforms, the kernel requirement translates to Ubuntu OS version 24.04 or Ubuntu OS version 24.10, depending on the GPU used.

## Minimum Configuration
The recommended minimum configuration for memory is 64 GB, and for storage is 128 GB. Further requirements is dependent on the specific configuration of the application like KV cache, context size, and etc. Any changes to the default parameters of the sample application must be assessed for memory and storage implications.

It is possible to reduce the memory to 32 GB, provided that the model configuration is also reduced. Raise an issue in the GitHub repository if you require support for smaller configurations.

## Software Requirements
The software requirements to install the sample application are provided in other documentation pages and are not repeated here.

## Compatibility Notes

**Known Limitations**:
- None

## Validation
- Ensure all dependencies are installed and configured before proceeding to [Get Started](./get-started.md).
