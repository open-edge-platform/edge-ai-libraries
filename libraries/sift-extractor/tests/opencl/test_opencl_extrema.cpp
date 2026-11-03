// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "opencl_extrema.hpp"

#include <algorithm>
#include <cstdio>
#include <vector>

int main() {
  constexpr int width = 17;
  constexpr int height = 15;
  std::vector<sift_extractor::detail::DoGLevel> dog(3);
  for (int scale = 0; scale < 3; ++scale) {
    dog[static_cast<size_t>(scale)].octave = 0;
    dog[static_cast<size_t>(scale)].scale = scale;
    dog[static_cast<size_t>(scale)].width = width;
    dog[static_cast<size_t>(scale)].height = height;
    dog[static_cast<size_t>(scale)].pixels.assign(
        static_cast<size_t>(width) * height, 0.0f);
  }
  auto &center = dog[1].pixels;
  center[static_cast<size_t>(7) * width + 6] = 9.0f;
  center[static_cast<size_t>(9) * width + 11] = -8.0f;
  center[static_cast<size_t>(0) * width + 0] = 20.0f;

  try {
    sift_extractor::detail::OpenCLDoGExtrema detector;
    auto candidates = detector.detect(dog, 1.0f);
    std::sort(candidates.begin(), candidates.end(),
              [](const auto &left, const auto &right) {
                if (left.y != right.y)
                  return left.y < right.y;
                return left.x < right.x;
              });

    const bool passed =
        candidates.size() == 2 && candidates[0].x == 6 && candidates[0].y == 7 &&
        candidates[0].scale == 1 && candidates[0].response == 9.0f &&
        candidates[1].x == 11 && candidates[1].y == 9 &&
        candidates[1].scale == 1 && candidates[1].response == -8.0f;
    std::printf("OpenCL 3D extrema candidates: %zu\n", candidates.size());
    if (!passed) {
      std::fprintf(stderr, "3D extrema result did not match CPU reference\n");
      return 1;
    }
  } catch (const std::exception &error) {
    std::fprintf(stderr, "OpenCL extrema detection failed: %s\n", error.what());
    return 1;
  }
  return 0;
}
