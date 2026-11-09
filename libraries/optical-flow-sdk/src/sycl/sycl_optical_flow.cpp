// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/sycl_optical_flow.hpp"

#include "optical_flow_sdk/cpu_optical_flow.hpp"

namespace optical_flow_sdk {

SyclOpticalFlow::SyclOpticalFlow(Preset preset) : preset_(preset) {}

void SyclOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow) const {
  CostMap cost;
  calc(prev, next, flow, cost);
}

void SyclOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                           CostMap &cost) const {
  // Placeholder until SYCL DIS kernels land: keep API wiring and fall back to
  // the parity CPU path so consumers can exercise Backend::Sycl builds.
  // TODO(optical-flow-sdk): replace with USM/buffer DIS (see PLAN.md §7).
  CpuOpticalFlow cpu(preset_);
  cpu.calc(prev, next, flow, cost);
}

} // namespace optical_flow_sdk
