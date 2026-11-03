/*
 * Copyright (C) 2026 Intel Corporation
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef SIFT_LZE_IMPL_H_
#define SIFT_LZE_IMPL_H_

#include "sift_lze.h"

#include <sift_extractor/extractor.hpp>

#include <memory>
#include <mutex>
#include <string>
#include <vector>

class sift_lze_impl {
public:
  sift_lze_impl(unsigned int max_num_keypts, unsigned int num_octaves, float contrast_threshold,
                unsigned int no_of_cameras, const std::string &backend,
                const std::vector<std::vector<float>> &mask_rects);

  unsigned int max_num_keypts_ = 0;
  unsigned int num_octaves_ = 5;
  float contrast_threshold_ = 1.0f;
  unsigned int no_of_cameras_ = 1;
  std::string backend_name_ = "auto";
  std::vector<std::vector<float>> mask_rects_;

  std::mutex mutex_;
  int width_ = 0;
  int height_ = 0;
  std::unique_ptr<sift_extractor::Extractor> extractor_;
  sift_extractor::Backend resolved_ = sift_extractor::Backend::Auto;

  void ensure_extractor(int width, int height);
  sift_extractor::ExtractorOptions make_options() const;
  std::vector<float> to_float_gray(const unsigned char *u8, int width, int height,
                                   std::size_t step) const;
  void apply_rect_masks(std::vector<float> &gray, int width, int height) const;
  void apply_u8_mask(std::vector<float> &gray, const unsigned char *mask, int width, int height,
                     std::size_t step) const;

#ifdef OPENCV_FREE
  void extract(const std::vector<Mat2d> &in_image, const std::vector<Mat2d> &in_image_mask,
               std::vector<std::vector<KeyPoint>> &keypts, std::vector<DescMat2d> &out_descriptors);
#else
  void extract(const cv::_InputArray &in_image, const cv::_InputArray &in_image_mask,
               std::vector<std::vector<cv::KeyPoint>> &keypts, const cv::_OutputArray &out_descriptors);
#endif
};

#endif // SIFT_LZE_IMPL_H_
