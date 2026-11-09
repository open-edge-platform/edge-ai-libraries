// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/optical_flow.hpp"

#include <cstdlib>
#include <iostream>

int main() {
  using namespace optical_flow_sdk;
  if (algorithm_from_name("dis") != Algorithm::Dis ||
      algorithm_from_name("farneback") != Algorithm::Farneback) {
    std::cerr << "algorithm_from_name failed\n";
    return EXIT_FAILURE;
  }
  OpticalFlow dis(Backend::Cpu, Preset::Fast, Algorithm::Dis);
  OpticalFlow fb(Backend::Cpu, Preset::Fast, Algorithm::Farneback);
  if (dis.algorithm() != Algorithm::Dis || fb.algorithm() != Algorithm::Farneback) {
    std::cerr << "OpticalFlow algorithm accessor failed\n";
    return EXIT_FAILURE;
  }
  std::cout << "algorithms: " << algorithm_name(dis.algorithm()) << ", "
            << algorithm_name(fb.algorithm()) << "\n";
  return EXIT_SUCCESS;
}
