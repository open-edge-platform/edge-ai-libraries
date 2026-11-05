// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "sift_extractor/features.hpp"

#include <cstddef>
#include <memory>
#include <vector>

namespace sift_extractor {

struct SyclExtractorOptions {
  int octaves = 4;
  int capacity = 32768;
  double initial_blur = 1.0;
  float contrast_threshold = 3.0f;
};

class SyclExtractor {
public:
  SyclExtractor(int width, int height, SyclExtractorOptions options = {});
  ~SyclExtractor();
  SyclExtractor(const SyclExtractor &) = delete;
  SyclExtractor &operator=(const SyclExtractor &) = delete;
  SyclExtractor(SyclExtractor &&) = delete;
  SyclExtractor &operator=(SyclExtractor &&) = delete;

  std::vector<SiftFeature> extract(const float *pixels, std::size_t element_count,
                                  std::size_t row_stride = 0);

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace sift_extractor