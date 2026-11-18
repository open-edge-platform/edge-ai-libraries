// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "syclSift.h"
#include "sift_extractor/sycl_extractor.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <future>
#include <limits>
#include <stdexcept>
#include <vector>

namespace {

bool Check(bool condition, const char *message) {
  std::printf("%s: %s\n", condition ? "PASS" : "FAIL", message);
  return condition;
}

bool TestContext(const std::vector<float> &pixels, int width, int height, int expected) {
  using sift_extractor::SyclExtractor;
  using sift_extractor::SyclExtractorOptions;
  bool passed = true;
  const auto rejects = [](auto action) {
    try { action(); } catch (const std::invalid_argument &) { return true; }
    return false;
  };
  passed &= Check(rejects([&] { SyclExtractor invalid(0, height); }),
                  "context rejects invalid dimensions");
  SyclExtractorOptions options;
  options.octaves = 3;
  options.capacity = 8192;
  auto invalid_options = options;
  invalid_options.octaves = 0;
  passed &= Check(rejects([&] { SyclExtractor invalid(width, height, invalid_options); }),
                  "context rejects invalid octave options");
  invalid_options = options;
  invalid_options.capacity = 0;
  passed &= Check(rejects([&] { SyclExtractor invalid(width, height, invalid_options); }),
                  "context rejects invalid capacity");
  std::vector<sift_extractor::SiftFeature> owned;
  {
    SyclExtractor first(width, height, options);
    owned = first.extract(pixels.data(), pixels.size());
    passed &= Check(static_cast<int>(owned.size()) == expected,
                    "context matches raw extractor feature count");
    std::vector<float> blank(pixels.size(), 0.0f);
    passed &= Check(first.extract(blank.data(), blank.size()).empty(),
                    "context clears detections on a blank frame");
    passed &= Check(first.extract(pixels.data(), pixels.size()).size() == owned.size(),
                    "context recovers textured detections after blank frame");
    const std::size_t stride = static_cast<std::size_t>(width) + 7;
    std::vector<float> padded(stride * height, 0.0f);
    for (int row = 0; row < height; ++row)
      std::copy_n(pixels.data() + static_cast<std::size_t>(row) * width, width,
                  padded.data() + static_cast<std::size_t>(row) * stride);
    passed &= Check(first.extract(padded.data(), padded.size(), stride).size() == owned.size(),
                    "context accepts padded input rows");
    passed &= Check(rejects([&] { first.extract(nullptr, pixels.size()); }),
                    "context rejects null input");
    passed &= Check(rejects([&] { first.extract(pixels.data(), pixels.size() - 1); }),
                    "context rejects short input");
    passed &= Check(rejects([&] { first.extract(pixels.data(), pixels.size(), width - 1); }),
                    "context rejects short row stride");
    passed &= Check(rejects([&] {
      first.extract(pixels.data(), pixels.size(), std::numeric_limits<std::size_t>::max());
    }), "context rejects overflowing row stride");
    blank[0] = std::numeric_limits<float>::quiet_NaN();
    passed &= Check(rejects([&] { first.extract(blank.data(), blank.size()); }),
                    "context rejects nonfinite input");
    options.initial_blur = 1.2;
    SyclExtractor second(width, height, options);
    const auto second_count = second.extract(pixels.data(), pixels.size()).size();
    passed &= Check(first.extract(pixels.data(), pixels.size()).size() == owned.size(),
                    "interleaved contexts preserve their configuration");
    auto first_call = std::async(std::launch::async, [&] {
      return first.extract(pixels.data(), pixels.size()).size();
    });
    auto second_call = std::async(std::launch::async, [&] {
      return second.extract(pixels.data(), pixels.size()).size();
    });
    passed &= Check(first_call.get() == owned.size() && second_call.get() == second_count,
                    "context calls from two host threads are serialized safely");
  }
  passed &= Check(!owned.empty() && std::isfinite(owned.front().descriptor[0]),
                  "context results own their storage after destruction");
  options.capacity = 1;
  SyclExtractor limited(width, height, options);
  bool saturation_reported = false;
  try {
    limited.extract(pixels.data(), pixels.size());
  } catch (const std::runtime_error &) {
    saturation_reported = true;
  }
  passed &= Check(saturation_reported, "context reports capacity saturation");
  return passed;
}

bool TestAsyncErrorPropagation() {
  auto &queue = GetSyclQueue();
  queue.submit([](sycl::handler &handler) {
    handler.host_task([] {
      throw sycl::exception(sycl::make_error_code(sycl::errc::runtime),
                            "injected asynchronous regression failure");
    });
  });
  bool propagated = false;
  try {
    queue.wait_and_throw();
  } catch (const sycl::exception &) {
    propagated = true;
  }
  return Check(propagated, "asynchronous SYCL errors reach the waiting caller");
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
  const int expected = data.numPts;
  FreeSiftTempMemory(temporary);
  FreeSiftData(data);
  try {
    passed &= TestContext(pixels, width, height, expected);
    passed &= TestAsyncErrorPropagation();
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Context validation failed: %s\n", error.what());
    passed = false;
  }
  return passed ? 0 : 1;
}
