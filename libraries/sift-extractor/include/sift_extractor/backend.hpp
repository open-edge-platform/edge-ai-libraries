// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "sift_extractor/version.hpp"

#include <stdexcept>
#include <string>
#include <vector>

namespace sift_extractor {

// Dual backends with explicit dispatch. Neither OpenCL nor SYCL clears a
// single-default selection bar on current Arc evidence versus OpenCV. SYCL is
// faster on the development fixture but less repeatable; OpenCL is more stable
// on that fixture. Auto prefers SYCL when built (speed-biased), else OpenCL;
// this is NOT a quality endorsement.
enum class Backend {
  Auto = 0,
  OpenCL = 1,
  Sycl = 2,
};

inline const char *backend_name(Backend backend) {
  switch (backend) {
  case Backend::Auto:
    return "auto";
  case Backend::OpenCL:
    return "opencl";
  case Backend::Sycl:
    return "sycl";
  }
  return "unknown";
}

inline Backend backend_from_name(const std::string &name) {
  if (name == "auto") return Backend::Auto;
  if (name == "opencl") return Backend::OpenCL;
  if (name == "sycl") return Backend::Sycl;
  throw std::invalid_argument("Unknown SIFT backend name: " + name);
}

inline bool backend_available(Backend backend) {
  switch (backend) {
  case Backend::Auto:
    return SIFT_EXTRACTOR_HAS_OPENCL || SIFT_EXTRACTOR_HAS_SYCL;
  case Backend::OpenCL:
    return SIFT_EXTRACTOR_HAS_OPENCL;
  case Backend::Sycl:
    return SIFT_EXTRACTOR_HAS_SYCL;
  }
  return false;
}

inline std::vector<Backend> available_backends() {
  std::vector<Backend> backends;
  if (SIFT_EXTRACTOR_HAS_OPENCL) backends.push_back(Backend::OpenCL);
  if (SIFT_EXTRACTOR_HAS_SYCL) backends.push_back(Backend::Sycl);
  return backends;
}

// Resolve Auto to a concrete backend. Preference: SYCL (speed on Arc evidence),
// then OpenCL. Callers that need stability-first behavior should pass OpenCL
// explicitly. Throws if no enabled backend is available.
inline Backend resolve_backend(Backend requested) {
  if (requested == Backend::Auto) {
    if (SIFT_EXTRACTOR_HAS_SYCL) return Backend::Sycl;
    if (SIFT_EXTRACTOR_HAS_OPENCL) return Backend::OpenCL;
    throw std::runtime_error("No SIFT backend was enabled at build time");
  }
  if (!backend_available(requested))
    throw std::runtime_error(std::string("Requested SIFT backend is not available: ") +
                             backend_name(requested));
  return requested;
}

} // namespace sift_extractor
