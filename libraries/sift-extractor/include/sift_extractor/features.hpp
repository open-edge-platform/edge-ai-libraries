// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <array>

namespace sift_extractor {

struct SiftFeature {
  float x = 0.0f;
  float y = 0.0f;
  float scale = 0.0f;
  float orientation_degrees = 0.0f;
  float response = 0.0f;
  std::array<float, 128> descriptor{};
};

} // namespace sift_extractor
