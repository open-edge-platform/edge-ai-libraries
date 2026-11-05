// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "sift_extractor/opencl_device.hpp"

#include <cstdio>

int main() {
  try {
    const auto devices = sift_extractor::enumerate_opencl_devices();
    if (devices.empty()) {
      std::fprintf(stderr, "No OpenCL devices are available\n");
      return 1;
    }

    for (const auto &device : devices) {
      std::printf("%s | %s | %s | driver %s | CUs %zu | global %zu | local %zu | images %s\n",
                  device.platform_name.c_str(), device.name.c_str(),
                  device.version.c_str(), device.driver_version.c_str(),
                  device.compute_units, device.global_memory_bytes,
                  device.local_memory_bytes,
                  device.image_support ? "yes" : "no");
      if (device.name.empty() || device.vendor.empty() ||
          device.driver_version.empty() || device.compute_units == 0) {
        std::fprintf(stderr, "OpenCL device information is incomplete\n");
        return 1;
      }
    }
  } catch (const std::exception &error) {
    std::fprintf(stderr, "OpenCL enumeration failed: %s\n", error.what());
    return 1;
  }

  return 0;
}
