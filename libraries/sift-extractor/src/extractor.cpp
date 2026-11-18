// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "sift_extractor/extractor.hpp"

#include <stdexcept>

namespace sift_extractor {

struct Extractor::Impl {
  Backend backend = Backend::Auto;
  int width = 0;
  int height = 0;
  ExtractorOptions options;
#if SIFT_EXTRACTOR_HAS_OPENCL
  std::unique_ptr<OpenCLExtractor> opencl;
#endif
#if SIFT_EXTRACTOR_HAS_SYCL
  std::unique_ptr<SyclExtractor> sycl;
#endif
};

Extractor::Extractor(int width, int height, Backend backend, ExtractorOptions options)
    : impl_(std::make_unique<Impl>()) {
  impl_->backend = resolve_backend(backend);
  impl_->width = width;
  impl_->height = height;
  impl_->options = options;
  switch (impl_->backend) {
  case Backend::OpenCL:
#if SIFT_EXTRACTOR_HAS_OPENCL
    impl_->opencl = std::make_unique<OpenCLExtractor>();
    break;
#else
    throw std::runtime_error("OpenCL backend was not enabled at build time");
#endif
  case Backend::Sycl:
#if SIFT_EXTRACTOR_HAS_SYCL
    impl_->sycl = std::make_unique<SyclExtractor>(width, height, options.sycl);
    break;
#else
    throw std::runtime_error("SYCL backend was not enabled at build time");
#endif
  case Backend::Auto:
    throw std::logic_error("resolve_backend left Auto unresolved");
  }
}

Extractor::~Extractor() = default;

Backend Extractor::backend() const { return impl_->backend; }
int Extractor::width() const { return impl_->width; }
int Extractor::height() const { return impl_->height; }

std::vector<SiftFeature> Extractor::extract(const float *pixels, std::size_t element_count,
                                            std::size_t row_stride) {
  switch (impl_->backend) {
  case Backend::OpenCL:
#if SIFT_EXTRACTOR_HAS_OPENCL
    return impl_->opencl->extract(pixels, impl_->width, impl_->height, element_count,
                                  impl_->options.opencl, row_stride);
#else
    break;
#endif
  case Backend::Sycl:
#if SIFT_EXTRACTOR_HAS_SYCL
    return impl_->sycl->extract(pixels, element_count, row_stride);
#else
    break;
#endif
  case Backend::Auto:
    break;
  }
  throw std::runtime_error("Extractor backend is not available");
}

} // namespace sift_extractor
