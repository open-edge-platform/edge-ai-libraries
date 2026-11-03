// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace sift_extractor {

struct OpenCLDeviceInfo {
  std::string platform_name;
  std::string platform_version;
  std::string name;
  std::string vendor;
  std::string version;
  std::string driver_version;
  std::size_t compute_units = 0;
  std::size_t global_memory_bytes = 0;
  std::size_t local_memory_bytes = 0;
  bool image_support = false;
};

std::vector<OpenCLDeviceInfo> enumerate_opencl_devices();

} // namespace sift_extractor
