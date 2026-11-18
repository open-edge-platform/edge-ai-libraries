// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/metrics.hpp"

#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>

namespace fs = std::filesystem;

int main() {
  using namespace optical_flow_sdk;
  FlowField gt;
  gt.allocate(8, 6);
  FlowField pred;
  pred.allocate(8, 6);
  for (int y = 0; y < 6; ++y) {
    for (int x = 0; x < 8; ++x) {
      gt.dx(x, y) = 2.0f;
      gt.dy(x, y) = -1.0f;
      pred.dx(x, y) = 2.5f;
      pred.dy(x, y) = -1.0f;
    }
  }
  const EpeStats stats = endpoint_error(pred, gt, 0);
  if (std::fabs(stats.mean - 0.5) > 1e-6) {
    std::cerr << "unexpected EPE mean " << stats.mean << "\n";
    return EXIT_FAILURE;
  }

  const fs::path path = fs::temp_directory_path() / "optical_flow_sdk_test.flo";
  write_flo(path.string(), gt);
  const FlowField back = read_flo(path.string());
  fs::remove(path);
  if (back.width != gt.width || back.height != gt.height) {
    std::cerr << "flo shape mismatch\n";
    return EXIT_FAILURE;
  }
  for (std::size_t i = 0; i < gt.data.size(); ++i) {
    if (back.data[i] != gt.data[i]) {
      std::cerr << "flo roundtrip mismatch\n";
      return EXIT_FAILURE;
    }
  }
  std::cout << "metrics/flo ok mean_epe=" << stats.mean << "\n";
  return EXIT_SUCCESS;
}
