# System Requirements
This section provides detailed hardware, software, and platform requirements to help you set up and run the application efficiently.


## Hardware Platforms Used for Validation
- Intel® Xeon® processor: Fourth and fifth generation.
- Intel® Arc™ B580 Graphics GPU with following Intel Xeon processor configurations:
    - Intel Xeon Platinum 8490H processor
    - Intel Xeon Platinum 8468V processor
    - Intel Xeon Platinum 8580 processor
- Intel® Arc™ A770 Graphics GPU with following Intel® Core™ processor configurations:
    - Intel Core Ultra 7 Processor 265
    - Intel Core Ultra 9 Processor 285

## Operating Systems Used for Validation
- Ubuntu 22.04.2 LTS OS for Intel Xeon configurations only.
- If GPU is available, see the official [documentation](https://dgpu-docs.intel.com/devices/hardware-table.html) for details on required kernel version. For the listed hardware platforms, the kernel requirement translates to Ubuntu 24.04 or Ubuntu 24.10 OS, depending on the GPU used.

## Minimum Configuration
Intel recommends the minimum memory configuration of 64 GB, and minimum storage of 128 GB. Further requirements is dependent on the specific configuration of the application like KV cache, context size, and etc. If the default parameters of the sample application are changed, you must assess the memory and storage implications.

If the model configuration is reduced, you can reduce the memory size to 32 GB. If you need support for smaller configurations, raise an issue through the GitHub repository.

## Software Requirements

The software requirements to install the sample application are provided in other documentation pages and is not repeated here.

## Compatibility Notes

**Known Limitations**:
- None


## Validation
- Ensure that you have installed and configured all dependencies before proceeding to [Get Started](./get-started.md).
