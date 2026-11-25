// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/types.hpp"

#include <cstdlib>
#include <iostream>
#include <vector>

int main() {
  using namespace optical_flow_sdk;
  std::vector<std::uint8_t> pixels(16, 42);
  ImageView view{pixels.data(), 4, 4, 0};
  view.validate();

  FlowField flow;
  flow.allocate(4, 4);
  flow.dx(1, 2) = 1.5f;
  flow.dy(1, 2) = -0.5f;
  if (flow.dx(1, 2) != 1.5f || flow.dy(1, 2) != -0.5f) {
    std::cerr << "FlowField accessors failed\n";
    return EXIT_FAILURE;
  }

  CostMap cost;
  cost.allocate(4, 4);
  cost.at(0, 0) = 7;
  if (cost.at(0, 0) != 7) {
    std::cerr << "CostMap accessors failed\n";
    return EXIT_FAILURE;
  }
  return EXIT_SUCCESS;
}
