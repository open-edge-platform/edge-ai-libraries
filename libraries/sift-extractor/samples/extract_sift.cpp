// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include <sift_extractor/extractor.hpp>

#include <cstdio>
#include <string>
#include <vector>

int main(int argc, char **argv) {
  using sift_extractor::Backend;
  using sift_extractor::Extractor;
  using sift_extractor::backend_from_name;
  using sift_extractor::backend_name;

  const int width = 64;
  const int height = 64;
  Backend backend = Backend::Auto;
  if (argc > 1) backend = backend_from_name(argv[1]);

  try {
    Extractor extractor(width, height, backend);
    std::vector<float> image(static_cast<std::size_t>(width) * height, 0.0f);
    for (int y = 0; y < height; ++y)
      for (int x = 0; x < width; ++x)
        image[static_cast<std::size_t>(y) * width + x] =
            32.0f + 40.0f * static_cast<float>((x * 17 + y * 13) % 11);
    const auto features = extractor.extract(image.data(), image.size());
    std::printf("backend=%s features=%zu\n", backend_name(extractor.backend()),
                features.size());
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "extract_sift failed: %s\n", error.what());
    return 1;
  }
}
