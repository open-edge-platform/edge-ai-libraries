// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/opencl_optical_flow.hpp"

#include "optical_flow_sdk/cpu_optical_flow.hpp"

namespace optical_flow_sdk {

OpenCLOpticalFlow::OpenCLOpticalFlow(Preset preset) : preset_(preset) {}

void OpenCLOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow) const {
  CostMap cost;
  calc(prev, next, flow, cost);
}

void OpenCLOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                             CostMap &cost) const {
  // Placeholder until OpenCL DIS kernels land: keep API wiring and fall back to
  // the parity CPU path so consumers can exercise Backend::OpenCL builds.
  // TODO(optical-flow-sdk): replace with device-resident DIS (see PLAN.md §7).
  CpuOpticalFlow cpu(preset_);
  cpu.calc(prev, next, flow, cost);
}

} // namespace optical_flow_sdk
