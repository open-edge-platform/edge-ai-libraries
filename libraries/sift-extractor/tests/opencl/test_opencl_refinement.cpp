#include "opencl_extrema.hpp"

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
  } catch (const std::exception &error) {
    std::fprintf(stderr, "OpenCL refinement failed: %s\n", error.what());
    return 1;
  }
  return 0;
}
