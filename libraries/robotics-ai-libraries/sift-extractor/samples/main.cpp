/*
 * Copyright (C) 2026 Intel Corporation
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Mono / multi-camera SIFT extract sample (OpenCV-linked libsift_lze).
 * Descriptors are CV_32F 128-D (L2), not ORB binary/Hamming.
 */

#include "sift_lze.h"

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <cstdio>
#include <string>
#include <vector>

namespace {

void usage(const char *argv0) {
  std::fprintf(stderr,
               "Usage: %s --image=PATH [--images=N] [--backend=auto|opencl|sycl] "
               "[--octaves=5] [--contrast=1.0] [--max-features=0]\n",
               argv0);
}

} // namespace

int main(int argc, char **argv) {
  std::string image_path;
  unsigned images = 1;
  std::string backend = "auto";
  unsigned octaves = 5;
  float contrast = 1.0f;
  unsigned max_features = 0;

  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    auto take = [&](const char *key) -> std::string {
      const std::string prefix = std::string("--") + key + "=";
      if (arg.rfind(prefix, 0) == 0) return arg.substr(prefix.size());
      return {};
    };
    if (auto v = take("image"); !v.empty())
      image_path = v;
    else if (auto v = take("images"); !v.empty())
      images = static_cast<unsigned>(std::stoul(v));
    else if (auto v = take("backend"); !v.empty())
      backend = v;
    else if (auto v = take("octaves"); !v.empty())
      octaves = static_cast<unsigned>(std::stoul(v));
    else if (auto v = take("contrast"); !v.empty())
      contrast = std::stof(v);
    else if (auto v = take("max-features"); !v.empty())
      max_features = static_cast<unsigned>(std::stoul(v));
    else if (arg == "--help" || arg == "-h") {
      usage(argv[0]);
      return 0;
    } else {
      usage(argv[0]);
      return 2;
    }
  }
  if (image_path.empty() || images == 0) {
    usage(argv[0]);
    return 2;
  }

  cv::Mat gray = cv::imread(image_path, cv::IMREAD_GRAYSCALE);
  if (gray.empty()) {
    std::fprintf(stderr, "failed to read %s\n", image_path.c_str());
    return 1;
  }

  std::vector<cv::Mat> cams(images, gray);
  sift_lze extractor(max_features, octaves, contrast, images, backend);
  std::vector<std::vector<cv::KeyPoint>> keypts;
  std::vector<cv::Mat> descriptors;
  extractor.extract(cams, cv::noArray(), keypts, descriptors);

  std::printf("backend=%s resolved=%s cameras=%u size=%dx%d\n", backend.c_str(),
              extractor.get_resolved_backend().c_str(), images, gray.cols, gray.rows);
  for (unsigned i = 0; i < images; ++i) {
    std::printf("camera[%u]: keypoints=%zu descriptors=%dx%d type=%d\n", i, keypts[i].size(),
                descriptors[i].rows, descriptors[i].cols, descriptors[i].type());
  }
  return 0;
}
