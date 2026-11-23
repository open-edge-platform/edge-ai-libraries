// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Native smoke sample: extract SIFT on a synthetic pair, then Lowe-ratio match
// (OpenCLMatcher when built; otherwise host dot-product fallback).
#include <sift_extractor/extractor.hpp>
#include <sift_extractor/features.hpp>
#include <sift_extractor/version.hpp>

#if SIFT_EXTRACTOR_HAS_OPENCL
#include <sift_extractor/opencl_matcher.hpp>
#endif

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace {

constexpr float kLoweRatio = 0.8f;

struct MatchResult {
  int match = -1;
  float score = 0.0f;
  float ambiguity = 1.0f;
};

// Several offset Gaussians so extract finds keypoints and a small translation
// still leaves ratio-test survivors after match.
std::vector<float> make_scene(int width, int height, float tx, float ty) {
  std::vector<float> image(static_cast<std::size_t>(width) * height, 16.0f);
  const struct {
    float x, y, sigma, amp;
  } blobs[] = {
      {0.30f, 0.35f, 5.0f, 200.0f}, {0.55f, 0.40f, 4.0f, 180.0f},
      {0.40f, 0.65f, 6.0f, 190.0f}, {0.70f, 0.70f, 4.5f, 170.0f},
      {0.22f, 0.75f, 3.5f, 160.0f}, {0.78f, 0.28f, 5.5f, 185.0f},
  };
  for (int y = 0; y < height; ++y) {
    for (int x = 0; x < width; ++x) {
      float v = 16.0f;
      for (const auto &b : blobs) {
        const float dx =
            static_cast<float>(x) - (b.x * static_cast<float>(width) + tx);
        const float dy =
            static_cast<float>(y) - (b.y * static_cast<float>(height) + ty);
        v += b.amp * std::exp(-(dx * dx + dy * dy) / (2.0f * b.sigma * b.sigma));
      }
      image[static_cast<std::size_t>(y) * width + x] = v;
    }
  }
  return image;
}

std::vector<MatchResult> match_features_host(
    const std::vector<sift_extractor::SiftFeature> &query,
    const std::vector<sift_extractor::SiftFeature> &train) {
  std::vector<MatchResult> out(query.size());
  for (std::size_t qi = 0; qi < query.size(); ++qi) {
    float best = -1.0f;
    float second = -1.0f;
    int best_index = -1;
    for (std::size_t ti = 0; ti < train.size(); ++ti) {
      float score = 0.0f;
      for (int d = 0; d < 128; ++d)
        score += query[qi].descriptor[static_cast<std::size_t>(d)] *
                 train[ti].descriptor[static_cast<std::size_t>(d)];
      if (score > best) {
        second = best;
        best = score;
        best_index = static_cast<int>(ti);
      } else if (score > second) {
        second = score;
      }
    }
    out[qi].match = best_index;
    out[qi].score = best;
    out[qi].ambiguity = second / (best + 1.0e-6f);
  }
  return out;
}

std::size_t count_ratio_matches(const std::vector<MatchResult> &raw, float ratio) {
  std::size_t accepted = 0;
  for (const auto &m : raw) {
    if (m.match < 0) continue;
    if (m.ambiguity < ratio) ++accepted;
  }
  return accepted;
}

} // namespace

int main(int argc, char **argv) {
  using sift_extractor::Backend;
  using sift_extractor::Extractor;
  using sift_extractor::backend_from_name;
  using sift_extractor::backend_name;

  const int width = 256;
  const int height = 256;
  Backend backend = Backend::Auto;
  if (argc > 1) backend = backend_from_name(argv[1]);

  try {
    const auto image1 = make_scene(width, height, 0.0f, 0.0f);
    const auto image2 = make_scene(width, height, 8.0f, 5.0f);

    Extractor extractor(width, height, backend);
    const auto feats1 = extractor.extract(image1.data(), image1.size());
    Extractor extractor2(width, height, extractor.backend());
    const auto feats2 = extractor2.extract(image2.data(), image2.size());
    std::printf("backend=%s extract features=(%zu,%zu)\n",
                backend_name(extractor.backend()), feats1.size(), feats2.size());

    std::vector<MatchResult> raw;
    const char *matcher_name = "host";
#if SIFT_EXTRACTOR_HAS_OPENCL
    try {
      sift_extractor::OpenCLMatcher matcher;
      const auto gpu = matcher.match(feats1, feats2);
      raw.resize(gpu.size());
      for (std::size_t i = 0; i < gpu.size(); ++i) {
        raw[i].match = gpu[i].match;
        raw[i].score = gpu[i].score;
        raw[i].ambiguity = gpu[i].ambiguity;
      }
      matcher_name = "opencl";
    } catch (const std::exception &) {
      raw = match_features_host(feats1, feats2);
    }
#else
    raw = match_features_host(feats1, feats2);
#endif

    const std::size_t accepted = count_ratio_matches(raw, kLoweRatio);
    std::printf("match=%s ratio=%.2f accepted=%zu of %zu queries\n", matcher_name,
                static_cast<double>(kLoweRatio), accepted, feats1.size());
    std::size_t shown = 0;
    for (std::size_t i = 0; i < raw.size() && shown < 5; ++i) {
      if (raw[i].match < 0 || !(raw[i].ambiguity < kLoweRatio)) continue;
      const auto &q = feats1[i];
      const auto &t = feats2[static_cast<std::size_t>(raw[i].match)];
      std::printf(
          "  q[%zu] (%.1f,%.1f) -> t[%d] (%.1f,%.1f) score=%.4f ambiguity=%.4f\n",
          i, q.x, q.y, raw[i].match, t.x, t.y, raw[i].score, raw[i].ambiguity);
      ++shown;
    }
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "extract_and_match failed: %s\n", error.what());
    return 1;
  }
}
