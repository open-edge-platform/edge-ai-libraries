#pragma once

#include <vector>

namespace sift_extractor::detail {

class OpenCLGaussianBlur {
public:
  OpenCLGaussianBlur();
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
  struct Impl;
  Impl *impl_;
};

} // namespace sift_extractor::detail
