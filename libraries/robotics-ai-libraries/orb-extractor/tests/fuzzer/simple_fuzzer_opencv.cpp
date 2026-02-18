// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <memory>
#include <opencv2/opencv.hpp>
#include <random>
#include <vector>

// Simple fuzzer to test OpenCV API input validation and memory safety
// Tests parameter boundaries and edge cases without GPU dependencies

using namespace std;

// Function to test various OpenCV parameter combinations
void testOpenCVParameterCombinations(const uint8_t * data, size_t size)
{
  if (size < 20) return;  // Need enough data for parameters

  // Extract test parameters from fuzzer input
  uint32_t max_keypts = *reinterpret_cast<const uint32_t *>(data + 0);
  float scale_factor = *reinterpret_cast<const float *>(data + 4);
  int num_levels = *reinterpret_cast<const int *>(data + 8);
  int ini_fast_thr = *reinterpret_cast<const int *>(data + 12);
  int min_fast_thr = *reinterpret_cast<const int *>(data + 16);

  // Test parameter boundary conditions
  max_keypts = max_keypts % 50000;  // Reasonable limit
  scale_factor = (scale_factor < 1.01f) ? 1.2f : scale_factor;
  scale_factor = (scale_factor > 3.0f) ? 2.0f : scale_factor;
  num_levels = (num_levels < 1) ? 1 : (num_levels > 10) ? 8 : num_levels;
  ini_fast_thr = (ini_fast_thr < 1) ? 20 : (ini_fast_thr > 100) ? 50 : ini_fast_thr;
  min_fast_thr = (min_fast_thr < 1) ? 7 : (min_fast_thr > 50) ? 20 : min_fast_thr;

  // Test with various image dimensions
  int width = 200 + (data[19] % 800);   // 200-1000 pixels
  int height = 200 + (data[18] % 600);  // 200-800 pixels

  // Test parameter validation - this should not crash
  try {
    // Basic parameter validation logic
    if (max_keypts == 0 || scale_factor <= 1.0f || num_levels < 1) {
      // Invalid parameters - should be handled gracefully
      return;
    }

    if (ini_fast_thr <= 0 || min_fast_thr <= 0 || min_fast_thr > ini_fast_thr) {
      // Invalid threshold values - should be handled gracefully
      return;
    }

    // Test OpenCV Mat creation and manipulation
    cv::Mat test_image = cv::Mat::zeros(height, width, CV_8UC1);

    // Fill with pattern based on fuzzer input
    for (int y = 0; y < height && y < 100; ++y) {
      for (int x = 0; x < width && x < 100; ++x) {
        if ((y * width + x + 20) < size) {
          test_image.at<uchar>(y, x) = data[(y * width + x + 20) % size];
        }
      }
    }

    // Test OpenCV keypoint detection (basic FAST)
    std::vector<cv::KeyPoint> keypoints;
    cv::FAST(test_image, keypoints, ini_fast_thr);

    // Test scale pyramid creation
    std::vector<cv::Mat> pyramid;
    pyramid.push_back(test_image.clone());

    for (int level = 1; level < num_levels; ++level) {
      cv::Mat scaled;
      double scale = 1.0 / pow(scale_factor, level);
      cv::Size new_size(int(width * scale), int(height * scale));

      if (new_size.width < 10 || new_size.height < 10) break;

      cv::resize(test_image, scaled, new_size);
      pyramid.push_back(scaled);
    }

    // Test descriptor computation if we have keypoints
    if (!keypoints.empty() && keypoints.size() < 1000) {
      cv::Mat descriptors;
      // Basic ORB descriptor computation would go here
      // For now just test keypoint data access
      for (const auto & kp : keypoints) {
        volatile float x = kp.pt.x;  // Access keypoint data
        volatile float y = kp.pt.y;
        (void)x;
        (void)y;  // Suppress unused variable warnings
      }
    }

  } catch (const std::exception & e) {
    // Any exception during parameter validation indicates a bug
    std::cout << "Exception during OpenCV parameter testing: " << e.what() << std::endl;
    abort();  // Fuzzer will catch this as a bug
  }
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t * data, size_t size)
{
  testOpenCVParameterCombinations(data, size);
  return 0;
}