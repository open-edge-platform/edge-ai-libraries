// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "sift_extractor/opencl_matcher.hpp"

#include <cmath>
#include <cstdio>
#include <vector>

namespace {

bool Check(bool condition, const char *message) {
  std::printf("%s: %s\n", condition ? "PASS" : "FAIL", message);
  return condition;
}

sift_extractor::SiftFeature Basis(int dimension, float x,
                                                float y) {
  sift_extractor::SiftFeature feature;
  feature.x = x;
  feature.y = y;
  feature.descriptor[static_cast<std::size_t>(dimension)] = 1.0f;
  return feature;
}

} // namespace

int main() {
  using sift_extractor::OpenCLMatcher;
  using sift_extractor::SiftFeature;

  constexpr int count = 4;
  std::vector<SiftFeature> first;
  std::vector<SiftFeature> second;
  first.reserve(count);
  second.reserve(count);
  for (int i = 0; i < count; ++i) {
    first.push_back(Basis(i, static_cast<float>(i + 1),
                          static_cast<float>(i + 2)));
    second.push_back(Basis(i, static_cast<float>(10 + i),
                           static_cast<float>(20 + i)));
  }

  OpenCLMatcher matcher;
  const auto results = matcher.match(first, second);

  bool passed = results.size() == static_cast<std::size_t>(count);
  passed &= Check(passed, "matcher returns one result per query");
  for (int i = 0; i < count; ++i) {
    passed &= Check(results[static_cast<std::size_t>(i)].match == i,
                    "orthogonal descriptors match their identical basis");
    passed &=
        Check(std::abs(results[static_cast<std::size_t>(i)].score - 1.0f) <
                  1e-5f,
              "best descriptor score is one");
    passed &= Check(results[static_cast<std::size_t>(i)].match_x ==
                            second[static_cast<std::size_t>(i)].x &&
                        results[static_cast<std::size_t>(i)].match_y ==
                            second[static_cast<std::size_t>(i)].y,
                    "matched keypoint coordinates are copied");
  }
  return passed ? 0 : 1;
}
