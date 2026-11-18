// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include <sift_extractor/extractor.hpp>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
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

} // namespace

// Phase B item-10 harness: mixed-backend extract soak (single-threaded; SYCL
// reference is process-global / not concurrent) plus optional independent-context
// OpenCL concurrency. Default is exploratory (short). --release targets >=10000
// mixed calls; optional --minutes N adds a wall-clock floor (the historical
// 30-minute gate is opt-in, not implied by --release). Failures abort.
// Not a quality-floor or held-out claim.
int main(int argc, char **argv) {
  using clock = std::chrono::steady_clock;
  using sift_extractor::Backend;
  using sift_extractor::Extractor;
  using sift_extractor::backend_name;
  using sift_extractor::available_backends;
  using sift_extractor::backend_available;

  bool release = false;
  bool calls_set = false;
  bool minutes_set = false;
  std::size_t target_calls = 200;
  double min_duration_s = 5.0;
  int width = 640;
  int height = 480;
  int concurrency = 2;
  unsigned seed = 1;
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--release") {
      release = true;
      if (!calls_set) target_calls = 10000;
      if (!minutes_set) min_duration_s = 0.0;
    } else if (arg == "--calls" && i + 1 < argc) {
      const int value = std::atoi(argv[++i]);
      if (value <= 0) {
        std::fprintf(stderr, "--calls must be positive\n");
        return 2;
      }
      target_calls = static_cast<std::size_t>(value);
      calls_set = true;
    } else if (arg == "--minutes" && i + 1 < argc) {
      const double value = std::atof(argv[++i]);
      if (value < 0.0) {
        std::fprintf(stderr, "--minutes must be nonnegative\n");
        return 2;
      }
      min_duration_s = value * 60.0;
      minutes_set = true;
    } else if (arg == "--width" && i + 1 < argc) {
      width = std::atoi(argv[++i]);
    } else if (arg == "--height" && i + 1 < argc) {
      height = std::atoi(argv[++i]);
    } else if (arg == "--concurrency" && i + 1 < argc) {
      concurrency = std::atoi(argv[++i]);
    } else if (arg == "--seed" && i + 1 < argc) {
      seed = static_cast<unsigned>(std::atoi(argv[++i]));
    } else if (arg == "--help" || arg == "-h") {
      std::fprintf(stderr,
                   "usage: soak_sift_extract [--release] [--calls N] [--minutes M] "
                   "[--width W] [--height H] [--concurrency N] [--seed S]\n"
                   "  Mixed-backend soak is single-threaded (SYCL is not reentrant).\n"
                   "  --release => --calls 10000 (no duration floor unless --minutes).\n"
                   "  --concurrency runs OpenCL-only independent contexts when OpenCL is built.\n");
      return 2;
    } else {
      std::fprintf(stderr, "unknown argument: %s\n", arg.c_str());
      return 2;
    }
  }
  if (width <= 0 || height <= 0 || concurrency <= 0) {
    std::fprintf(stderr, "width/height/concurrency must be positive\n");
    return 2;
  }

  const auto backends = available_backends();
  if (backends.empty()) {
    std::fprintf(stderr, "no backends available in this build\n");
    return 1;
  }

  const auto min_duration = std::chrono::duration_cast<clock::duration>(
      std::chrono::duration<double>(min_duration_s));
  const auto image = make_image(width, height, seed);

  std::size_t mixed_calls = 0;
  std::size_t features_total = 0;
  const auto started = clock::now();

  // Phase A: single-threaded mixed-backend rotation.
  {
    std::vector<std::unique_ptr<Extractor>> extractors;
    extractors.reserve(backends.size());
    for (Backend backend : backends)
      extractors.push_back(std::make_unique<Extractor>(width, height, backend));
    while (true) {
      const auto elapsed = clock::now() - started;
      if (mixed_calls >= target_calls && elapsed >= min_duration) break;
      Extractor &extractor = *extractors[mixed_calls % extractors.size()];
      const auto features = extractor.extract(image.data(), image.size());
      features_total += features.size();
      ++mixed_calls;
      if ((mixed_calls & 0xffu) == 0u) {
        const double sec = std::chrono::duration<double>(clock::now() - started).count();
        std::fprintf(stderr, "soak mixed progress calls=%zu elapsed_s=%.1f\n", mixed_calls, sec);
      }
    }
  }

  // Phase B: independent-context OpenCL concurrency (skipped if OpenCL absent).
  std::size_t concurrent_calls = 0;
  int concurrent_failures = 0;
  std::string concurrent_error;
  bool ran_concurrency = false;
  const std::size_t concurrent_target = release ? 2000 : 100;
  if (backend_available(Backend::OpenCL) && concurrency > 1) {
    ran_concurrency = true;
    std::atomic<std::size_t> calls{0};
    std::atomic<std::size_t> feats{0};
    std::atomic<int> failures{0};
    std::mutex err_mu;
    const auto conc_started = clock::now();
    auto worker = [&](int worker_id) {
      try {
        Extractor extractor(width, height, Backend::OpenCL);
        std::size_t local = 0;
        while (calls.load(std::memory_order_relaxed) < concurrent_target) {
          if (failures.load(std::memory_order_relaxed) != 0) break;
          const auto features = extractor.extract(image.data(), image.size());
          feats.fetch_add(features.size(), std::memory_order_relaxed);
          calls.fetch_add(1, std::memory_order_relaxed);
          ++local;
          (void)worker_id;
        }
      } catch (const std::exception &error) {
        failures.fetch_add(1, std::memory_order_relaxed);
        std::lock_guard<std::mutex> lock(err_mu);
        if (concurrent_error.empty()) concurrent_error = error.what();
      }
    };
    std::vector<std::thread> threads;
    threads.reserve(static_cast<std::size_t>(concurrency));
    for (int i = 0; i < concurrency; ++i) threads.emplace_back(worker, i);
    for (auto &thread : threads) thread.join();
    concurrent_calls = calls.load();
    concurrent_failures = failures.load();
    features_total += feats.load();
    const double conc_s = std::chrono::duration<double>(clock::now() - conc_started).count();
    std::fprintf(stderr, "soak concurrency opencl calls=%zu failures=%d elapsed_s=%.1f\n",
                 concurrent_calls, concurrent_failures, conc_s);
  }

  const double elapsed_s = std::chrono::duration<double>(clock::now() - started).count();
  std::string backend_list;
  for (std::size_t i = 0; i < backends.size(); ++i) {
    if (i) backend_list += ",";
    backend_list += backend_name(backends[i]);
  }

  const char *error_json = "null";
  std::string error_owned;
  if (!concurrent_error.empty()) {
    error_owned = std::string("\"") + concurrent_error + "\"";
    error_json = error_owned.c_str();
  }

  std::printf(
      "{\"path\":\"soak\",\"release\":%s,\"width\":%d,\"height\":%d,"
      "\"concurrency\":%d,\"seed\":%u,\"backends\":\"%s\","
      "\"target_calls\":%zu,\"min_duration_s\":%.1f,\"mixed_calls\":%zu,"
      "\"concurrent_opencl\":%s,\"concurrent_calls\":%zu,\"concurrent_failures\":%d,"
      "\"concurrent_target\":%zu,\"features_total\":%zu,\"elapsed_s\":%.3f,\"error\":%s}\n",
      release ? "true" : "false", width, height, concurrency, seed, backend_list.c_str(),
      target_calls, min_duration_s, mixed_calls, ran_concurrency ? "true" : "false",
      concurrent_calls, concurrent_failures, concurrent_target, features_total, elapsed_s,
      error_json);

  if (mixed_calls < target_calls) return 1;
  if (clock::now() - started < min_duration) return 1;
  if (concurrent_failures != 0) return 1;
  if (ran_concurrency && concurrent_calls < concurrent_target) return 1;
  return 0;
}
