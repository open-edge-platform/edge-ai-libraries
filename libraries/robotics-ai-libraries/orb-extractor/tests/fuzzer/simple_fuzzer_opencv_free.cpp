// Copyright (C) 2025 Intel Corporation
//
// SPDX-License-Identifier: Apache-2.0

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <memory>
#include <random>
#include <vector>

// Simple fuzzer to test input validation and memory safety
// Tests parameter boundaries and edge cases without GPU dependencies

using namespace std;

// Function to test various parameter combinations
void testParameterCombinations(const uint8_t * data, size_t size)
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

  // Create test image data
  std::vector<unsigned char> image_data(width * height);

  // Fill with pattern based on fuzzer input
  for (size_t i = 0; i < image_data.size() && i + 20 < size; ++i) {
    image_data[i] = data[(i + 20) % size];
  }

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

    // Test memory allocation patterns
    std::vector<std::vector<unsigned char>> multi_images(num_levels);
    for (int level = 0; level < num_levels; ++level) {
      int level_width = width / (int)pow(scale_factor, level);
      int level_height = height / (int)pow(scale_factor, level);
      if (level_width < 10 || level_height < 10) break;

      multi_images[level].resize(level_width * level_height);
      // Fill with test data
      memset(multi_images[level].data(), (level * 37) % 256, multi_images[level].size());
    }

  } catch (const std::exception & e) {
    // Any exception during parameter validation indicates a bug
    std::cout << "Exception during parameter testing: " << e.what() << std::endl;
    abort();  // Fuzzer will catch this as a bug
  }
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t * data, size_t size)
{
  testParameterCombinations(data, size);
  return 0;
}