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

struct RefinedKeypoint {
  float x = 0.0f;
  float y = 0.0f;
  float scale = 0.0f;
  float response = 0.0f;
  float edge_response = 0.0f;
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
  std::vector<RefinedKeypoint> refine(
      const std::vector<DoGLevel> &dog_levels,
      const std::vector<ExtremaCandidate> &candidates,
      float contrast_threshold, float edge_limit);

private:
  struct Impl;
  Impl *impl_;
};

} // namespace sift_extractor::detail
