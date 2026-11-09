// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/types.hpp"

namespace optical_flow_sdk {

// CPU Farneback-style dense flow (polynomial neighborhood expansion on a
// Gaussian pyramid). OpenCV-free; parameters follow the usual Farneback dial.
class FarnebackOpticalFlow {
public:
  explicit FarnebackOpticalFlow(Preset preset = Preset::Fast);

  void calc(const ImageView &prev, const ImageView &next, FlowField &flow) const;
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost) const;

  Preset preset() const { return preset_; }

private:
  Preset preset_;
  double pyr_scale_;
  int levels_;
  int winsize_;
  int iterations_;
  int poly_n_;
  double poly_sigma_;
};

} // namespace optical_flow_sdk
