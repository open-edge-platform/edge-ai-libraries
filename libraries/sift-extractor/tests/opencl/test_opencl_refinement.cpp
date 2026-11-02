#include "opencl_extrema.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

namespace {

float quadratic(float peak, float x, float y, float scale, float center_x,
                float center_y, float center_scale, float curvature_x,
                float curvature_y, float curvature_scale) {
  const float dx = x - center_x;
  const float dy = y - center_y;
  const float ds = scale - center_scale;
  return peak - 0.5f * (curvature_x * dx * dx + curvature_y * dy * dy +
                        curvature_scale * ds * ds);
}

} // namespace

int main() {
  constexpr int width = 32;
  constexpr int height = 28;
  constexpr int scale_count = 5;
  std::vector<sift_extractor::detail::DoGLevel> dog(scale_count);
  for (int scale = 0; scale < scale_count; ++scale) {
    auto &level = dog[static_cast<size_t>(scale)];
    level.octave = 0;
    level.scale = scale;
    level.width = width;
    level.height = height;
    level.pixels.resize(static_cast<size_t>(width) * height);
    for (int y = 0; y < height; ++y) {
      for (int x = 0; x < width; ++x) {
        const float peak = quadratic(10.0f, static_cast<float>(x),
                   static_cast<float>(y),
                   static_cast<float>(scale), 8.2f, 7.15f,
                   2.1f, 2.0f, 2.0f, 2.0f);
        const float ridge = quadratic(5.0f, static_cast<float>(x),
                    static_cast<float>(y),
                    static_cast<float>(scale), 21.0f, 14.0f,
                    2.0f, 2.0f, 0.01f, 2.0f);
        const float value = std::max(peak, ridge);
        level.pixels[static_cast<size_t>(y) * width + x] = value;
      }
    }
  }

  try {
    sift_extractor::detail::OpenCLDoGExtrema detector;
    const auto candidates = detector.detect(dog, 1.0f);
    const bool candidates_match =
        candidates.size() == 2 && candidates[0].x == 8 && candidates[0].y == 7 &&
        candidates[0].scale == 2 && candidates[1].x == 21 &&
        candidates[1].y == 14 && candidates[1].scale == 2;
    if (!candidates_match) {
      std::fprintf(stderr, "3D extrema candidates did not match the quadratic fixture\n");
      return 1;
    }
    const auto refined = detector.refine(dog, candidates, 1.0f, 12.1f);
    const bool passed =
        refined.size() == 1 && std::abs(refined[0].x - 8.2f) < 1e-3f &&
        std::abs(refined[0].y - 7.15f) < 1e-3f &&
        std::abs(refined[0].scale - 2.1f) < 1e-3f &&
        std::abs(refined[0].response - 10.0f) < 1e-3f &&
        refined[0].edge_response < 12.1f;

    std::printf("Refined keypoints: %zu", refined.size());
    if (!refined.empty())
      std::printf(" (x=%.4f, y=%.4f, scale=%.4f, response=%.4f, edge=%.4f)",
                  refined[0].x, refined[0].y, refined[0].scale,
                  refined[0].response, refined[0].edge_response);
    std::printf("\n");
    if (!passed) {
      std::fprintf(stderr,
                   "OpenCL refinement failed subpixel or edge-response checks\n");
      return 1;
    }

    auto two_octaves = dog;
    for (auto level : dog) {
      level.octave = 1;
      two_octaves.push_back(std::move(level));
    }
    const auto mapped = detector.detect_pyramid(two_octaves, 2, 3, 1.6f,
                                                1.0f, 12.1f);
    if (mapped.size() != 2)
      return 1;
    for (size_t index = 0; index < mapped.size(); ++index) {
      const auto &point = mapped[index];
      const float factor = std::ldexp(1.0f, static_cast<int>(index));
      const float expected_sigma = 1.6f * std::exp2(2.6f / 3.0f);
      if (point.octave != static_cast<int>(index) ||
          std::abs(point.image_x - 8.2f * factor) > 1e-3f ||
          std::abs(point.image_y - 7.15f * factor) > 1e-3f ||
          std::abs(point.octave_sigma - expected_sigma) > 1e-3f ||
          std::abs(point.image_sigma - expected_sigma * factor) > 1e-3f)
        return 1;
    }

    const std::vector<float> blank(static_cast<size_t>(width) * height, 0.0f);
    if (!detector.detect_image(blank, width, height, 2, 3, 1.6f, 1.0f,
                                12.1f).empty())
      return 1;

    constexpr int texture_width = 129;
    constexpr int texture_height = 97;
    std::vector<float> texture(texture_width * texture_height);
    for (int row = 0; row < texture_height; ++row) {
      for (int column = 0; column < texture_width; ++column)
        texture[static_cast<size_t>(row) * texture_width + column] =
            static_cast<float>((column * 37 + row * 61 + column * row) & 255);
    }
    const auto detected = detector.detect_image(texture, texture_width,
        texture_height, 2, 3, 1.6f, 0.1f, 12.1f);
    if (detected.empty())
      return 1;
    for (const auto &point : detected) {
      if (!std::isfinite(point.image_sigma) || point.image_sigma <= 0.0f ||
          point.image_x < 0.0f || point.image_x >= texture_width ||
          point.image_y < 0.0f || point.image_y >= texture_height)
        return 1;
    }
    std::printf("Mapped two analytic octaves; image detector found %zu points; "
                "blank input found none\n", detected.size());

    sift_extractor::detail::GaussianLevel ramp;
    ramp.width = 65;
    ramp.height = 65;
    ramp.sigma = 2.0f;
    ramp.pixels.resize(65 * 65);
    sift_extractor::detail::ScaleSpaceKeypoint sample;
    sample.local.x = 32.0f;
    sample.local.y = 32.0f;
    sample.octave_sigma = 2.0f;
    sample.image_sigma = 2.0f;
    sample.image_x = 32.0f;
    sample.image_y = 32.0f;
    std::array<float, 128> horizontal_descriptor{};
    for (float degrees : {0.0f, 90.0f, 45.0f, 355.0f}) {
      const float radians = degrees * 3.14159265358979323846f / 180.0f;
      for (int row = 0; row < ramp.height; ++row) {
        for (int column = 0; column < ramp.width; ++column)
          ramp.pixels[static_cast<size_t>(row) * ramp.width + column] =
              std::cos(radians) * (column - 32) +
              std::sin(radians) * (row - 32);
      }
      const auto oriented = detector.assign_orientations(ramp, {sample});
      if (oriented.size() != 1)
        return 1;
      float angle_error = std::abs(oriented[0].orientation_degrees - degrees);
      angle_error = std::min(angle_error, 360.0f - angle_error);
      if (angle_error > 0.1f) {
        std::fprintf(stderr, "Gradient angle %.2f returned %.4f\n", degrees,
                     oriented[0].orientation_degrees);
        return 1;
      }
      const auto features = detector.compute_descriptors(ramp, oriented);
      if (features.size() != 1) return 1;
      double norm_squared = 0.0;
      for (float value : features[0].descriptor) {
        if (!std::isfinite(value) || value < 0.0f) return 1;
        norm_squared += static_cast<double>(value) * value;
      }
      if (std::abs(std::sqrt(norm_squared) - 1.0) > 1e-5) return 1;
      if (degrees == 0.0f) horizontal_descriptor = features[0].descriptor;
      if (degrees == 90.0f) {
        float max_rotation_error = 0.0f;
        for (size_t bin = 0; bin < 128; ++bin)
          max_rotation_error = std::max(max_rotation_error,
              std::abs(horizontal_descriptor[bin] - features[0].descriptor[bin]));
        std::printf("90-degree ramp descriptor max error %.8f\n", max_rotation_error);
        if (max_rotation_error > 1e-4f) return 1;
      }
    }
    for (int row = 0; row < ramp.height; ++row) {
      for (int column = 0; column < ramp.width; ++column)
        ramp.pixels[static_cast<size_t>(row) * ramp.width + column] =
            static_cast<float>(std::abs(column - 32));
    }
    const auto secondary_peaks = detector.assign_orientations(ramp, {sample});
    if (secondary_peaks.size() != 2) return 1;
    std::fill(ramp.pixels.begin(), ramp.pixels.end(), 0.0f);
    if (!detector.assign_orientations(ramp, {sample}).empty()) return 1;
    std::printf("Orientation directions, secondary peaks, blank image, descriptor "
                "normalization and rotation checks passed\n");

    const auto image_features = detector.extract_image(texture, texture_width,
        texture_height, 2, 3, 1.6f, 0.1f, 12.1f);
    if (image_features.empty()) return 1;
    for (const auto &feature : image_features) {
      double norm_squared = 0.0;
      for (float value : feature.descriptor) {
        if (!std::isfinite(value) || value < 0.0f) return 1;
        norm_squared += static_cast<double>(value) * value;
      }
      if (std::abs(std::sqrt(norm_squared) - 1.0) > 1e-5) return 1;
    }
    if (!detector.extract_image(blank, width, height, 2, 3, 1.6f, 1.0f,
                                 12.1f).empty()) return 1;
    std::printf("Image-to-feature pipeline: %zu oriented descriptors\n",
                image_features.size());
  } catch (const std::exception &error) {
    std::fprintf(stderr, "OpenCL refinement failed: %s\n", error.what());
    return 1;
  }
  return 0;
}
