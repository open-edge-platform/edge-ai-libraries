// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "sift_extractor/backend.hpp"
#include "sift_extractor/features.hpp"
#include "sift_extractor/version.hpp"

#if SIFT_EXTRACTOR_HAS_OPENCL
#include "sift_extractor/opencl_extractor.hpp"
#endif
#if SIFT_EXTRACTOR_HAS_SYCL
#include "sift_extractor/sycl_extractor.hpp"
#endif

#include <cstddef>
#include <memory>
#include <vector>

namespace sift_extractor {

// Dual-backend dispatch facade. OpenCL and SYCL retain distinct option contracts;
// Auto resolution is speed-biased and not a quality-floor claim.
struct ExtractorOptions {
#if SIFT_EXTRACTOR_HAS_SYCL
  SyclExtractorOptions sycl{};
#endif
#if SIFT_EXTRACTOR_HAS_OPENCL
  OpenCLExtractorOptions opencl{};
#endif
};

class Extractor {
public:
  Extractor(int width, int height, Backend backend = Backend::Auto,
            ExtractorOptions options = {});
  ~Extractor();
  Extractor(const Extractor &) = delete;
  Extractor &operator=(const Extractor &) = delete;
  Extractor(Extractor &&) = delete;
  Extractor &operator=(Extractor &&) = delete;

  Backend backend() const;
  int width() const;
  int height() const;

  // Fixed-shape grayscale FP32 extraction for the resolved backend.
  std::vector<SiftFeature> extract(const float *pixels, std::size_t element_count,
                                   std::size_t row_stride = 0);

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace sift_extractor
