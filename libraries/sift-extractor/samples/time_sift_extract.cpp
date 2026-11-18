// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include <sift_extractor/extractor.hpp>

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<float> make_image(int width, int height, unsigned seed) {
  std::vector<float> image(static_cast<std::size_t>(width) * height);
  for (int y = 0; y < height; ++y)
    for (int x = 0; x < width; ++x)
      image[static_cast<std::size_t>(y) * width + x] =
          32.0f + 40.0f * static_cast<float>(((x * 17 + y * 13 + static_cast<int>(seed)) % 11));
  return image;
}

std::vector<float> load_pgm(const std::string &path, int *width, int *height) {
  std::ifstream input(path, std::ios::binary);
  if (!input) throw std::runtime_error("failed to open image: " + path);
  std::string magic;
  input >> magic;
  if (magic != "P5") throw std::runtime_error("only binary PGM P5 is supported");
  int max_value = 0;
  input >> *width >> *height >> max_value;
  if (!input || *width <= 0 || *height <= 0 || max_value <= 0 || max_value > 255)
    throw std::runtime_error("invalid PGM header: " + path);
  input.get(); // consume single whitespace before raster
  std::vector<unsigned char> bytes(static_cast<std::size_t>(*width) * *height);
  input.read(reinterpret_cast<char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
  if (!input) throw std::runtime_error("failed to read PGM raster: " + path);
  std::vector<float> image(bytes.size());
  for (std::size_t i = 0; i < bytes.size(); ++i) image[i] = static_cast<float>(bytes[i]);
  return image;
}

double median_ms(std::vector<double> samples) {
  if (samples.empty()) return 0.0;
  std::sort(samples.begin(), samples.end());
  const auto n = samples.size();
  if (n % 2 == 1) return samples[n / 2];
  return 0.5 * (samples[n / 2 - 1] + samples[n / 2]);
}

} // namespace

int main(int argc, char **argv) {
  using sift_extractor::Backend;
  using sift_extractor::Extractor;
  using sift_extractor::backend_from_name;
  using sift_extractor::backend_name;

  const char *backend_name_arg = argc > 1 ? argv[1] : "opencl";
  int width = argc > 2 ? std::atoi(argv[2]) : 640;
  int height = argc > 3 ? std::atoi(argv[3]) : 480;
  const int warmups = argc > 4 ? std::atoi(argv[4]) : 3;
  const int samples = argc > 5 ? std::atoi(argv[5]) : 30;
  const unsigned seed = argc > 6 ? static_cast<unsigned>(std::atoi(argv[6])) : 1;
  const char *image_path = argc > 7 ? argv[7] : nullptr;
  if (warmups < 0 || samples <= 0) {
    std::fprintf(stderr,
                 "usage: time_sift_extract [backend] [W] [H] [warmups] [samples] [seed] [image.pgm]\n");
    return 2;
  }

  try {
    Backend backend = backend_from_name(backend_name_arg);
    std::vector<float> image;
    if (image_path) {
      image = load_pgm(image_path, &width, &height);
    } else {
      if (width <= 0 || height <= 0) {
        std::fprintf(stderr, "width/height must be positive without an image path\n");
        return 2;
      }
      image = make_image(width, height, seed);
    }
    Extractor extractor(width, height, backend);
    std::size_t feature_count = 0;
    for (int i = 0; i < warmups; ++i)
      feature_count = extractor.extract(image.data(), image.size()).size();

    std::vector<double> times_ms;
    times_ms.reserve(static_cast<std::size_t>(samples));
    for (int i = 0; i < samples; ++i) {
      const auto started = std::chrono::steady_clock::now();
      const auto features = extractor.extract(image.data(), image.size());
      const auto ended = std::chrono::steady_clock::now();
      feature_count = features.size();
      times_ms.push_back(std::chrono::duration<double, std::milli>(ended - started).count());
    }

    const double med = median_ms(times_ms);
    const double mean =
        std::accumulate(times_ms.begin(), times_ms.end(), 0.0) / static_cast<double>(times_ms.size());
    const std::string image_json =
        image_path ? (std::string("\"") + image_path + "\"") : std::string("null");
    std::printf(
        "{\"path\":\"native\",\"backend\":\"%s\",\"width\":%d,\"height\":%d,"
        "\"warmups\":%d,\"samples\":%d,\"seed\":%u,\"image\":%s,\"features\":%zu,"
        "\"median_ms\":%.6f,\"mean_ms\":%.6f,\"fps_median\":%.3f}\n",
        backend_name(extractor.backend()), width, height, warmups, samples, seed, image_json.c_str(),
        feature_count, med, mean, med > 0.0 ? 1000.0 / med : 0.0);
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "time_sift_extract failed: %s\n", error.what());
    return 1;
  }
}
