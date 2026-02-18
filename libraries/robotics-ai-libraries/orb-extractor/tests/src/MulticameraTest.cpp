// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#ifndef OPENCV_FREE

#include <unistd.h>

#include <chrono>
#include <fstream>
#include <memory>

#include "TestUtil.h"
#include "gtest/gtest.h"
#include "orb_extractor.h"

using namespace cv;

constexpr uint32_t max_num_keypts_ = 2000;
constexpr int num_levels_ = 2;
constexpr int ini_fast_thr_ = 20;
constexpr int min_fast_thr_ = 7;
constexpr float scale_factor_ = 1.1f;

void multicameraTest(int num)
{
  int num_of_camera = num;
  std::vector<cv::Mat> stereo_images;
  stereo_images.resize(num_of_camera);

  for (int i = 0; i < num_of_camera; i++) {
    stereo_images[i] = cv::imread(DATAPATH + "/market.jpg", cv::IMREAD_GRAYSCALE);
  }

  std::vector<std::vector<KeyType>> keypts(num_of_camera);
  std::vector<MatType> descriptors(num_of_camera);

  const cv::_InputArray in_image_array(stereo_images);
  const cv::_InputArray in_image_mask_array;
  const cv::_OutputArray descriptor_array(descriptors);

  std::vector<std::vector<float>> mask_rect;

  auto extractor = std::make_shared<orb_extractor>(
    max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, num_of_camera,
    mask_rect);

  extractor->extract(in_image_array, in_image_mask_array, keypts, descriptor_array);

  for (int i = 0; i < num_of_camera; i++) {
    ASSERT_TRUE(keypts.at(i).size() == descriptors.at(i).rows)
      << "keypoints size=" << keypts.at(i).size()
      << " descriptors size= " << descriptors.at(i).rows;
  }
}

TEST(MulticameraTest, Positive)
{
  for (int i = 2; i < 16; i++) multicameraTest(i);
}

#endif  // OPENCV_FREE
