// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/types.hpp"
#include "optical_flow_sdk/version.hpp"

#if OPTICALFLOW_HAS_OPENCL

namespace optical_flow_sdk {

// OpenCL DIS backend. Kernel path lands in a follow-on change; the type exists
// so Auto dispatch and packaging wire correctly when OpenCL is enabled.
class OpenCLOpticalFlow {
public:
  explicit OpenCLOpticalFlow(Preset preset = Preset::Fast);

  void calc(const ImageView &prev, const ImageView &next, FlowField &flow) const;
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost) const;

  Preset preset() const { return preset_; }

private:
  Preset preset_;
};

} // namespace optical_flow_sdk

#endif // OPTICALFLOW_HAS_OPENCL
