// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/types.hpp"

namespace optical_flow_sdk {

// CPU Dense Inverse Search (DIS-style) implementation. OpenCV-free.
class CpuOpticalFlow {
public:
  explicit CpuOpticalFlow(Preset preset = Preset::Fast);

  void calc(const ImageView &prev, const ImageView &next, FlowField &flow) const;
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost) const;

  Preset preset() const { return preset_; }

private:
  Preset preset_;
  int patch_size_;
  int patch_stride_;
  int coarsest_scale_;
  int finest_scale_;
  int gradient_descent_iters_;
  bool variational_refinement_;
};

} // namespace optical_flow_sdk
