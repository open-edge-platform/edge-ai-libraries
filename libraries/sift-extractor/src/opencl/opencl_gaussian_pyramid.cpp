#include "opencl_gaussian_pyramid.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace sift_extractor::detail {
namespace {

std::vector<float> make_gaussian_kernel(float sigma) {
  if (!(sigma > 0.0f) || !std::isfinite(sigma))
    throw std::invalid_argument("Gaussian sigma must be finite and positive");
  const int radius = std::max(1, static_cast<int>(std::ceil(3.0f * sigma)));
  std::vector<float> weights(static_cast<size_t>(2 * radius + 1));
  double sum = 0.0;
  for (int offset = -radius; offset <= radius; ++offset) {
    const double position = static_cast<double>(offset);
    const double value =
        std::exp(-(position * position) / (2.0 * sigma * sigma));
    weights[static_cast<size_t>(offset + radius)] = static_cast<float>(value);
    sum += value;
  }
  for (float &weight : weights)
    weight = static_cast<float>(weight / sum);
  return weights;
}

} // namespace

std::vector<GaussianLevel> OpenCLGaussianPyramid::build(
    const std::vector<float> &image, int width, int height, int octave_count,
    int intervals, float base_sigma) {
  if (width <= 0 || height <= 0 || octave_count <= 0 || intervals <= 0 ||
      !std::isfinite(base_sigma) || base_sigma <= 0.0f)
    throw std::invalid_argument("Invalid Gaussian pyramid parameters");
  if (image.size() != static_cast<size_t>(width) * height)
    throw std::invalid_argument("Image buffer size does not match dimensions");

  const int levels_per_octave = intervals + 3;
  const float scale_step = std::pow(2.0f, 1.0f / intervals);
  std::vector<GaussianLevel> levels;
  levels.reserve(static_cast<size_t>(octave_count) * levels_per_octave);

  std::vector<float> octave_base = image;
  int octave_width = width;
  int octave_height = height;
  float previous_sigma = 0.0f;

  for (int octave = 0; octave < octave_count; ++octave) {
    std::vector<float> current = octave_base;
    float sigma_at_previous_level = previous_sigma;

    for (int scale = 0; scale < levels_per_octave; ++scale) {
      const float target_sigma =
          base_sigma * std::pow(scale_step, static_cast<float>(scale));
      const float variance = target_sigma * target_sigma -
                             sigma_at_previous_level * sigma_at_previous_level;
      if (variance < -1e-5f)
        throw std::logic_error("Gaussian pyramid sigma decreased between levels");
      if (variance > 1e-8f) {
        const float incremental_sigma = std::sqrt(variance);
        current = primitives_.apply(current, octave_width, octave_height,
                                    make_gaussian_kernel(incremental_sigma));
      }

      GaussianLevel level;
      level.octave = octave;
      level.scale = scale;
      level.width = octave_width;
      level.height = octave_height;
      level.sigma = target_sigma;
      level.pixels = current;
      levels.push_back(std::move(level));
      sigma_at_previous_level = target_sigma;
    }

    if (octave + 1 < octave_count) {
      const GaussianLevel &downsample_source =
          levels[static_cast<size_t>(octave) * levels_per_octave + intervals];
      int next_width = 0;
      int next_height = 0;
      octave_base = primitives_.downsample_by_two(
        downsample_source.pixels, octave_width, octave_height, next_width,
        next_height);
      octave_width = next_width;
      octave_height = next_height;
      previous_sigma = base_sigma;
    }
  }

  return levels;
}

std::vector<DoGLevel> OpenCLGaussianPyramid::difference_levels(
    const std::vector<GaussianLevel> &gaussian_levels, int octave_count,
    int intervals) {
  if (octave_count <= 0 || intervals <= 0)
    throw std::invalid_argument("Octave count and intervals must be positive");
  const int gaussian_levels_per_octave = intervals + 3;
  const size_t expected_count =
      static_cast<size_t>(octave_count) * gaussian_levels_per_octave;
  if (gaussian_levels.size() != expected_count)
    throw std::invalid_argument("Gaussian level count does not match pyramid configuration");

  std::vector<DoGLevel> differences;
  differences.reserve(static_cast<size_t>(octave_count) * (intervals + 2));
  for (int octave = 0; octave < octave_count; ++octave) {
    const size_t octave_offset =
        static_cast<size_t>(octave) * gaussian_levels_per_octave;
    for (int scale = 0; scale < intervals + 2; ++scale) {
      const GaussianLevel &lower =
          gaussian_levels[octave_offset + static_cast<size_t>(scale)];
      const GaussianLevel &upper =
          gaussian_levels[octave_offset + static_cast<size_t>(scale + 1)];
      if (lower.octave != octave || upper.octave != octave ||
          lower.scale != scale || upper.scale != scale + 1 ||
          lower.width != upper.width || lower.height != upper.height)
        throw std::invalid_argument("Gaussian levels are not a contiguous octave pyramid");

      DoGLevel difference;
      difference.octave = octave;
      difference.scale = scale;
      difference.width = lower.width;
      difference.height = lower.height;
      difference.sigma = std::sqrt(lower.sigma * upper.sigma);
      difference.pixels = primitives_.difference_of_gaussians(
          upper.pixels, lower.pixels, difference.width, difference.height);
      differences.push_back(std::move(difference));
    }
  }
  return differences;
}

} // namespace sift_extractor::detail
