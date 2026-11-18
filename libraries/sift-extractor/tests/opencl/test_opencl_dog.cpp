// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "opencl_gaussian_blur.hpp"

#include <cmath>
#include <cstdio>
#include <vector>

int main() {
  constexpr int width = 71;
  constexpr int height = 53;
  std::vector<float> first(static_cast<size_t>(width) * height);
  std::vector<float> second(first.size());
  for (size_t i = 0; i < first.size(); ++i) {
    first[i] = static_cast<float>(i % 257) * 0.25f;
    second[i] = static_cast<float>((i * 3) % 191) * 0.125f;
  }

  try {
    sift_extractor::detail::OpenCLGaussianBlur scale_space;
    const std::vector<float> actual =
        scale_space.difference_of_gaussians(first, second, width, height);
    float max_error = 0.0f;
    for (size_t i = 0; i < actual.size(); ++i) {
      const float expected = first[i] - second[i];
      const float error = std::abs(actual[i] - expected);
      if (error > max_error)
        max_error = error;
    }

    std::printf("Maximum CPU/OpenCL DoG error: %.8f\n", max_error);
    if (max_error != 0.0f) {
      std::fprintf(stderr, "OpenCL DoG differs from CPU reference\n");
      return 1;
    }
  } catch (const std::exception &error) {
    std::fprintf(stderr, "OpenCL DoG failed: %s\n", error.what());
    return 1;
  }
  return 0;
}
