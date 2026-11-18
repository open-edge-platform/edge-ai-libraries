// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "sift_extractor/sycl_extractor.hpp"
#include "syclSift.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <mutex>
#include <stdexcept>

namespace sift_extractor {
namespace {
std::mutex &legacy_mutex() {
  static std::mutex mutex;
  return mutex;
}
}

struct SyclExtractor::Impl {
  int width;
  int height;
  int pitch;
  SyclExtractorOptions options;
  SyclImage image;
  SiftData data{};
  float *scratch = nullptr;
  std::vector<float> upload;

  Impl(int image_width, int image_height, SyclExtractorOptions settings)
      : width(image_width), height(image_height), pitch(iAlignUp(image_width, 128)),
        options(settings), upload(static_cast<std::size_t>(pitch) * height, 0.0f) {}

  ~Impl() {
    if (scratch) FreeSiftTempMemory(scratch);
    FreeSiftData(data);
  }
};

SyclExtractor::SyclExtractor(int width, int height, SyclExtractorOptions options) {
  if (width < 32 || width > 3840 || height < 32 || height > 2160 ||
      options.octaves < 1 || options.octaves > 6 ||
      std::min(width, height) / (1 << (options.octaves - 1)) < 8 ||
      options.capacity < 1 || options.capacity > 262144 ||
      !std::isfinite(options.initial_blur) || options.initial_blur <= 0.0 ||
      options.initial_blur > 3.0 || !std::isfinite(options.contrast_threshold) ||
      options.contrast_threshold <= 0.0f)
    throw std::invalid_argument("Invalid SYCL extractor dimensions or options");
  std::lock_guard<std::mutex> lock(legacy_mutex());
  const auto device = GetSyclQueue().get_device();
  if (!device.is_gpu() || device.get_info<sycl::info::device::vendor_id>() != 0x8086)
    throw std::runtime_error("SYCL extractor requires an Intel GPU");
  auto state = std::make_unique<Impl>(width, height, options);
  state->image.Allocate(width, height, state->pitch, false);
  InitSiftData(state->data, options.capacity, true, true);
  state->scratch = AllocSiftTempMemory(width, height, options.octaves, false);
  if (!state->image.d_data || !state->data.h_data || !state->data.d_data || !state->scratch)
    throw std::runtime_error("SYCL extractor allocation failed");
  impl_ = std::move(state);
}

SyclExtractor::~SyclExtractor() {
  std::lock_guard<std::mutex> lock(legacy_mutex());
  impl_.reset();
}

std::vector<SiftFeature> SyclExtractor::extract(const float *pixels,
    std::size_t element_count, std::size_t row_stride) {
  std::lock_guard<std::mutex> lock(legacy_mutex());
  auto &state = *impl_;
  if (!row_stride) row_stride = static_cast<std::size_t>(state.width);
  const auto width = static_cast<std::size_t>(state.width);
  const auto rows_before_last = static_cast<std::size_t>(state.height - 1);
  if (!pixels || row_stride < width ||
      row_stride > (std::numeric_limits<std::size_t>::max() - width) / rows_before_last ||
      element_count < rows_before_last * row_stride + width)
    throw std::invalid_argument("Invalid SYCL extractor input buffer or stride");
  for (int row = 0; row < state.height; ++row) {
    const float *source = pixels + static_cast<std::size_t>(row) * row_stride;
    if (!std::all_of(source, source + width, [](float value) { return std::isfinite(value); }))
      throw std::invalid_argument("SYCL extractor input must be finite");
    std::copy_n(source, width, state.upload.data() + static_cast<std::size_t>(row) * state.pitch);
  }
  auto &queue = GetSyclQueue();
  queue.memcpy(state.image.d_data, state.upload.data(), state.upload.size() * sizeof(float)).wait_and_throw();
  ExtractSift(state.data, state.image, state.options.octaves, state.options.initial_blur,
              state.options.contrast_threshold, 0.0f, false, state.scratch);
  queue.wait_and_throw();
  if (state.data.numPts < 0 || state.data.numPts >= state.data.maxPts)
    throw std::runtime_error("SYCL extractor feature capacity reached or invalid count");
  std::vector<SiftFeature> output;
  output.reserve(static_cast<std::size_t>(state.data.numPts));
  for (int index = 0; index < state.data.numPts; ++index) {
    const auto &point = state.data.h_data[index];
    if (!std::isfinite(point.xpos) || !std::isfinite(point.ypos) ||
        !std::isfinite(point.scale) || !std::isfinite(point.orientation) ||
        !std::isfinite(point.sharpness))
      throw std::runtime_error("SYCL extractor produced invalid keypoint attributes");
    SiftFeature feature{point.xpos, point.ypos, point.scale, point.orientation, point.sharpness, {}};
    double norm = 0.0;
    for (std::size_t bin = 0; bin < feature.descriptor.size(); ++bin) {
      const float value = point.data[bin];
      if (!std::isfinite(value)) throw std::runtime_error("SYCL descriptor is not finite");
      feature.descriptor[bin] = value;
      norm += static_cast<double>(value) * value;
    }
    if (norm <= 0.0) throw std::runtime_error("SYCL descriptor is zero");
    output.push_back(feature);
  }
  return output;
}

} // namespace sift_extractor