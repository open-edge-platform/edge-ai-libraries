// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#include <unistd.h>

#include <chrono>
#include <fstream>
#include <memory>

#include "TestUtil.h"
#include "gtest/gtest.h"
#include "orb_extractor.h"
#include "orb_type.h"

constexpr uint32_t max_num_keypts_ = 2000;
constexpr int num_levels_ = 1;
constexpr int ini_fast_thr_ = 20;
constexpr int min_fast_thr_ = 7;
constexpr float scale_factor_ = 1.1f;

bool compareKeyPointsDescriptor(
  vector<cv::KeyPoint> & left_keypts, std::vector<cv::KeyPoint> & right_keypts,
  unsigned char * left, unsigned char * right)
{
  int desc_size = 32;
  for (int i = 0; i < left_keypts.size(); i++) {
    cv::KeyPoint expectedResult = left_keypts[i];
    auto it = std::find_if(
      right_keypts.begin(), right_keypts.end(), [&expectedResult](const cv::KeyPoint & element) {
        return (
          (element.pt.x == expectedResult.pt.x) && (element.pt.y == expectedResult.pt.y) &&
          (element.size == expectedResult.size) && (element.angle == expectedResult.angle) &&
          (element.response == expectedResult.response) &&
          (element.octave == expectedResult.octave));
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

void opencvfreeTest(int num_camera)
{
  // multi
  int num_of_cameras = num_camera;

  std::vector<cv::Mat> all_images;
  all_images.resize(num_of_cameras);

  for (int i = 0; i < num_of_cameras; i++) {
    all_images[i] = cv::imread(DATAPATH + "/market.jpg", cv::IMREAD_GRAYSCALE);
  }

  std::vector<std::vector<KeyType>> keypts(num_of_cameras);
  std::vector<MatType> all_descriptors(num_of_cameras);

  Mat2d * images = new Mat2d[num_of_cameras];
  std::vector<MatType> in_image_array;
  for (int i = 0; i < num_of_cameras; i++) {
    images[i] = Mat2d(all_images[i].rows, all_images[i].cols, all_images[i].data);
    in_image_array.push_back(images[i]);
  }

  std::vector<MatType> in_image_mask_array;
  std::vector<MatType> descriptor_array;

  // mono
  std::vector<cv::Mat> single_image;
  single_image.resize(1);
  single_image[0] = cv::imread(DATAPATH + "/market.jpg", cv::IMREAD_GRAYSCALE);

  std::vector<std::vector<KeyType>> single_keypts(num_of_cameras);
  std::vector<MatType> single_all_descriptors(num_of_cameras);

  Mat2d * sing_image = new Mat2d[1];
  std::vector<MatType> in_single_image_array;
  for (int i = 0; i < 1; i++) {
    sing_image[i] = Mat2d(single_image[i].rows, single_image[i].cols, single_image[i].data);
    in_single_image_array.push_back(sing_image[i]);
  }

  std::vector<MatType> single_in_image_mask_array;
  std::vector<MatType> single_descriptor_array;

  std::vector<std::vector<float>> mask_rect;

  auto extractor = std::make_shared<orb_extractor>(
    max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, num_of_cameras,
    mask_rect);
  auto single_extractor = std::make_shared<orb_extractor>(
    max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, 1, mask_rect);

  extractor->extract(in_image_array, in_image_mask_array, keypts, descriptor_array);

  single_extractor->extract(
    in_single_image_array, single_in_image_mask_array, single_keypts, single_descriptor_array);

  std::vector<std::vector<cv::KeyPoint>> all_keypts(num_of_cameras);
  std::vector<std::vector<cv::KeyPoint>> single_all_keypts(1);

  // multi
  for (int i = 0; i < num_of_cameras; i++) {
    auto & gpu_keypts = keypts.at(i);
    for (int pt = 0; pt < gpu_keypts.size(); pt++) {
      all_keypts[i].emplace_back(
        cv::KeyPoint(
          gpu_keypts[pt].x, gpu_keypts[pt].y, gpu_keypts[pt].size, gpu_keypts[pt].angle,
          gpu_keypts[pt].response, gpu_keypts[pt].octave, -1));
    }
  }

  // mono
  for (int i = 0; i < 1; i++) {
    auto & gpu_keypts = single_keypts.at(i);
    for (int pt = 0; pt < gpu_keypts.size(); pt++) {
      single_all_keypts[i].emplace_back(
        cv::KeyPoint(
          gpu_keypts[pt].x, gpu_keypts[pt].y, gpu_keypts[pt].size, gpu_keypts[pt].angle,
          gpu_keypts[pt].response, gpu_keypts[pt].octave, -1));
    }
  }

  std::vector<cv::KeyPoint> single_out_keypts = single_all_keypts[0];

  // multi unit test
  for (int i = 0; i < num_of_cameras - 1; i++) {
    std::vector<cv::KeyPoint> left_keypts = all_keypts[i];
    int j = i + 1;
    std::vector<cv::KeyPoint> right_keypts = all_keypts[j];

    // Compare keypoints size left image and right image
    ASSERT_TRUE(right_keypts.size() == left_keypts.size())
      << "Left keypoints size=" << left_keypts.size()
      << " Right keypoints size= " << right_keypts.size();
    ASSERT_TRUE(single_out_keypts.size() == left_keypts.size())
      << "single image keypoints size=" << left_keypts.size()
      << " Right keypoints size= " << right_keypts.size();
    // compare with stereo output result or multiple image output result
    ASSERT_TRUE(compareKeyPointsDescriptor(
      left_keypts, right_keypts, descriptor_array.at(i).row(0), descriptor_array.at(j).row(0)));
  }

  // mono
  // compare mono output result with multi image output result
  std::vector<cv::KeyPoint> left_keypts = all_keypts[0];
  ASSERT_TRUE(compareKeyPointsDescriptor(
    single_out_keypts, left_keypts, single_descriptor_array.at(0).row(0),
    descriptor_array.at(0).row(0)));
}

TEST(OpencvfreeTest, Positive)
{
  for (int i = 1; i < 9; i++) {
    opencvfreeTest(i + 1);
  }
}
