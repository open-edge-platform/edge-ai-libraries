// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#ifndef OPENCV_FREE

#include <unistd.h>

#include <chrono>
#include <cstdlib>
#include <fstream>
#include <memory>
#include <opencv2/features2d.hpp>
#include <opencv2/highgui.hpp>

#include "TestUtil.h"
#include "gtest/gtest.h"
#include "orb_extractor.h"

using namespace cv;

constexpr uint32_t max_num_keypts_ = 2000;
constexpr int num_levels_ = 8;
constexpr int ini_fast_thr_ = 20;
constexpr int min_fast_thr_ = 7;
constexpr float scale_factor_ = 1.1f;

void imagemaskTest()
{
  std::vector<cv::Mat> image;
  image.resize(1);

  image[0] = cv::imread(DATAPATH + "/market.jpg", cv::IMREAD_GRAYSCALE);

  std::vector<std::vector<cv::KeyPoint>> keypts;
  keypts.resize(1);

  std::vector<cv::Mat> descriptors;

  const cv::_InputArray in_image_array(image);

  std::vector<cv::Mat> images_mask;

  images_mask.resize(1);

  images_mask[0] = cv::imread(DATAPATH + "/circle.jpg", cv::IMREAD_GRAYSCALE);

  const cv::_InputArray in_image_mask_array(images_mask);

  const cv::_OutputArray descriptor_array(descriptors);

  std::vector<std::vector<float>> mask_rect;

  constexpr int no_of_camera = 1;
  auto extractor = std::make_shared<orb_extractor>(
    max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, no_of_camera,
    mask_rect);

  extractor->extract(in_image_array, in_image_mask_array, keypts, descriptor_array);

  std::vector<cv::KeyPoint> draw_keypts = keypts.at(0);

  cv::Mat out(image.at(0).rows, image.at(0).cols, cv::IMREAD_GRAYSCALE);
  cv::drawKeypoints(image.at(0), draw_keypts, out, cv::Scalar(255, 0, 0));

  // Only show GUI elements if we have a display (not in headless CI environment)
  const char * display_env = std::getenv("DISPLAY");
  bool has_display = display_env && strlen(display_env) > 0;

  if (has_display) {
    std::cout << "Display available - showing visualization" << std::endl;
    cv::imshow("mask_image", images_mask[0]);
    cv::waitKey(0);
    cv::imshow("mask_image_output", out);
    cv::waitKey(0);
  } else {
    std::cout << "Headless environment detected - skipping visualization" << std::endl;
    std::cout << "Test completed successfully without GUI display" << std::endl;
  }
}

TEST(StereoTest, Positive) { imagemaskTest(); }

#endif  // OPENCV_FREE
