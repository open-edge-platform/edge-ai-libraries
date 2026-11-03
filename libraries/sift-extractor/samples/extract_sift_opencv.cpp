// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include <sift_extractor/opencv_adapter.hpp>

#include <cstdio>
#include <opencv2/core.hpp>
#include <string>
#include <vector>

int main(int argc, char **argv) {
  using sift_extractor::Backend;
  using sift_extractor::Extractor;
  using sift_extractor::backend_from_name;
  using sift_extractor::backend_name;
  using sift_extractor::opencv::detect_and_compute;

  const int width = 64;
  const int height = 64;
  Backend backend = Backend::Auto;
  if (argc > 1) backend = backend_from_name(argv[1]);

  try {
    Extractor extractor(width, height, backend);
    cv::Mat image(height, width, CV_8UC1);
    for (int y = 0; y < height; ++y)
      for (int x = 0; x < width; ++x)
        image.at<unsigned char>(y, x) =
            static_cast<unsigned char>(32 + (x * 17 + y * 13) % 11);

    std::vector<cv::KeyPoint> keypoints;
    cv::Mat descriptors;
    detect_and_compute(extractor, image, keypoints, descriptors);
    std::printf("backend=%s keypoints=%zu descriptors=%dx%d\n",
                backend_name(extractor.backend()), keypoints.size(), descriptors.rows,
                descriptors.cols);
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "extract_sift_opencv failed: %s\n", error.what());
    return 1;
  }
}
