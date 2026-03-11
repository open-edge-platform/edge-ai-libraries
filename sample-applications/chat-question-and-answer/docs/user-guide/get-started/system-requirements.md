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

## Operating Systems used for validation

- Ubuntu 22.04.2 LTS for Xeon® only configurations.
- If GPU is available, refer to the official [documentation](https://dgpu-docs.intel.com/devices/hardware-table.html) for details on required kernel version. For the listed hardware platforms, the kernel requirement translates to Ubuntu 24.04 or Ubuntu 24.10 depending on the GPU used.
- Validation on EMT 3.0 has been done.

## Minimum Configuration

The recommended minimum configuration depends on the model serving used.

- For OVMS based deployment, recommendation for memory is 64GB and storage is 128 GB. This is applicable for both Ubuntu and EMT 3.0.
- For vLLM based deployment, recommendation for memory is 128GB. Minimum storage is 128GB, but check based on the model configuration. Memory configuration can be reduced by changing the default KV_CACHE_SPACE to a lower value. Lower KV_CACHE has impact on the performance and accuracy of the pipeline. This is applicable for both Ubuntu and EMT 3.0. (*vLLM is deprecated effective 2025.2.0*)
- For TGI based deloyment on EMT 3.0, recommendation is to run it on Xeon® based systems. TGI on Core&trade; is observed to take a long time to startup with no guarantee that it will be functional. No such limitations on Ubuntu based systems for TGI. (*TGI is deprecated effective 2025.2.0*)

Further requirements is dependent on the specific configuration of the application like KV cache, context size etc. Any changes to the default parameters of the sample application should be assessed for memory and storage implications. Raise a git issue in case of any required support for smaller configurations.

## Software Requirements

The software requirements to install the sample application are provided in other documentation pages and is not repeated here.

## Compatibility Notes

**Known Limitations**:

- None

## Validation

- Ensure all dependencies are installed and configured before proceeding to [Get Started](../get-started.md).
