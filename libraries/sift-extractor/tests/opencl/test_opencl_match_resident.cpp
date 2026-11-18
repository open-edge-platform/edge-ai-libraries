// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "sift_extractor/opencl_extractor.hpp"

#include <cmath>
#include <cstdio>
#include <vector>

namespace {

bool Check(bool condition, const char *message) {
  std::printf("%s: %s\n", condition ? "PASS" : "FAIL", message);
  return condition;
}

} // namespace

int main() {
  using sift_extractor::OpenCLExtractor;
  using sift_extractor::OpenCLExtractorOptions;

  // Synthetic textured field large enough for extract.
  constexpr int width = 128;
  constexpr int height = 128;
  std::vector<float> image(static_cast<std::size_t>(width) * height, 0.0f);
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      const float dx = static_cast<float>(x - 40);
      const float dy = static_cast<float>(y - 40);
      image[static_cast<std::size_t>(y) * width + static_cast<std::size_t>(x)] =
          128.0f + 80.0f * std::exp(-(dx * dx + dy * dy) / 80.0f) +
          40.0f * std::exp(-((x - 90) * (x - 90) + (y - 90) * (y - 90)) / 60.0f);
    }
  }

  OpenCLExtractor extractor;
  OpenCLExtractorOptions options;
  options.octaves = 2;
  options.intervals = 3;
  options.base_sigma = 1.6f;
  options.contrast_threshold = 0.5f;
  options.edge_limit = 10.0f;
  options.max_features = 0;

  const auto features = extractor.extract(image.data(), width, height, image.size(),
                                          options);
  bool passed = Check(!features.empty(), "extract produced features");
  passed &= Check(extractor.has_resident_match(), "extract retained resident match");
  const auto matches = extractor.match_last_self();
  passed &= Check(matches.size() == features.size(),
                  "resident self-match returns one result per feature");
  if (!matches.empty()) {
    // Self-match should prefer identity for distinctive descriptors.
    int identity = 0;
    for (std::size_t i = 0; i < matches.size(); ++i)
      if (matches[i].match == static_cast<int>(i))
        ++identity;
    passed &= Check(identity > 0, "resident self-match finds some identity pairs");
    passed &= Check(std::isfinite(matches.front().score),
                    "resident self-match scores are finite");
  }
  const auto again = extractor.match_last_self();
  passed &= Check(again.size() == matches.size(),
                  "repeated resident self-match stays available");
  return passed ? 0 : 1;
}
