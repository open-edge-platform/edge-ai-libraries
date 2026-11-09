// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/types.hpp"
#include "optical_flow_sdk/version.hpp"

#if OPTICALFLOW_HAS_SYCL

namespace optical_flow_sdk {

// SYCL DIS backend. Still CPU-fallback until device kernels land; the type
// exists so Auto dispatch and packaging wire correctly when SYCL is enabled.
class SyclOpticalFlow {
public:
  explicit SyclOpticalFlow(Preset preset = Preset::Fast);

  void calc(const ImageView &prev, const ImageView &next, FlowField &flow) const;
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost) const;

  Preset preset() const { return preset_; }

private:
  Preset preset_;
};

} // namespace optical_flow_sdk

#endif // OPTICALFLOW_HAS_SYCL
