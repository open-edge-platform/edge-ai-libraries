// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "opencl_gaussian_blur.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

namespace {

std::vector<float> cpu_blur(const std::vector<float> &image, int width,
                            int height, const std::vector<float> &kernel) {
  const int radius = static_cast<int>(kernel.size() / 2);
  std::vector<float> temporary(image.size());
  std::vector<float> result(image.size());

  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      float sum = 0.0f;
      for (int offset = -radius; offset <= radius; ++offset) {
        const int sample_x = std::clamp(x + offset, 0, width - 1);
        sum += image[static_cast<size_t>(y) * width + sample_x] *
               kernel[static_cast<size_t>(offset + radius)];
      }
      temporary[static_cast<size_t>(y) * width + x] = sum;
    }
  }

  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      float sum = 0.0f;
      for (int offset = -radius; offset <= radius; ++offset) {
        const int sample_y = std::clamp(y + offset, 0, height - 1);
        sum += temporary[static_cast<size_t>(sample_y) * width + x] *
               kernel[static_cast<size_t>(offset + radius)];
      }
      result[static_cast<size_t>(y) * width + x] = sum;
    }
  }
  return result;
}

} // namespace

int main() {
  constexpr int width = 73;
  constexpr int height = 59;
  const std::vector<float> kernel = {0.25f, 0.5f, 0.25f};
  std::vector<float> image(static_cast<size_t>(width) * height);
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      image[static_cast<size_t>(y) * width + x] =
          static_cast<float>((x * 37 + y * 61 + (x * y) % 251) & 255);
    }
  }

  try {
    sift_extractor::detail::OpenCLGaussianBlur blur;
    const std::vector<float> actual = blur.apply(image, width, height, kernel);
    const std::vector<float> expected = cpu_blur(image, width, height, kernel);
    float max_error = 0.0f;
    for (size_t i = 0; i < actual.size(); ++i)
      max_error = std::max(max_error, std::abs(actual[i] - expected[i]));

    std::printf("Maximum CPU/OpenCL Gaussian blur error: %.8f\n", max_error);
    if (max_error > 1e-4f) {
      std::fprintf(stderr, "OpenCL Gaussian blur differs from CPU reference\n");
      return 1;
    }
  } catch (const std::exception &error) {
    std::fprintf(stderr, "OpenCL Gaussian blur failed: %s\n", error.what());
    return 1;
  }

  return 0;
}
