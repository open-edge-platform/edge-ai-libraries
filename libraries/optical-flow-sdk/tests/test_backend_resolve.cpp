// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/backend.hpp"

#include <cstdlib>
#include <iostream>

int main() {
  using namespace optical_flow_sdk;
  const Backend resolved = resolve_backend(Backend::Auto);
  if (!backend_available(resolved)) {
    std::cerr << "resolved backend is unavailable\n";
    return EXIT_FAILURE;
  }
  if (backend_from_name("cpu") != Backend::Cpu) {
    std::cerr << "backend_from_name(cpu) failed\n";
    return EXIT_FAILURE;
  }
  if (preset_from_name("fast") != Preset::Fast) {
    std::cerr << "preset_from_name(fast) failed\n";
    return EXIT_FAILURE;
  }
  const auto backends = available_backends();
  if (backends.empty()) {
    std::cerr << "no backends available\n";
    return EXIT_FAILURE;
  }
  std::cout << "auto -> " << backend_name(resolved) << "\n";
  return EXIT_SUCCESS;
}
