#include "syclSift.h"

#include <cmath>
#include <cstdio>
#include <vector>

namespace {

bool Check(bool condition, const char *message) {
  std::printf("%s: %s\n", condition ? "PASS" : "FAIL", message);
  return condition;
}

} // namespace

int main() {
  constexpr int width = 256;
  constexpr int height = 256;
  constexpr int capacity = 8192;
  const int pitch = iAlignUp(width, 128);

  InitSycl(0);

  std::vector<float> pixels(static_cast<size_t>(width) * height);
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      const unsigned int pattern = static_cast<unsigned int>(
          (x * 37 + y * 61 + (x * y) % 251 + ((x ^ y) * 13)) & 255);
      pixels[static_cast<size_t>(y) * width + x] = static_cast<float>(pattern);
    }
  }

  SyclImage image;
  image.Allocate(width, height, pitch, false, nullptr, pixels.data());
  image.Download();

  SiftData data;
  InitSiftData(data, capacity, true, true);
  float *temporary = AllocSiftTempMemory(width, height, 3, false);
  if (!temporary) {
    std::fprintf(stderr, "Failed to allocate SIFT temporary storage\n");
    FreeSiftData(data);
    return 1;
  }

  ExtractSift(data, image, 3, 1.0, 3.0f, 0.0f, false, temporary);

  bool passed = true;
  passed &= Check(data.numPts > 0, "textured image produces keypoints");
  passed &= Check(data.numPts <= data.maxPts, "feature count respects capacity");

  bool finite_keypoints = true;
  bool finite_descriptors = true;
  bool nonzero_descriptors = true;
  for (int i = 0; i < data.numPts; ++i) {
    const SiftPoint &point = data.h_data[i];
    finite_keypoints &= std::isfinite(point.xpos) && std::isfinite(point.ypos) &&
                        std::isfinite(point.scale) &&
                        std::isfinite(point.orientation);

    double norm_squared = 0.0;
    for (float value : point.data) {
      finite_descriptors &= std::isfinite(value);
      norm_squared += static_cast<double>(value) * value;
    }
    nonzero_descriptors &= norm_squared > 0.0;
  }

  passed &= Check(finite_keypoints, "keypoint attributes are finite");
  passed &= Check(finite_descriptors, "descriptor values are finite");
  passed &= Check(nonzero_descriptors, "descriptors are nonzero");

  std::printf("Detected features: %d\n", data.numPts);
  FreeSiftTempMemory(temporary);
  FreeSiftData(data);
  return passed ? 0 : 1;
}
