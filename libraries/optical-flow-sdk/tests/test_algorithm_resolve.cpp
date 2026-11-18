// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/optical_flow.hpp"
#include "optical_flow_sdk/sea_raft.hpp"

#include <cstdlib>
#include <iostream>

int main() {
  using namespace optical_flow_sdk;
  if (algorithm_from_name("dis") != Algorithm::Dis ||
      algorithm_from_name("farneback") != Algorithm::Farneback ||
      algorithm_from_name("sea-raft") != Algorithm::SeaRaft) {
    std::cerr << "algorithm_from_name failed\n";
    return EXIT_FAILURE;
  }
  OpticalFlow dis(Backend::Cpu, Preset::Fast, Algorithm::Dis);
  OpticalFlow fb(Backend::Cpu, Preset::Fast, Algorithm::Farneback);
  if (dis.algorithm() != Algorithm::Dis || fb.algorithm() != Algorithm::Farneback) {
    std::cerr << "OpticalFlow algorithm accessor failed\n";
    return EXIT_FAILURE;
  }
  // SeaRaft constructs only when OpenVINO+model are available; name parse is enough here.
  std::cout << "algorithms: " << algorithm_name(dis.algorithm()) << ", "
            << algorithm_name(fb.algorithm()) << ", "
            << algorithm_name(Algorithm::SeaRaft)
            << " available=" << (sea_raft_available() ? "yes" : "no") << "\n";
  return EXIT_SUCCESS;
}
