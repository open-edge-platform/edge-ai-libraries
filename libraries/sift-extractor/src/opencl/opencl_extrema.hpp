#pragma once

#include "opencl_gaussian_pyramid.hpp"

#include <array>
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

struct ScaleSpaceKeypoint {
  RefinedKeypoint local;
  int octave = 0;
  float image_x = 0.0f;
  float image_y = 0.0f;
  float octave_sigma = 0.0f;
  float image_sigma = 0.0f;
};

struct OrientedKeypoint {
  ScaleSpaceKeypoint keypoint;
  float orientation_degrees = 0.0f;
};

struct SiftFeature {
  OrientedKeypoint point;
  std::array<float, 128> descriptor{};
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
    std::vector<ScaleSpaceKeypoint> detect_pyramid(
      const std::vector<DoGLevel> &dog_levels, int octave_count, int intervals,
      float base_sigma, float contrast_threshold, float edge_limit);
    std::vector<ScaleSpaceKeypoint> detect_image(
      const std::vector<float> &image, int width, int height, int octave_count,
      int intervals, float base_sigma, float contrast_threshold, float edge_limit);
      std::vector<OrientedKeypoint> assign_orientations(
        const GaussianLevel &level, const std::vector<ScaleSpaceKeypoint> &points);
      std::vector<SiftFeature> compute_descriptors(
        const GaussianLevel &level, const std::vector<OrientedKeypoint> &points);
        std::vector<SiftFeature> extract_image(
          const std::vector<float> &image, int width, int height, int octave_count,
          int intervals, float base_sigma, float contrast_threshold, float edge_limit);

private:
  struct Impl;
  Impl *impl_;
};

} // namespace sift_extractor::detail
