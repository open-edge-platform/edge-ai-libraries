// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "sift_extractor/features.hpp"

#include <memory>
#include <vector>

namespace sift_extractor {

// Best / second-best descriptor match for one query feature (Lowe ratio uses
// ambiguity = second / (best + 1e-6)).
struct SiftMatchResult {
  int match = -1;
  float score = 0.0f;
  float ambiguity = 1.0f;
  float match_x = 0.0f;
  float match_y = 0.0f;
};

// OpenCL GPU self/cross matcher for host SiftFeature descriptors (upload →
// tiled float4 kernel → readback). Mirrors the SYCL MatchSiftData path.
// Repeated self-match on the same host vector keeps descriptors resident.
// match() is serialized internally (safe across threads / GIL release).
class OpenCLMatcher {
public:
  OpenCLMatcher();
  ~OpenCLMatcher();
  OpenCLMatcher(const OpenCLMatcher &) = delete;
  OpenCLMatcher &operator=(const OpenCLMatcher &) = delete;
  OpenCLMatcher(OpenCLMatcher &&) = delete;
  OpenCLMatcher &operator=(OpenCLMatcher &&) = delete;

  std::vector<SiftMatchResult> match(const std::vector<SiftFeature> &query,
                                     const std::vector<SiftFeature> &train);

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace sift_extractor
