// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "sift_extractor/opencl_extractor.hpp"

#include "opencl_extrema.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace sift_extractor {

struct OpenCLExtractor::Impl {
  detail::OpenCLDoGExtrema detector;
};

OpenCLExtractor::OpenCLExtractor() : impl_(std::make_unique<Impl>()) {}
OpenCLExtractor::~OpenCLExtractor() = default;

std::vector<SiftFeature> OpenCLExtractor::extract(const float *pixels, int width,
    int height, std::size_t element_count, OpenCLExtractorOptions options,
    std::size_t row_stride) {
  if (width < 32 || width > 3840 || height < 32 || height > 2160 ||
      options.octaves < 1 || options.octaves > 6 ||
      options.intervals < 1 || options.intervals > 32 ||
      !std::isfinite(options.base_sigma) || options.base_sigma < 0.1f ||
      options.base_sigma > 16.0f || !std::isfinite(options.contrast_threshold) ||
      options.contrast_threshold < 0.0f || !std::isfinite(options.edge_limit) ||
      options.edge_limit <= 0.0f || options.max_features < 0)
    throw std::invalid_argument("Invalid OpenCL extractor dimensions or options");
  if (!row_stride) row_stride = static_cast<std::size_t>(width);
  const auto width_u = static_cast<std::size_t>(width);
  const auto rows_before_last = static_cast<std::size_t>(height - 1);
  if (!pixels || row_stride < width_u ||
      row_stride > (std::numeric_limits<std::size_t>::max() - width_u) / rows_before_last ||
      element_count < rows_before_last * row_stride + width_u)
    throw std::invalid_argument("Invalid OpenCL extractor input buffer or stride");

  std::vector<float> packed;
  packed.resize(width_u * static_cast<std::size_t>(height));
  for (int row = 0; row < height; ++row) {
    const float *source = pixels + static_cast<std::size_t>(row) * row_stride;
    if (!std::all_of(source, source + width, [](float value) { return std::isfinite(value); }))
      throw std::invalid_argument("OpenCL extractor input must be finite");
    std::copy_n(source, width_u, packed.begin() + static_cast<std::size_t>(row) * width_u);
  }

  const auto native = impl_->detector.extract_image(
      packed, width, height, options.octaves, options.intervals, options.base_sigma,
      options.contrast_threshold, options.edge_limit, options.max_features);
  std::vector<SiftFeature> features;
  features.reserve(native.size());
  for (const auto &feature : native) {
    SiftFeature out;
    out.x = feature.point.keypoint.image_x;
    out.y = feature.point.keypoint.image_y;
    out.scale = feature.point.keypoint.image_sigma;
    out.orientation_degrees = feature.point.orientation_degrees;
    out.response = feature.point.keypoint.local.response;
    out.descriptor = feature.descriptor;
    features.push_back(out);
  }
  return features;
}

bool OpenCLExtractor::has_resident_match() const {
  return impl_->detector.has_resident_match();
}

std::vector<SiftMatchResult> OpenCLExtractor::match_last_self() {
  const auto native = impl_->detector.match_last_self();
  std::vector<SiftMatchResult> results;
  results.reserve(native.size());
  for (const auto &entry : native) {
    SiftMatchResult out;
    out.match = entry.match;
    out.score = entry.score;
    out.ambiguity = entry.ambiguity;
    out.match_x = entry.match_x;
    out.match_y = entry.match_y;
    results.push_back(out);
  }
  return results;
}

} // namespace sift_extractor
