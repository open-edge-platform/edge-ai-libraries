// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <vector>

struct _cl_command_queue;
struct _cl_mem;

namespace sift_extractor::detail {

struct GaussianLevel;
struct DoGLevel;

class OpenCLGaussianBlur {
public:
  OpenCLGaussianBlur();
  explicit OpenCLGaussianBlur(_cl_command_queue *queue);
  ~OpenCLGaussianBlur();

  OpenCLGaussianBlur(const OpenCLGaussianBlur &) = delete;
  OpenCLGaussianBlur &operator=(const OpenCLGaussianBlur &) = delete;
  OpenCLGaussianBlur(OpenCLGaussianBlur &&) = delete;
  OpenCLGaussianBlur &operator=(OpenCLGaussianBlur &&) = delete;

  std::vector<float> apply(const std::vector<float> &image, int width,
                           int height, const std::vector<float> &kernel);
  std::vector<float> difference_of_gaussians(
      const std::vector<float> &first, const std::vector<float> &second,
      int width, int height);
  std::vector<float> downsample_by_two(const std::vector<float> &image,
                                       int width, int height,
                                       int &output_width,
                                       int &output_height);

private:
  friend class OpenCLGaussianPyramid;
  void build_pyramid(const std::vector<float> &image,
                     std::vector<GaussianLevel> &gaussian,
                     std::vector<DoGLevel> &differences,
                     const std::vector<std::vector<float>> &kernels,
                     int intervals,
                     std::vector<_cl_mem *> *device_differences = nullptr,
                     std::vector<_cl_mem *> *device_gaussian = nullptr,
                     bool wait_for_completion = true);
  struct Impl;
  Impl *impl_;
};

} // namespace sift_extractor::detail
