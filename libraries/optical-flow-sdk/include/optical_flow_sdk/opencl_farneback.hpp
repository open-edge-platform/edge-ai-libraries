// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/types.hpp"
#include "optical_flow_sdk/version.hpp"

#include <memory>

#if OPTICALFLOW_HAS_OPENCL

namespace optical_flow_sdk {

// OpenCL Farneback-class dense flow (windowed LK pyramid). Same preset dial as
// CPU Farneback; first device port uses central-diff gradients.
class OpenCLFarnebackOpticalFlow {
public:
  explicit OpenCLFarnebackOpticalFlow(Preset preset = Preset::Fast);
  ~OpenCLFarnebackOpticalFlow();

  OpenCLFarnebackOpticalFlow(OpenCLFarnebackOpticalFlow &&) noexcept;
  OpenCLFarnebackOpticalFlow &operator=(OpenCLFarnebackOpticalFlow &&) noexcept;
  OpenCLFarnebackOpticalFlow(const OpenCLFarnebackOpticalFlow &) = delete;
  OpenCLFarnebackOpticalFlow &operator=(const OpenCLFarnebackOpticalFlow &) = delete;

  void calc(const ImageView &prev, const ImageView &next, FlowField &flow) const;
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost) const;

  Preset preset() const;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace optical_flow_sdk

#endif
