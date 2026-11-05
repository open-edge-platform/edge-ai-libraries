// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Microbench: extract once per resolution, then time MatchSiftData under
// SIFT_MATCH_OPTS variants (tile / vec / host sync).

#include "syclSift.h"

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <unistd.h>
#include <vector>

namespace {

class SilenceStdout {
public:
  SilenceStdout() {
    fflush(stdout);
    saved_ = dup(STDOUT_FILENO);
    const int devnull = open("/dev/null", O_WRONLY);
    if (saved_ >= 0 && devnull >= 0) {
      dup2(devnull, STDOUT_FILENO);
      close(devnull);
    } else if (devnull >= 0) {
      close(devnull);
    }
  }
  ~SilenceStdout() {
    fflush(stdout);
    if (saved_ >= 0) {
      dup2(saved_, STDOUT_FILENO);
      close(saved_);
    }
  }
  SilenceStdout(const SilenceStdout &) = delete;
  SilenceStdout &operator=(const SilenceStdout &) = delete;

private:
  int saved_ = -1;
};

double median(std::vector<double> values) {
  if (values.empty())
    return 0.0;
  std::sort(values.begin(), values.end());
  const auto n = values.size();
  if (n % 2 == 1)
    return values[n / 2];
  return 0.5 * (values[n / 2 - 1] + values[n / 2]);
}

cv::Mat load_gray(const std::string &path) {
  cv::Mat image = cv::imread(path, cv::IMREAD_GRAYSCALE);
  if (image.empty())
    throw std::runtime_error("failed to load image: " + path);
  return image;
}

} // namespace

int main(int argc, char **argv) {
  if (argc < 2) {
    std::fprintf(stderr, "Usage: %s IMAGE [warmup] [runs]\n", argv[0]);
    return 2;
  }
  const std::string image_path = argv[1];
  const int warmup = argc > 2 ? std::atoi(argv[2]) : 10;
  const int runs = argc > 3 ? std::atoi(argv[3]) : 30;

  const char *variants[] = {
      "tile16,scalar,full", // previous reference default
      "tile16,scalar,slim",
      "tile16,scalar,none",
      "tile16,vec4,full",
      "tile16,vec4,slim",
      "tile16,vec4,none",
      "tile32,scalar,full",
      "tile32,scalar,slim",
      "tile32,scalar,none",
      "tile32,vec4,full",
      "tile32,vec4,slim", // new product default
      "tile32,vec4,none",
      "tile64,vec4,full",
      "tile64,vec4,slim",
      "tile64,vec4,none",
  };

  struct Size {
    int w;
    int h;
    const char *name;
  };
  const Size sizes[] = {{1280, 960, "SXGA"}, {1920, 1080, "1080p"}};

  InitSycl(0);
  cv::Mat src = load_gray(image_path);

  std::cout << "# SYCL MatchSiftData optimization sweep\n\n";
  std::cout << "Fixture: `" << image_path << "` warmup=" << warmup
            << " runs=" << runs << " (median)\n\n";
  std::cout << "| Size | Features | Opts | Match (ms) | Match FPS |\n";
  std::cout << "| --- | ---: | --- | ---: | ---: |\n";

  for (const Size &size : sizes) {
    cv::Mat resized;
    cv::resize(src, resized, cv::Size(size.w, size.h));
    cv::Mat f32;
    // SYCL extract expects 0..255 float pixels (same as resolution_ladder_bench).
    resized.convertTo(f32, CV_32FC1);

    const int pitch = iAlignUp(size.w, 128);
    std::vector<float> packed(static_cast<std::size_t>(pitch) * size.h, 0.0f);
    for (int y = 0; y < size.h; ++y)
      std::memcpy(packed.data() + static_cast<std::size_t>(y) * pitch,
                  f32.ptr<float>(y),
                  static_cast<std::size_t>(size.w) * sizeof(float));

    SyclImage image;
    image.Allocate(size.w, size.h, pitch, true);
    std::memcpy(image.h_data, packed.data(), packed.size() * sizeof(float));

    SiftData data{};
    InitSiftData(data, 32768, true, true);
    float *scratch = AllocSiftTempMemory(size.w, size.h, 5, false);
    auto &queue = GetSyclQueue();
    {
      SilenceStdout silence;
      queue.memcpy(image.d_data, packed.data(), packed.size() * sizeof(float))
          .wait();
      ExtractSift(data, image, 5, 1.0, 3.0f, 0.0f, false, scratch);
      queue.wait();
    }
    const int features = data.numPts;
    if (features < 10) {
      std::cout << "| " << size.name << " | " << features
                << " | — | skip | — |\n";
      FreeSiftTempMemory(scratch);
      FreeSiftData(data);
      continue;
    }

    for (const char *opts : variants) {
      setenv("SIFT_MATCH_OPTS", opts, 1);
      {
        SilenceStdout silence;
        for (int i = 0; i < warmup; ++i)
          MatchSiftData(data, data);
      }
      std::vector<double> times;
      times.reserve(static_cast<std::size_t>(runs));
      {
        SilenceStdout silence;
        for (int i = 0; i < runs; ++i) {
          const auto start = std::chrono::steady_clock::now();
          MatchSiftData(data, data);
          const auto end = std::chrono::steady_clock::now();
          times.push_back(
              std::chrono::duration<double, std::milli>(end - start).count());
        }
      }
      const double ms = median(times);
      const double fps = ms > 0.0 ? 1000.0 / ms : 0.0;
      std::cout << "| " << size.name << " | " << features << " | `" << opts
                << "` | " << std::fixed << std::setprecision(2) << ms << " | "
                << std::setprecision(0) << fps << " |\n";
      std::cerr << size.name << " " << opts << " " << ms << " ms\n";
    }

    FreeSiftTempMemory(scratch);
    FreeSiftData(data);
  }
  return 0;
}
