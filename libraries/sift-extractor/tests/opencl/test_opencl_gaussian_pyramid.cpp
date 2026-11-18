// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "opencl_gaussian_pyramid.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>
#include <stdexcept>
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

bool check_resident(sift_extractor::detail::OpenCLGaussianPyramid &pyramid,
                    const std::vector<float> &image, int width, int height,
                    int octaves, int intervals, float sigma) {
  const auto expected = pyramid.build(image, width, height, octaves, intervals, sigma);
  const auto expected_dog = pyramid.difference_levels(expected, octaves, intervals);
  const auto equal_level = [](const auto &first, const auto &second) {
    return first.octave == second.octave && first.scale == second.scale &&
           first.width == second.width && first.height == second.height &&
           first.sigma == second.sigma && first.pixels == second.pixels;
  };
  for (bool wait_for_completion : {true, false}) {
    const auto actual = pyramid.build_with_differences(image, width, height,
        octaves, intervals, sigma, false, wait_for_completion);
    if (actual.gaussian.size() != expected.size() ||
        actual.differences.size() != expected_dog.size())
      return false;
    for (size_t index = 0; index < expected.size(); ++index)
      if (!equal_level(actual.gaussian[index], expected[index])) return false;
    for (size_t index = 0; index < expected_dog.size(); ++index)
      if (!equal_level(actual.differences[index], expected_dog[index])) return false;
  }
  return true;
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

    const auto dog_levels = pyramid.difference_levels(levels, octaves, intervals);
    const size_t dog_levels_per_octave = static_cast<size_t>(intervals + 2);
    passed &= dog_levels.size() ==
              static_cast<size_t>(octaves) * dog_levels_per_octave;
    float max_dog_error = 0.0f;
    for (const auto &dog : dog_levels) {
      const size_t gaussian_offset =
          static_cast<size_t>(dog.octave) * levels_per_octave + dog.scale;
      const auto &lower = levels[gaussian_offset];
      const auto &upper = levels[gaussian_offset + 1];
      passed &= dog.width == lower.width && dog.height == lower.height;
      for (size_t i = 0; i < dog.pixels.size(); ++i) {
        const float expected = upper.pixels[i] - lower.pixels[i];
        max_dog_error = std::max(max_dog_error,
                                 std::abs(dog.pixels[i] - expected));
      }
    }
    passed &= max_dog_error == 0.0f;

    passed &= check_resident(pyramid, image, width, height, octaves, intervals, base_sigma);
    struct Configuration { int width, height, octaves, intervals; float sigma; };
    for (const auto config : {Configuration{97, 65, 3, 5, 1.2f},
                              Configuration{257, 129, 4, 3, 1.6f},
                              Configuration{65, 33, 2, 1, 16.0f},
                              Configuration{3, 2, 2, 32, 0.1f},
                              Configuration{1, 1, 4, 1, 0.1f},
                              Configuration{2, 3, 3, 2, 2.0f},
                              Configuration{17, 15, 2, 3, 4.0f},
                              Configuration{17, 15, 2, 3, 4.1f},
                              Configuration{1, 1, 2, 3, 4.0f},
                              Configuration{33, 19, 1, 3, 1.6f}}) {
      std::vector<float> changed(static_cast<size_t>(config.width) * config.height);
      for (size_t index = 0; index < changed.size(); ++index)
        changed[index] = static_cast<float>((index * 37 + index / config.width) % 251);
      passed &= check_resident(pyramid, changed, config.width, config.height,
                                config.octaves, config.intervals, config.sigma);
      std::fill(changed.begin(), changed.end(), 0.0f);
      passed &= check_resident(pyramid, changed, config.width, config.height,
                                config.octaves, config.intervals, config.sigma);
    }
    auto invalid = image;
    invalid[0] = std::numeric_limits<float>::quiet_NaN();
    bool rejected = false;
    try {
      pyramid.build_with_differences(invalid, width, height, octaves, intervals, base_sigma);
    } catch (const std::invalid_argument &) {
      rejected = true;
    }
    passed &= rejected;
    passed &= check_resident(pyramid, image, width, height, octaves, intervals, base_sigma);

    std::printf("Gaussian pyramid: %zu levels, DoG levels %zu, "
                "first-level max error %.8f, DoG max error %.8f\n",
                levels.size(), dog_levels.size(), max_error, max_dog_error);
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
