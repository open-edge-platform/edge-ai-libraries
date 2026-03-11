// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#include <unistd.h>

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <random>
#include <vector>

#include "../src/TestUtil.h"
#include "config.h"
#include "gtest/gtest.h"
#include "orb_extractor.h"
#include "orb_type.h"

using namespace std;

constexpr uint32_t max_num_keypts_ = 2000;
constexpr int num_levels_ = 1;
constexpr int ini_fast_thr_ = 20;
constexpr int min_fast_thr_ = 7;
constexpr float scale_factor_ = 1.1f;

// Global variable to track GPU availability
// -1: unknown, 0: unavailable, 1: available
static int gpu_available = -1;

// Function to generate a random integer within a range
int randomInt(int min, int max)
{
  static std::random_device rd;
  static std::mt19937 gen(rd());
  std::uniform_int_distribution<int> distribution(min, max);

  return distribution(gen);
}

// Generate random image data for OpenCV-free mode
void generateRandomImageData(unsigned char * data, int width, int height, int num_objects)
{
  // Initialize with white background
  memset(data, 255, width * height);

  // Generate random objects (simple rectangles)
  for (int obj = 0; obj < num_objects && obj < 50; ++obj) {
    int rect_width = randomInt(20, std::min(200, width / 4));
    int rect_height = randomInt(20, std::min(200, height / 4));
    int rect_x = randomInt(0, std::max(1, width - rect_width));
    int rect_y = randomInt(0, std::max(1, height - rect_height));

    unsigned char intensity = randomInt(0, 128);  // Darker objects

    // Draw filled rectangle
    for (int y = rect_y; y < rect_y + rect_height && y < height; ++y) {
      for (int x = rect_x; x < rect_x + rect_width && x < width; ++x) {
        data[y * width + x] = intensity;
      }
    }
  }
}

bool compareKeyPointsDescriptor(
  vector<KeyType> & left_keypts, std::vector<KeyType> & right_keypts, unsigned char * left,
  unsigned char * right)
{
  int desc_size = 32;
  if (left_keypts.size() != right_keypts.size()) {
    std::cout << "\n gpukeypts and cpukeypts are not same size\n";
    std::cout << "left keypoints size=" << left_keypts.size()
              << " right keypoints size=" << right_keypts.size() << "\n";
    return false;
  }

  for (int i = 0; i < left_keypts.size(); i++) {
    if (left_keypts[i].x != right_keypts[i].x || left_keypts[i].y != right_keypts[i].y) {
      std::cout << "\n keypoints are not matching at index " << i << "\n";
      return false;
    }

    // Compare descriptors
    int desc_col = i * desc_size;
    for (int j = 0; j < desc_size; j++) {
      if (left[desc_col + j] != right[desc_col + j]) {
        std::cout << "\n descriptor mismatch at keypoint " << i << " position " << j << "\n";
        return false;
      }
    }
  }
  return true;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t * data, size_t size)
{
  // Skip if GPU is known to be unavailable
  if (gpu_available == 0) {
    return 0;
  }

  try {
    if (size < sizeof(int)) {
      return 0;
    }

    // Extract integers from data
    int numIntegers = size / sizeof(int);
    const int * integers = reinterpret_cast<const int *>(data);

    for (int i = 0; i < numIntegers; ++i) {
      if ((integers[i] < 5000) && (integers[i] > 1)) {
        // Image dimensions
        int width = 848;
        int height = 480;
        int total_pixels = width * height;

        // Number of objects to generate
        int num_objects = integers[i];

        // Allocate raw image data
        std::vector<unsigned char> left_image_data(total_pixels);
        std::vector<unsigned char> right_image_data(total_pixels);

        // Generate random image content
        generateRandomImageData(left_image_data.data(), width, height, num_objects);
        generateRandomImageData(right_image_data.data(), width, height, num_objects);

        // Create Mat2d objects for OpenCV-free mode
        std::vector<MatType> stereo_images;
        stereo_images.resize(2);

        stereo_images[0] = Mat2d(height, width, left_image_data.data());
        stereo_images[1] = Mat2d(height, width, right_image_data.data());

        std::vector<std::vector<KeyType>> keypts;
        keypts.resize(2);

        std::vector<MatType> stereo_descriptors;
        std::vector<MatType> mask_images;  // Empty mask array

        std::vector<std::vector<float>> mask_rect;

        constexpr int no_of_camera = 2;
        auto extractor = std::make_shared<orb_extractor>(
          max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, no_of_camera,
          mask_rect);

        extractor->set_gpu_kernel_path(ORBLZE_KERNEL_PATH_STRING);

        extractor->extract(stereo_images, mask_images, keypts, stereo_descriptors);

        if ((keypts.at(0).size() == 0) && (keypts.at(1).size() == 0)) {
          // No keypoints found, continue to next data
          continue;
        }

        std::vector<KeyType> left_keypts = keypts.at(0);
        std::vector<KeyType> right_keypts = keypts.at(1);

        // Compare keypoints size for left and right images
        if (left_keypts.size() != right_keypts.size()) {
          throw std::invalid_argument("left image and right image KeyPoints are not same size");
        }

        if (stereo_descriptors.size() >= 2) {
          if (!(compareKeyPointsDescriptor(
                left_keypts, right_keypts, stereo_descriptors.at(0).data(),
                stereo_descriptors.at(1).data()))) {
            throw std::invalid_argument(
              "left image and right image KeyPoints Descriptor are not same");
          }
        }

        break;
      }
    }

  } catch (std::exception & e) {
    std::string error_msg(e.what());
    // Handle GPU/device initialization errors gracefully (expected on CPU-only
    // systems)
    if (
      error_msg.find("program was built") != std::string::npos ||
      error_msg.find("Failed to build") != std::string::npos ||
      error_msg.find("PI_ERROR") != std::string::npos ||
      error_msg.find("Device build") != std::string::npos) {
      // Mark GPU as unavailable and skip all future tests
      cout << "GPU/device initialization errors; Will skip future tests: " << e.what() << endl;
      gpu_available = 0;
      return 0;
    }
    // All other exceptions should fail (including keypoint mismatches)
    cout << "Exception occurred in OpenCV-free fuzzer: " << e.what() << endl;
    exit(1);
  }

  // If we successfully completed a test, mark GPU as available
  if (gpu_available == -1) {
    gpu_available = 1;
  }

  return 0;
}