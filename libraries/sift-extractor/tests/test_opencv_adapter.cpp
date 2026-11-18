// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include <sift_extractor/opencv_adapter.hpp>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

namespace {

void require(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "test_opencv_adapter failed: %s\n", message);
    std::exit(1);
  }
}

} // namespace

int main() {
  using sift_extractor::SiftFeature;
  using sift_extractor::opencv::to_float_gray;
  using sift_extractor::opencv::to_keypoint;
  using sift_extractor::opencv::to_opencv;

  SiftFeature feature;
  feature.x = 12.5f;
  feature.y = 34.25f;
  feature.scale = 1.75f;
  feature.orientation_degrees = 90.0f;
  feature.response = 0.42f;
  for (int bin = 0; bin < 128; ++bin) feature.descriptor[static_cast<std::size_t>(bin)] = 0.01f * bin;

  const cv::KeyPoint point = to_keypoint(feature);
  require(point.pt.x == feature.x && point.pt.y == feature.y, "keypoint position");
  require(std::fabs(point.size - 2.0f * feature.scale) < 1e-6f, "keypoint size diameter");
  require(point.angle == feature.orientation_degrees, "keypoint angle");
  require(point.response == feature.response, "keypoint response");

  std::vector<cv::KeyPoint> keypoints;
  cv::Mat descriptors;
  to_opencv({feature}, keypoints, descriptors);
  require(keypoints.size() == 1, "keypoint count");
  require(descriptors.rows == 1 && descriptors.cols == 128 && descriptors.type() == CV_32F,
          "descriptor shape");
  require(descriptors.at<float>(0, 17) == feature.descriptor[17], "descriptor copy");

  cv::Mat u8(8, 8, CV_8UC1, cv::Scalar(10));
  const cv::Mat f32 = to_float_gray(u8);
  require(f32.type() == CV_32FC1 && f32.isContinuous(), "8U conversion");
  require(f32.at<float>(0, 0) == 10.0f, "8U value");

  cv::Mat already(4, 4, CV_32FC1, cv::Scalar(0.5f));
  const cv::Mat reused = to_float_gray(already);
  require(reused.at<float>(1, 1) == 0.5f, "32F passthrough");

  bool rejected = false;
  try {
    to_float_gray(cv::Mat(2, 2, CV_8UC3, cv::Scalar(1, 2, 3)));
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  require(rejected, "reject multi-channel");

  std::printf("test_opencv_adapter: conversion checks passed\n");
  return 0;
}
