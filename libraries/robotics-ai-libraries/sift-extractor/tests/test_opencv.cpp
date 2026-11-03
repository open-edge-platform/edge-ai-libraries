/*
 * Copyright (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

#include "sift_lze.h"

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include <cstdio>
#include <vector>

int main() {
  cv::Mat image(240, 320, CV_8UC1, cv::Scalar(32));
  cv::rectangle(image, cv::Rect(40, 40, 120, 80), cv::Scalar(200), cv::FILLED);

  sift_lze extractor(0, 4, 1.0f, 2, "auto");
  std::vector<cv::Mat> cams = {image, image};
  std::vector<std::vector<cv::KeyPoint>> keypts;
  std::vector<cv::Mat> descriptors;
  extractor.extract(cams, cv::noArray(), keypts, descriptors);
  if (keypts.size() != 2 || descriptors.size() != 2) {
    std::fprintf(stderr, "camera count mismatch\n");
    return 1;
  }
  if (!descriptors[0].empty() &&
      (descriptors[0].type() != CV_32F || descriptors[0].cols != 128)) {
    std::fprintf(stderr, "descriptor layout must be Nx128 CV_32F\n");
    return 1;
  }
  std::printf("opencv stereo keypoints=%zu,%zu backend=%s\n", keypts[0].size(), keypts[1].size(),
              extractor.get_resolved_backend().c_str());
  return 0;
}
