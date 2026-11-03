/*
 * Copyright (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

#include "sift_lze.h"

#include <cstdio>
#include <vector>

int main() {
  constexpr int W = 320;
  constexpr int H = 240;
  Mat2d image(H, W, static_cast<unsigned char>(32));
  for (int y = 40; y < 120; ++y)
    for (int x = 40; x < 160; ++x) image.row(y)[x] = static_cast<unsigned char>(200);

  // Mono + stereo (same frame twice) with a host rect mask.
  std::vector<std::vector<float>> masks = {{1.0f, 2.0f, 1.0f, 2.0f}};
  sift_lze mono(0, 4, 1.0f, 1, "auto", masks);
  std::vector<Mat2d> images = {image};
  std::vector<Mat2d> empty_masks;
  std::vector<std::vector<KeyPoint>> keypts;
  std::vector<DescMat2d> descriptors;
  mono.extract(images, empty_masks, keypts, descriptors);
  if (keypts.size() != 1 || descriptors.size() != 1) {
    std::fprintf(stderr, "mono camera count mismatch\n");
    return 1;
  }
  std::printf("ocvfree mono keypoints=%zu backend=%s\n", keypts[0].size(),
              mono.get_resolved_backend().c_str());

  sift_lze stereo(0, 4, 1.0f, 2, "auto");
  std::vector<Mat2d> pair = {image, image};
  stereo.extract(pair, empty_masks, keypts, descriptors);
  if (keypts.size() != 2 || descriptors.size() != 2) {
    std::fprintf(stderr, "stereo camera count mismatch\n");
    return 1;
  }
  std::printf("ocvfree stereo keypoints=%zu,%zu\n", keypts[0].size(), keypts[1].size());
  return 0;
}
