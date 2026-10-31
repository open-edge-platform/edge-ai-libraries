#pragma once

#include "opencl_gaussian_pyramid.hpp"

#include <vector>

namespace sift_extractor::detail {

struct ExtremaCandidate {
  int x = 0;
  int y = 0;
  int scale = 0;
  float response = 0.0f;
};

class OpenCLDoGExtrema {
public:
  OpenCLDoGExtrema();
  ~OpenCLDoGExtrema();

  OpenCLDoGExtrema(const OpenCLDoGExtrema &) = delete;
  OpenCLDoGExtrema &operator=(const OpenCLDoGExtrema &) = delete;
  OpenCLDoGExtrema(OpenCLDoGExtrema &&) = delete;
  OpenCLDoGExtrema &operator=(OpenCLDoGExtrema &&) = delete;

  std::vector<ExtremaCandidate> detect(const std::vector<DoGLevel> &dog_levels,
                                       float contrast_threshold);

private:
  struct Impl;
  Impl *impl_;
};

} // namespace sift_extractor::detail
