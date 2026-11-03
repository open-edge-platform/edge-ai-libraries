/*
 * Copyright (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 *
 * Wrapper keypoints/descriptors must match a direct sift_extractor::Extractor call.
 */

#include "sift_lze.h"

#include <sift_extractor/extractor.hpp>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

namespace {

float circular_angle_delta_deg(float a, float b) {
  float d = std::fmod(a - b + 180.0f, 360.0f);
  if (d < 0.0f) d += 360.0f;
  return std::fabs(d - 180.0f);
}

} // namespace

int main() {
  // Isolate from ambient SIFT_BACKEND so Auto / explicit backends stay aligned.
#if defined(_WIN32)
  _putenv_s("SIFT_BACKEND", "");
#else
  unsetenv("SIFT_BACKEND");
#endif

  cv::Mat image(240, 320, CV_8UC1, cv::Scalar(40));
  cv::rectangle(image, cv::Rect(32, 32, 120, 80), cv::Scalar(220), cv::FILLED);
  cv::circle(image, cv::Point(220, 140), 28, cv::Scalar(180), cv::FILLED);

  std::vector<float> pixels(static_cast<std::size_t>(image.cols) * image.rows);
  for (int y = 0; y < image.rows; ++y)
    for (int x = 0; x < image.cols; ++x)
      pixels[static_cast<std::size_t>(y) * image.cols + x] =
          static_cast<float>(image.at<unsigned char>(y, x));

  sift_extractor::ExtractorOptions options;
#if SIFT_EXTRACTOR_HAS_OPENCL
  options.opencl.octaves = 4;
  options.opencl.contrast_threshold = 1.0f;
#endif
#if SIFT_EXTRACTOR_HAS_SYCL
  options.sycl.octaves = 4;
  options.sycl.contrast_threshold = 1.0f;
#endif
  sift_extractor::Extractor core(image.cols, image.rows, sift_extractor::Backend::Auto, options);
  const auto core_features = core.extract(pixels.data(), pixels.size());

  // Rebuild float from the same Mat path the wrapper uses (continuous gray).
  sift_lze wrap(0, 4, 1.0f, 1, sift_extractor::backend_name(core.backend()));
  std::vector<std::vector<cv::KeyPoint>> keypts;
  std::vector<cv::Mat> descriptors;
  wrap.extract(image, cv::noArray(), keypts, descriptors);

  if (keypts.size() != 1 || descriptors.size() != 1) {
    std::fprintf(stderr, "wrap camera count mismatch\n");
    return 1;
  }
  if (keypts[0].size() != core_features.size()) {
    std::fprintf(stderr, "count mismatch wrap=%zu core=%zu\n", keypts[0].size(),
                 core_features.size());
    return 1;
  }
  if (descriptors[0].type() != CV_32F || descriptors[0].cols != 128 ||
      descriptors[0].rows != static_cast<int>(keypts[0].size())) {
    std::fprintf(stderr, "descriptor layout mismatch\n");
    return 1;
  }

  // Match wrap keypoints to core features by position, scale, and orientation.
  std::vector<char> used(core_features.size(), 0);
  for (std::size_t wi = 0; wi < keypts[0].size(); ++wi) {
    const auto &k = keypts[0][wi];
    std::size_t best = 0;
    float best_cost = 1e30f;
    for (std::size_t ci = 0; ci < core_features.size(); ++ci) {
      if (used[ci]) continue;
      const auto &cf = core_features[ci];
      const float dx = cf.x - k.pt.x;
      const float dy = cf.y - k.pt.y;
      const float d_scale = (2.0f * cf.scale) - k.size;
      const float d_angle = circular_angle_delta_deg(cf.orientation_degrees, k.angle);
      const float cost = dx * dx + dy * dy + 0.25f * d_scale * d_scale + 0.01f * d_angle * d_angle;
      if (cost < best_cost) {
        best_cost = cost;
        best = ci;
      }
    }
    if (best_cost > 1e-2f) {
      std::fprintf(stderr, "wrap keypoint %zu has no core match (cost=%g)\n", wi, best_cost);
      return 1;
    }
    used[best] = 1;
    const float *d = descriptors[0].ptr<float>(static_cast<int>(wi));
    double l2 = 0.0;
    for (int j = 0; j < 128; ++j) {
      const double diff =
          static_cast<double>(d[j] - core_features[best].descriptor[static_cast<std::size_t>(j)]);
      l2 += diff * diff;
    }
    if (std::sqrt(l2) > 1e-3) {
      std::fprintf(stderr, "descriptor %zu L2 mismatch %g\n", wi, std::sqrt(l2));
      return 1;
    }
  }
  std::printf("same-core PASS features=%zu backend=%s\n", core_features.size(),
              wrap.get_resolved_backend().c_str());
  return 0;
}
