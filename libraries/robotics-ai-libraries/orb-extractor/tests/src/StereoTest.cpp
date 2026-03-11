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
constexpr int num_levels_ = 1;
constexpr int ini_fast_thr_ = 20;
constexpr int min_fast_thr_ = 7;
constexpr float scale_factor_ = 1.1f;

bool compareKeyPointsDescriptor(
  vector<cv::KeyPoint> & left_keypts, std::vector<cv::KeyPoint> & right_keypts, uchar * left,
  uchar * right)
{
  int desc_size = 32;
  for (int i = 0; i < left_keypts.size(); i++) {
    cv::KeyPoint expectedResult = left_keypts[i];
    auto it = std::find_if(
      right_keypts.begin(), right_keypts.end(), [&expectedResult](const cv::KeyPoint & element) {
        return ((element.pt.x == expectedResult.pt.x) && (element.pt.y == expectedResult.pt.y));
      });
    if (it != right_keypts.end()) {
      int right_index = std::distance(right_keypts.begin(), it);
      int desc_col = i * 32;
      int n = 0;
      for (int j = desc_col; j < desc_size + desc_col; j++) {
        if (left[j] != right[right_index * 32 + n]) {
          std::cout << "\n i=" << i << " right=" << right_index << "\n";
          std::cout << "\n keypoint:" << i << " descriptor is not matching";
          std::cout << "\n descriptor:" << j << " expected=" << left[j]
                    << " actual=" << right[right_index * 32 + j];
          std::cout << "\n left_keypoint_x:" << left_keypts[i].pt.x
                    << " left_keypoint_y:" << left_keypts[i].pt.y;
          std::cout << "\n right_keypoint_x:" << right_keypts[right_index].pt.x
                    << " right_keypoint_y:" << right_keypts[right_index].pt.y << "\n";
          return false;
        }
        n++;
      }
    } else {
      std::cout << "left keypts " << i << " is missing in right keypts\n";
      return false;
    }
  }

  return true;
}

void stereoTest()
{
  std::vector<cv::Mat> stereo_images;
  stereo_images.resize(2);

  stereo_images[0] = cv::imread(DATAPATH + "/market.jpg", cv::IMREAD_GRAYSCALE);
  stereo_images[1] = cv::imread(DATAPATH + "/market.jpg", cv::IMREAD_GRAYSCALE);

  std::vector<std::vector<cv::KeyPoint>> keypts;
  keypts.resize(2);

  std::vector<cv::Mat> stereo_descriptors;

  const cv::_InputArray in_image_array(stereo_images);
  const cv::_InputArray in_image_mask_array;
  const cv::_OutputArray descriptor_array(stereo_descriptors);

  std::vector<std::vector<float>> mask_rect;

  constexpr int no_of_camera = 2;
  auto extractor = std::make_shared<orb_extractor>(
    max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, no_of_camera,
    mask_rect);

  extractor->extract(in_image_array, in_image_mask_array, keypts, descriptor_array);

  std::vector<cv::KeyPoint> left_keypts = keypts.at(0);
  std::vector<cv::KeyPoint> right_keypts = keypts.at(1);

  // Compare keypoints size left image and right image
  ASSERT_TRUE(right_keypts.size() == left_keypts.size())
    << "Left keypoints size=" << left_keypts.size()
    << " Right keypoints size= " << right_keypts.size();
  // std::cout << "\nLeft keypoints size=" << left_keypts.size() << " Right
  // keypoints size= " << right_keypts.size(); Compare keypoints left image and
  // right image Compare Descriptors left image and right image
  ASSERT_TRUE(compareKeyPointsDescriptor(
    left_keypts, right_keypts, stereo_descriptors.at(0).data, stereo_descriptors.at(1).data));
}

TEST(StereoTest, Positive) { stereoTest(); }

#endif  // OPENCV_FREE
