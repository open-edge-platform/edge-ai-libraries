// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "sift_extractor/features.hpp"
#include "sift_extractor/opencl_matcher.hpp"

#include <cstddef>
#include <memory>
#include <vector>

namespace sift_extractor {

// Public OpenCL owning extractor. Parameter defaults follow the diagnostic
// validate_sift_pair OpenCL path and are NOT equivalent to SyclExtractorOptions.
struct OpenCLExtractorOptions {
  int octaves = 4;
  int intervals = 3;
  float base_sigma = 1.6f;
  float contrast_threshold = 1.0f;
  float edge_limit = 10.0f;
  int max_features = 0;
};

class OpenCLExtractor {
public:
  OpenCLExtractor();
  ~OpenCLExtractor();
  OpenCLExtractor(const OpenCLExtractor &) = delete;
  OpenCLExtractor &operator=(const OpenCLExtractor &) = delete;
  OpenCLExtractor(OpenCLExtractor &&) = delete;
  OpenCLExtractor &operator=(OpenCLExtractor &&) = delete;

  // Grayscale FP32 pixels, tightly packed by default. Width/height may change
  // between calls. Returns the same public SiftFeature records as SyclExtractor.
  std::vector<SiftFeature> extract(const float *pixels, int width, int height,
                                   std::size_t element_count,
                                   OpenCLExtractorOptions options = {},
                                   std::size_t row_stride = 0);

  // Self-match on descriptors retained from the last extract (same OpenCL
  // context/queue). Prefer this over OpenCLMatcher for extract→match timing.
  bool has_resident_match() const;
  std::vector<SiftMatchResult> match_last_self();

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace sift_extractor
