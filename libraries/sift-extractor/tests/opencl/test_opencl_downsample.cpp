// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "opencl_gaussian_blur.hpp"

#include <cstdio>
#include <vector>

int main() {
  constexpr int width = 71;
  constexpr int height = 53;
  std::vector<float> image(static_cast<size_t>(width) * height);
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x)
      image[static_cast<size_t>(y) * width + x] =
          static_cast<float>(y * width + x);
  }

  try {
    sift_extractor::detail::OpenCLGaussianBlur scale_space;
    int output_width = 0;
    int output_height = 0;
    const std::vector<float> actual = scale_space.downsample_by_two(
        image, width, height, output_width, output_height);

    bool passed = output_width == 36 && output_height == 27 &&
                  actual.size() ==
                      static_cast<size_t>(output_width) * output_height;
    for (int y = 0; y < output_height; ++y) {
      for (int x = 0; x < output_width; ++x) {
        const float expected = image[static_cast<size_t>(2 * y) * width + 2 * x];
        passed &= actual[static_cast<size_t>(y) * output_width + x] == expected;
      }
    }

    if (!passed) {
      std::fprintf(stderr, "OpenCL 2x downsample differs from CPU reference\n");
      return 1;
    }
    std::printf("OpenCL 2x downsample matches CPU reference (%dx%d -> %dx%d)\n",
                width, height, output_width, output_height);
  } catch (const std::exception &error) {
    std::fprintf(stderr, "OpenCL 2x downsample failed: %s\n", error.what());
    return 1;
  }
  return 0;
}
