// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "opencl_extrema.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>
#include <random>
#include <set>
#include <stdexcept>
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

    auto relocation_dog = dog;
    for (int scale = 0; scale < scale_count; ++scale) {
      for (int row = 0; row < height; ++row) {
        for (int column = 0; column < width; ++column) {
          const float horizontal = column - 8.6f;
          const float vertical = row - 7.25f;
          const float layer = scale - 2.1f;
          relocation_dog[scale].pixels[static_cast<size_t>(row) * width + column] =
              10.0f - (horizontal * horizontal + vertical * vertical -
                       1.6f * horizontal * vertical + layer * layer);
        }
      }
    }
    const auto relocation_candidates = detector.detect(relocation_dog, 1.0f);
    const auto relocated = detector.refine(relocation_dog, relocation_candidates, 1.0f, 12.1f);
    if (relocation_candidates.size() != 1 || relocation_candidates[0].x != 8 ||
        relocation_candidates[0].y != 7 || relocated.size() != 1 ||
        std::abs(relocated[0].x - 8.6f) > 1e-3f ||
        std::abs(relocated[0].y - 7.25f) > 1e-3f ||
        std::abs(relocated[0].scale - 2.1f) > 1e-3f ||
        std::abs(relocated[0].response - 10.0f) > 1e-3f) {
      std::fprintf(stderr, "Valid coupled extremum was lost instead of relocated\n");
      return 1;
    }
    auto distant_seed = relocation_candidates;
    distant_seed[0].x = 3;
    if (!detector.refine(relocation_dog, distant_seed, 1.0f, 12.1f).empty() ||
        !detector.refine(relocation_dog, relocation_candidates, 11.0f, 12.1f).empty() ||
        !detector.refine(relocation_dog, relocation_candidates, 1.0f, 10.0f).empty()) {
      std::fprintf(stderr, "Relocation bypassed iteration, contrast or edge rejection\n");
      return 1;
    }
    auto boundary_dog = dog;
    for (int scale = 0; scale < scale_count; ++scale)
      for (int row = 0; row < height; ++row)
        for (int column = 0; column < width; ++column)
          boundary_dog[scale].pixels[static_cast<size_t>(row) * width + column] =
              quadratic(10.0f, column, row, scale, -0.6f, 7.15f, 2.1f, 2.0f, 2.0f, 2.0f);
    auto boundary_seed = relocation_candidates;
    boundary_seed[0].x = 1;
    if (!detector.refine(boundary_dog, boundary_seed, 1.0f, 12.1f).empty()) {
      std::fprintf(stderr, "Relocation accepted a peak outside the image interior\n");
      return 1;
    }
    std::printf("Bounded relocation recovers coupled extrema and preserves rejection filters\n");

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

    constexpr int noise_width = 1025;
    constexpr int noise_height = 769;
    std::mt19937 generator(47);
    std::vector<float> noise(noise_width * noise_height);
    for (auto &value : noise) value = static_cast<float>(generator() & 255);
    sift_extractor::detail::OpenCLGaussianPyramid collision_pyramid;
    size_t localized_collisions = 0;
    for (const int intervals : {3, 5}) {
      for (const float sigma : {1.0f, 1.6f}) {
        const auto points = detector.detect_image(noise, noise_width,
            noise_height, 3, intervals, sigma, 0.1f, 12.1f);
        const auto host_levels = collision_pyramid.build_with_differences(
            noise, noise_width, noise_height, 3, intervals, sigma);
        const auto host_points = detector.detect_pyramid(host_levels.differences,
            3, intervals, sigma, 0.1f, 12.1f);
        if (points.empty() || points.size() != host_points.size()) return 1;
        size_t expected_index = 0;
        for (int octave = 0; octave < 3; ++octave) {
          const auto begin = host_levels.differences.begin() + octave * (intervals + 2);
          const std::vector<sift_extractor::detail::DoGLevel> octave_levels(
              begin, begin + intervals + 2);
          const auto candidates = detector.detect(octave_levels, 0.1f);
          const auto raw_points = detector.refine(octave_levels, candidates, 0.1f, 12.1f);
          std::set<std::array<float, 3>> first_locations;
          for (const auto &expected : raw_points) {
            if (!first_locations.insert({expected.x, expected.y, expected.scale}).second) {
              ++localized_collisions;
              continue;
            }
            if (expected_index >= host_points.size()) return 1;
            const auto &actual = host_points[expected_index++];
            if (actual.octave != octave || actual.local.x != expected.x ||
                actual.local.y != expected.y || actual.local.scale != expected.scale ||
                actual.local.response != expected.response ||
                actual.local.edge_response != expected.edge_response) {
              std::fprintf(stderr, "Deduplication changed first-occurrence point ordering\n");
              return 1;
            }
          }
        }
        if (expected_index != host_points.size()) return 1;
        for (size_t index = 0; index < points.size(); ++index) {
          const auto &actual = points[index];
          const auto &expected = host_points[index];
          if (actual.octave != expected.octave || actual.local.x != expected.local.x ||
              actual.local.y != expected.local.y || actual.local.scale != expected.local.scale ||
              actual.local.response != expected.local.response ||
              actual.local.edge_response != expected.local.edge_response) {
            std::fprintf(stderr, "Deduplicated host and resident point ordering differs\n");
            return 1;
          }
        }
        std::set<std::array<float, 4>> locations;
        size_t duplicates = 0;
        for (const auto &point : points)
          if (!locations.insert({static_cast<float>(point.octave), point.local.x,
                                 point.local.y, point.local.scale}).second)
            ++duplicates;
        std::printf("Localized points: intervals=%d sigma=%.1f total=%zu duplicates=%zu\n",
                    intervals, sigma, points.size(), duplicates);
        if (duplicates != 0) {
          std::fprintf(stderr, "Distinct extrema seeds converged to duplicate localized points\n");
          return 1;
        }
      }
    }
    if (localized_collisions == 0) return 1;
    std::printf("Independent ordered-set reference preserved first occurrences across %zu collisions\n",
                localized_collisions);

    size_t compacted_checks = 0;
    for (const auto shape : {std::array<int, 3>{3, 3, 3},
                             std::array<int, 3>{18, 18, 3},
                             std::array<int, 3>{71, 53, 5},
                             std::array<int, 3>{19, 21, 7}}) {
      std::vector<sift_extractor::detail::DoGLevel> levels(shape[2]);
      for (int scale = 0; scale < shape[2]; ++scale) {
        auto &level = levels[scale];
        level.width = shape[0];
        level.height = shape[1];
        level.scale = scale;
        level.pixels.resize(static_cast<size_t>(shape[0]) * shape[1]);
        for (int row = 0; row < shape[1]; ++row)
          for (int column = 0; column < shape[0]; ++column)
            level.pixels[static_cast<size_t>(row) * shape[0] + column] =
                scale == shape[2] / 2 && row % 4 == 1 && column % 4 == 1
                    ? (column % 8 == 1 ? 10.0f : -10.0f) : 0.0f;
      }
      for (int pass = 0; pass < 3; ++pass) {
        const auto reference_candidates = detector.detect(levels, 1.0f);
        const auto reference = detector.refine(levels, reference_candidates, 1.0f, 12.1f);
        const auto compacted = detector.detect_pyramid(levels, 1, shape[2] - 2,
                                                        1.6f, 1.0f, 12.1f);
        if (reference.size() != compacted.size() || (pass == 0 && reference.empty()))
          return 1;
        for (size_t index = 0; index < reference.size(); ++index) {
          const auto &expected = reference[index];
          const auto &actual = compacted[index].local;
          if (actual.x != expected.x || actual.y != expected.y ||
              actual.scale != expected.scale || actual.response != expected.response ||
              actual.edge_response != expected.edge_response) return 1;
        }
        ++compacted_checks;
        for (auto &level : levels)
          for (size_t index = 0; index < level.pixels.size(); ++index)
            level.pixels[index] = pass == 0
                ? static_cast<float>((index * 37 + level.scale * 61) % 251) : 0.0f;
      }
    }
    std::printf("Stable compacted refinement matches host reference in %zu cases\n",
                compacted_checks);

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
    sift_extractor::detail::OrientedKeypoint horizontal_orientation;
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
      if (degrees == 0.0f) {
        horizontal_descriptor = features[0].descriptor;
        horizontal_orientation = oriented[0];
      }
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
        ramp.pixels[static_cast<size_t>(row) * ramp.width + column] = row - 32;
    }
    const auto changed_image_feature =
        detector.compute_descriptors(ramp, {horizontal_orientation});
    if (changed_image_feature.size() != 1 ||
        changed_image_feature[0].descriptor == horizontal_descriptor) {
      std::fprintf(stderr, "Descriptor reused gradients from mutated image\n");
      return 1;
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

    sift_extractor::detail::OpenCLDoGExtrema serial_detector(true);
    sift_extractor::detail::GaussianLevel descriptor_image;
    descriptor_image.width = texture_width;
    descriptor_image.height = texture_height;
    descriptor_image.pixels = texture;
    std::vector<sift_extractor::detail::OrientedKeypoint> descriptor_points;
    for (float sigma : {0.1f, 1.6f, 3.2f, 12.0f, 4096.0f}) {
      for (float angle : {0.0f, 0.1f, 45.0f, 90.0f, 180.0f, 270.0f, 359.9f}) {
        for (const auto position : {std::array<float, 2>{0.0f, 0.0f},
                                    std::array<float, 2>{128.0f, 96.0f},
                                    std::array<float, 2>{1.2f, 95.8f},
                                    std::array<float, 2>{127.9f, 0.1f},
                                    std::array<float, 2>{64.25f, 48.75f}}) {
          auto point = sample;
          point.local.x = point.image_x = position[0];
          point.local.y = point.image_y = position[1];
          point.octave_sigma = point.image_sigma = sigma;
          descriptor_points.push_back({point, angle});
        }
      }
    }
    for (int index = 0; index < 512; ++index) {
      auto point = sample;
      point.local.x = point.image_x = static_cast<float>((index * 37) % (texture_width * 100)) / 100.0f;
      point.local.y = point.image_y = static_cast<float>((index * 71) % (texture_height * 100)) / 100.0f;
      point.octave_sigma = point.image_sigma = 0.1f + static_cast<float>((index * 79) % 997) / 29.0f;
      descriptor_points.push_back({point, static_cast<float>((index * 137) % 36000) / 100.0f});
    }
    const auto serial_descriptors = serial_detector.compute_descriptors(
        descriptor_image, descriptor_points);
    std::vector<sift_extractor::detail::ScaleSpaceKeypoint> orientation_points;
    for (const auto &point : descriptor_points) orientation_points.push_back(point.keypoint);
    const auto serial_orientations = serial_detector.assign_orientations(descriptor_image, orientation_points);
    const auto parallel_orientations = detector.assign_orientations(descriptor_image, orientation_points);
    if (serial_orientations.size() != parallel_orientations.size()) return 1;
    for (size_t index = 0; index < serial_orientations.size(); ++index) {
      if (serial_orientations[index].keypoint.local.x != parallel_orientations[index].keypoint.local.x ||
          serial_orientations[index].keypoint.local.y != parallel_orientations[index].keypoint.local.y ||
          serial_orientations[index].orientation_degrees != parallel_orientations[index].orientation_degrees)
        return 1;
    }
    std::printf("Workgroup/serial orientations: %zu inputs, %zu exact oriented records\n",
                orientation_points.size(), serial_orientations.size());
    const auto parallel_descriptors = detector.compute_descriptors(
        descriptor_image, descriptor_points);
    const auto repeated_descriptors = detector.compute_descriptors(
        descriptor_image, descriptor_points);
    if (parallel_descriptors.size() != descriptor_points.size() ||
        serial_descriptors.size() != descriptor_points.size() ||
        repeated_descriptors.size() != descriptor_points.size()) return 1;
    float max_serial_error = 0.0f;
    for (size_t index = 0; index < descriptor_points.size(); ++index) {
      if (parallel_descriptors[index].descriptor != repeated_descriptors[index].descriptor)
        return 1;
      for (size_t bin = 0; bin < 128; ++bin) {
        const float actual = parallel_descriptors[index].descriptor[bin];
        if (!std::isfinite(actual) || actual < 0.0f) return 1;
        max_serial_error = std::max(max_serial_error,
            std::abs(actual - serial_descriptors[index].descriptor[bin]));
      }
    }
    std::printf("Workgroup/serial descriptors: %zu points, max bin error %.8f\n",
                descriptor_points.size(), max_serial_error);
    if (max_serial_error > 2e-5f) return 1;
    std::fill(descriptor_image.pixels.begin(), descriptor_image.pixels.end(), 0.0f);
    const auto zero_descriptors = detector.compute_descriptors(descriptor_image, descriptor_points);
    for (const auto &feature : zero_descriptors)
      for (float value : feature.descriptor)
        if (value != 0.0f) return 1;
    if (!detector.compute_descriptors(descriptor_image, {}).empty()) return 1;

    const auto image_features = detector.extract_image(texture, texture_width,
        texture_height, 2, 3, 1.6f, 0.1f, 12.1f);
    if (image_features.empty()) return 1;
    sift_extractor::detail::OpenCLGaussianPyramid host_pyramid;
    const auto host_levels = host_pyramid.build_with_differences(texture,
        texture_width, texture_height, 2, 3, 1.6f);
    const auto host_points = detector.detect_pyramid(host_levels.differences,
        2, 3, 1.6f, 0.1f, 12.1f);
    std::vector<std::vector<sift_extractor::detail::ScaleSpaceKeypoint>> host_groups(
        host_levels.gaussian.size());
    for (const auto &point : host_points) {
      const int level = std::clamp(static_cast<int>(std::lround(point.local.scale)), 0, 5);
      host_groups[static_cast<size_t>(point.octave) * 6 + level].push_back(point);
    }
    std::vector<sift_extractor::detail::SiftFeature> host_features;
    for (size_t group = 0; group < host_groups.size(); ++group) {
      if (host_groups[group].empty()) continue;
      const auto oriented = detector.assign_orientations(host_levels.gaussian[group], host_groups[group]);
      const auto features = detector.compute_descriptors(host_levels.gaussian[group], oriented);
      host_features.insert(host_features.end(), features.begin(), features.end());
    }
    if (host_features.size() != image_features.size() || host_features.size() <= host_points.size()) return 1;
    for (size_t index = 0; index < image_features.size(); ++index) {
      const auto &actual = image_features[index];
      const auto &expected = host_features[index];
      if (actual.point.keypoint.image_x != expected.point.keypoint.image_x ||
          actual.point.keypoint.image_y != expected.point.keypoint.image_y ||
          actual.point.keypoint.image_sigma != expected.point.keypoint.image_sigma ||
          actual.point.keypoint.local.response != expected.point.keypoint.local.response ||
          actual.point.orientation_degrees != expected.point.orientation_degrees ||
          actual.descriptor != expected.descriptor) return 1;
    }
    std::printf("Resident pyramid feature records exactly match the host pipeline after orientation-capacity growth\n");
    for (int detector_width : {texture_width, texture_width - 1}) {
      const std::vector<float> detector_image(texture.begin(),
        texture.begin() + static_cast<size_t>(detector_width) * texture_height);
      for (int octave_count : {8, 4, 2, 1, 4}) {
        const auto reference_levels = host_pyramid.build_with_differences(detector_image,
          detector_width, texture_height, octave_count, 3, 1.6f);
        const auto reference_points = detector.detect_pyramid(reference_levels.differences,
          octave_count, 3, 1.6f, 0.1f, 12.1f);
        const auto resident_points = detector.detect_image(detector_image, detector_width,
          texture_height, octave_count, 3, 1.6f, 0.1f, 12.1f);
        if (reference_points.size() != resident_points.size()) return 1;
        for (size_t index = 0; index < reference_points.size(); ++index) {
          const auto &expected = reference_points[index];
          const auto &actual = resident_points[index];
          if (actual.octave != expected.octave || actual.image_x != expected.image_x ||
              actual.image_y != expected.image_y || actual.image_sigma != expected.image_sigma ||
              actual.local.scale != expected.local.scale || actual.local.response != expected.local.response)
            return 1;
        }
      }
    }
    std::printf("Batched detection matches synchronous reference after aligned/unaligned octave reuse\n");
    sift_extractor::detail::OpenCLDoGExtrema capacity_detector;
    for (int repeats : {1, 4, 2, 0, 4}) {
      const int capacity_width = texture_width * std::max(1, repeats);
      const int capacity_height = texture_height * std::max(1, repeats);
      std::vector<float> capacity_image(static_cast<size_t>(capacity_width) * capacity_height);
      for (int row = 0; row < capacity_height; ++row)
        for (int column = 0; column < capacity_width; ++column)
          capacity_image[static_cast<size_t>(row) * capacity_width + column] = repeats == 0 ? 0.0f :
            texture[static_cast<size_t>(row % texture_height) * texture_width + column % texture_width];
      const auto reference_levels = host_pyramid.build_with_differences(capacity_image,
        capacity_width, capacity_height, 2, 3, 1.6f);
      const auto expected = detector.detect_pyramid(reference_levels.differences, 2, 3, 1.6f, 0.1f, 12.1f);
      const auto actual = capacity_detector.detect_image(capacity_image, capacity_width,
        capacity_height, 2, 3, 1.6f, 0.1f, 12.1f);
      if (expected.size() != actual.size() || (repeats == 4 && expected.size() <= 64) ||
          (repeats == 0 && !actual.empty())) return 1;
      for (size_t index = 0; index < expected.size(); ++index) {
        const auto &reference = expected[index];
        const auto &point = actual[index];
        if (reference.octave != point.octave || reference.image_x != point.image_x ||
            reference.image_y != point.image_y || reference.image_sigma != point.image_sigma ||
            reference.octave_sigma != point.octave_sigma || reference.local.x != point.local.x ||
            reference.local.y != point.local.y || reference.local.scale != point.local.scale ||
            reference.local.response != point.local.response ||
            reference.local.edge_response != point.local.edge_response) return 1;
      }
    }
    std::printf("Candidate capacity growth, shrink and blank reuse preserve every refined record\n");
    const auto serial_features = serial_detector.extract_image(texture, texture_width,
        texture_height, 2, 3, 1.6f, 0.1f, 12.1f);
    if (serial_features.size() != image_features.size()) return 1;
    for (size_t index = 0; index < image_features.size(); ++index) {
      const auto &actual = image_features[index];
      const auto &expected = serial_features[index];
      if (actual.point.keypoint.image_x != expected.point.keypoint.image_x ||
          actual.point.keypoint.image_y != expected.point.keypoint.image_y ||
          actual.point.orientation_degrees != expected.point.orientation_degrees)
        return 1;
      for (size_t bin = 0; bin < 128; ++bin)
        if (std::abs(actual.descriptor[bin] - expected.descriptor[bin]) > 2e-5f)
          return 1;
    }
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
    detector.extract_image(texture, texture_width, texture_height, 2, 4,
                1.2f, 0.1f, 12.1f);
    const auto repeated_features = detector.extract_image(texture, texture_width,
      texture_height, 2, 3, 1.6f, 0.1f, 12.1f);
    if (repeated_features.size() != image_features.size()) return 1;
    for (size_t index = 0; index < image_features.size(); ++index) {
      const auto &expected = image_features[index];
      const auto &actual = repeated_features[index];
      if (actual.point.keypoint.image_x != expected.point.keypoint.image_x ||
        actual.point.keypoint.image_y != expected.point.keypoint.image_y ||
        actual.point.keypoint.image_sigma != expected.point.keypoint.image_sigma ||
        actual.point.orientation_degrees != expected.point.orientation_degrees ||
        actual.descriptor != expected.descriptor) return 1;
    }
    auto expected_capped = image_features;
    std::stable_sort(expected_capped.begin(), expected_capped.end(),
      [](const auto &first, const auto &second) {
        return std::abs(first.point.keypoint.local.response) >
           std::abs(second.point.keypoint.local.response);
      });
    expected_capped.resize(8);
    const auto capped_features = detector.extract_image(texture, texture_width,
      texture_height, 2, 3, 1.6f, 0.1f, 12.1f, 8);
    if (capped_features.size() != expected_capped.size()) return 1;
    for (size_t index = 0; index < capped_features.size(); ++index) {
      const auto &expected = expected_capped[index];
      const auto &actual = capped_features[index];
      if (actual.point.keypoint.image_x != expected.point.keypoint.image_x ||
        actual.point.keypoint.image_y != expected.point.keypoint.image_y ||
        actual.point.orientation_degrees != expected.point.orientation_degrees ||
        actual.descriptor != expected.descriptor) return 1;
    }
    std::printf("Reused pyramid preserves features after blank, resized and "
          "reconfigured frames\n");
    for (float invalid_value : {std::numeric_limits<float>::quiet_NaN(),
         std::numeric_limits<float>::infinity(), -std::numeric_limits<float>::infinity()}) {
      for (size_t position : {size_t{0}, texture.size() / 2, texture.size() - 1}) {
        auto invalid_image = texture;
        invalid_image[position] = invalid_value;
        bool detection_rejected = false;
        bool extraction_rejected = false;
        try {
          detector.detect_image(invalid_image, texture_width, texture_height, 2, 3, 1.6f, 0.1f, 12.1f);
        } catch (const std::invalid_argument &) {
          detection_rejected = true;
        }
        try {
          detector.extract_image(invalid_image, texture_width, texture_height, 2, 3, 1.6f, 0.1f, 12.1f);
        } catch (const std::invalid_argument &) {
          extraction_rejected = true;
        }
        if (!detection_rejected || !extraction_rejected) return 1;
      }
    }
    const auto recovered_features = detector.extract_image(texture, texture_width,
      texture_height, 2, 3, 1.6f, 0.1f, 12.1f);
    if (recovered_features.size() != image_features.size()) return 1;
    std::printf("Detection and extraction reject non-finite pixels at beginning, middle and end\n");
    std::printf("Image-to-feature pipeline: %zu oriented descriptors\n",
                image_features.size());
  } catch (const std::exception &error) {
    std::fprintf(stderr, "OpenCL refinement failed: %s\n", error.what());
    return 1;
  }
  return 0;
}
