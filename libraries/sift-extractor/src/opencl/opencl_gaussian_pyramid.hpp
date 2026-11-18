// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "opencl_gaussian_blur.hpp"

#include <vector>

namespace sift_extractor::detail {

struct GaussianLevel {
  int octave = 0;
  int scale = 0;
  int width = 0;
  int height = 0;
  float sigma = 0.0f;
  std::vector<float> pixels;
};

struct DoGLevel {
  int octave = 0;
  int scale = 0;
  int width = 0;
  int height = 0;
  float sigma = 0.0f;
  std::vector<float> pixels;
};

struct GaussianDoGPyramid {
  std::vector<GaussianLevel> gaussian;
  std::vector<DoGLevel> differences;
  std::vector<_cl_mem *> device_differences;
  std::vector<_cl_mem *> device_gaussian;
};

class OpenCLGaussianPyramid {
public:
  OpenCLGaussianPyramid() = default;
  explicit OpenCLGaussianPyramid(_cl_command_queue *queue) : primitives_(queue) {}
  OpenCLGaussianPyramid(const OpenCLGaussianPyramid &) = delete;
  OpenCLGaussianPyramid &operator=(const OpenCLGaussianPyramid &) = delete;
  OpenCLGaussianPyramid(OpenCLGaussianPyramid &&) = delete;
  OpenCLGaussianPyramid &operator=(OpenCLGaussianPyramid &&) = delete;

  std::vector<GaussianLevel> build(const std::vector<float> &image, int width,
                                   int height, int octave_count,
                                   int intervals, float base_sigma);
  std::vector<DoGLevel> difference_levels(
      const std::vector<GaussianLevel> &gaussian_levels, int octave_count,
      int intervals);
    GaussianDoGPyramid build_with_differences(
      const std::vector<float> &image, int width, int height, int octave_count,
      int intervals, float base_sigma, bool keep_on_device = false,
      bool wait_for_completion = true);

private:
  OpenCLGaussianBlur primitives_;
};

} // namespace sift_extractor::detail
