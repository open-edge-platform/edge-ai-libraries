/*
 * Copyright (C) 2026 Intel Corporation
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Thin robotics wrapper around the horizontal sift_extractor core.
 * Descriptors are 128-D float (L2); not drop-in for ORB binary/Hamming matchers.
 */

#ifndef SIFT_LZE_H_
#define SIFT_LZE_H_

#include "config.h"
#include "sift_type.h"

#include <string>
#include <vector>

class sift_lze {
public:
  sift_lze() = delete;

  //! max_num_keypts: 0 = uncapped (core default). backend: "auto"|"opencl"|"sycl".
  //! mask_rects: ORB-compatible quarter-grid exclusion rectangles
  //!   {x0, x1, y0, y1} in units of width/4 and height/4 (host-side zeroing).
  sift_lze(unsigned int max_num_keypts, unsigned int num_octaves, float contrast_threshold,
           unsigned int no_of_cameras, const std::string &backend = "auto",
           const std::vector<std::vector<float>> &mask_rects = {});

  ~sift_lze();

  sift_lze(const sift_lze &) = delete;
  sift_lze &operator=(const sift_lze &) = delete;

#ifdef OPENCV_FREE
  //! Descriptors are 128-D float rows (L2). DescMat2d is mat<float>.
  void extract(const std::vector<Mat2d> &in_image, const std::vector<Mat2d> &in_image_mask,
               std::vector<std::vector<KeyPoint>> &keypts, std::vector<DescMat2d> &out_descriptors);
#else
  void extract(const cv::_InputArray &in_image, const cv::_InputArray &in_image_mask,
               std::vector<std::vector<cv::KeyPoint>> &keypts, const cv::_OutputArray &out_descriptors);
#endif

  unsigned int get_max_num_keypoints() const;
  void set_max_num_keypoints(unsigned int max_num_keypts);

  unsigned int get_num_octaves() const;
  void set_num_octaves(unsigned int num_octaves);

  float get_contrast_threshold() const;
  void set_contrast_threshold(float contrast_threshold);

  std::string get_backend() const;
  void set_backend(const std::string &backend);

  //! Resolved backend name after first extract ("opencl" or "sycl").
  std::string get_resolved_backend() const;

private:
  sift_lze_impl *extractor_impl;
};

#endif // SIFT_LZE_H_
