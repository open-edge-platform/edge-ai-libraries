// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/version.hpp"

#include <stdexcept>
#include <string>
#include <vector>

namespace optical_flow_sdk {

// CPU is always available. SYCL/OpenCL are optional build-time backends.
// Auto prefers SYCL, then OpenCL, then CPU (speed-biased for Intel GPU SKUs).
enum class Backend {
  Auto = 0,
  Cpu = 1,
  OpenCL = 2,
  Sycl = 3,
};

enum class Preset {
  Slow = 0,
  Medium = 1,
  Fast = 2,
};

inline const char *backend_name(Backend backend) {
  switch (backend) {
  case Backend::Auto:
    return "auto";
  case Backend::Cpu:
    return "cpu";
  case Backend::OpenCL:
    return "opencl";
  case Backend::Sycl:
    return "sycl";
  }
  return "unknown";
}

inline Backend backend_from_name(const std::string &name) {
  if (name == "auto")
    return Backend::Auto;
  if (name == "cpu")
    return Backend::Cpu;
  if (name == "opencl")
    return Backend::OpenCL;
  if (name == "sycl")
    return Backend::Sycl;
  throw std::invalid_argument("Unknown optical-flow backend name: " + name);
}

inline const char *preset_name(Preset preset) {
  switch (preset) {
  case Preset::Slow:
    return "slow";
  case Preset::Medium:
    return "medium";
  case Preset::Fast:
    return "fast";
  }
  return "unknown";
}

inline Preset preset_from_name(const std::string &name) {
  if (name == "slow")
    return Preset::Slow;
  if (name == "medium")
    return Preset::Medium;
  if (name == "fast")
    return Preset::Fast;
  throw std::invalid_argument("Unknown optical-flow preset name: " + name);
}

inline bool backend_available(Backend backend) {
  switch (backend) {
  case Backend::Auto:
    return OPTICALFLOW_HAS_CPU || OPTICALFLOW_HAS_OPENCL || OPTICALFLOW_HAS_SYCL;
  case Backend::Cpu:
    return OPTICALFLOW_HAS_CPU;
  case Backend::OpenCL:
    return OPTICALFLOW_HAS_OPENCL;
  case Backend::Sycl:
    return OPTICALFLOW_HAS_SYCL;
  }
  return false;
}

inline std::vector<Backend> available_backends() {
  std::vector<Backend> backends;
  if (OPTICALFLOW_HAS_CPU)
    backends.push_back(Backend::Cpu);
  if (OPTICALFLOW_HAS_OPENCL)
    backends.push_back(Backend::OpenCL);
  if (OPTICALFLOW_HAS_SYCL)
    backends.push_back(Backend::Sycl);
  return backends;
}

inline Backend resolve_backend(Backend requested) {
  if (requested == Backend::Auto) {
    if (OPTICALFLOW_HAS_SYCL)
      return Backend::Sycl;
    if (OPTICALFLOW_HAS_OPENCL)
      return Backend::OpenCL;
    if (OPTICALFLOW_HAS_CPU)
      return Backend::Cpu;
    throw std::runtime_error("No optical-flow backend was enabled at build time");
  }
  if (!backend_available(requested))
    throw std::runtime_error(std::string("Requested optical-flow backend is not available: ") +
                             backend_name(requested));
  return requested;
}

} // namespace optical_flow_sdk
