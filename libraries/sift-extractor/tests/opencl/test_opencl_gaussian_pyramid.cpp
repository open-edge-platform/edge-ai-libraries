#include "opencl_gaussian_pyramid.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

namespace {

std::vector<float> make_kernel(float sigma) {
  const int radius = std::max(1, static_cast<int>(std::ceil(3.0f * sigma)));
  std::vector<float> kernel(static_cast<size_t>(2 * radius + 1));
  double sum = 0.0;
  for (int offset = -radius; offset <= radius; ++offset) {
    const double position = static_cast<double>(offset);
    const double value =
        std::exp(-(position * position) / (2.0 * sigma * sigma));
    kernel[static_cast<size_t>(offset + radius)] = static_cast<float>(value);
    sum += value;
  }
  for (float &weight : kernel)
    weight = static_cast<float>(weight / sum);
  return kernel;
}

std::vector<float> cpu_blur(const std::vector<float> &image, int width,
                            int height, const std::vector<float> &kernel) {
  const int radius = static_cast<int>(kernel.size() / 2);
  std::vector<float> temporary(image.size());
  std::vector<float> output(image.size());
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      float sum = 0.0f;
      for (int offset = -radius; offset <= radius; ++offset) {
        const int xx = std::clamp(x + offset, 0, width - 1);
        sum += image[static_cast<size_t>(y) * width + xx] *
               kernel[static_cast<size_t>(offset + radius)];
      }
      temporary[static_cast<size_t>(y) * width + x] = sum;
    }
  }
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      float sum = 0.0f;
      for (int offset = -radius; offset <= radius; ++offset) {
        const int yy = std::clamp(y + offset, 0, height - 1);
        sum += temporary[static_cast<size_t>(yy) * width + x] *
               kernel[static_cast<size_t>(offset + radius)];
      }
      output[static_cast<size_t>(y) * width + x] = sum;
    }
  }
  return output;
}

} // namespace

int main() {
  constexpr int width = 71;
  constexpr int height = 53;
  constexpr int octaves = 2;
  constexpr int intervals = 3;
  constexpr float base_sigma = 1.6f;
  std::vector<float> image(static_cast<size_t>(width) * height);
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x)
      image[static_cast<size_t>(y) * width + x] =
          static_cast<float>((x * 37 + y * 61 + (x * y) % 251) & 255);
  }

  try {
    sift_extractor::detail::OpenCLGaussianPyramid pyramid;
    const auto levels = pyramid.build(image, width, height, octaves, intervals,
                                      base_sigma);
    const int levels_per_octave = intervals + 3;
    bool passed = levels.size() ==
                  static_cast<size_t>(octaves * levels_per_octave);
    passed &= levels[0].width == width && levels[0].height == height;
    passed &= levels[levels_per_octave].width == (width + 1) / 2 &&
              levels[levels_per_octave].height == (height + 1) / 2;

    const float sigma_step = std::pow(2.0f, 1.0f / intervals);
    for (int scale = 0; scale < levels_per_octave; ++scale) {
      const float expected_sigma =
          base_sigma * std::pow(sigma_step, static_cast<float>(scale));
      passed &= std::abs(levels[scale].sigma - expected_sigma) < 1e-5f;
      passed &= levels[scale].width == width && levels[scale].height == height;
    }
    passed &= std::abs(levels[levels_per_octave].sigma - base_sigma) < 1e-5f;

    const auto expected_first =
        cpu_blur(image, width, height, make_kernel(base_sigma));
    float max_error = 0.0f;
    for (size_t i = 0; i < expected_first.size(); ++i)
      max_error = std::max(max_error,
                           std::abs(expected_first[i] - levels[0].pixels[i]));
    passed &= max_error < 1e-4f;

    for (const auto &level : levels) {
      passed &= level.pixels.size() ==
                static_cast<size_t>(level.width) * level.height;
      passed &= std::all_of(level.pixels.begin(), level.pixels.end(),
                            [](float value) { return std::isfinite(value); });
    }

    std::printf("Gaussian pyramid: %zu levels, first-level max error %.8f\n",
                levels.size(), max_error);
    if (!passed) {
      std::fprintf(stderr, "OpenCL Gaussian pyramid check failed\n");
      return 1;
    }
  } catch (const std::exception &error) {
    std::fprintf(stderr, "OpenCL Gaussian pyramid failed: %s\n", error.what());
    return 1;
  }

  return 0;
}
