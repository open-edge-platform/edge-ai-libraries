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

} // namespace sift_extractor::detail
