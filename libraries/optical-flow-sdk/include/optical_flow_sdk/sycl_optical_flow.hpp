// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/sycl_device.hpp"
#include "optical_flow_sdk/types.hpp"
#include "optical_flow_sdk/version.hpp"

#include <cstdint>
#include <memory>

#if OPTICALFLOW_HAS_SYCL

namespace optical_flow_sdk {

// SYCL DIS backend: device-resident pyramid + patch inverse search + densify.
// Advanced SYCL DIS path (secondary under Backend::Auto). Prefer OpticalFlow
// unless you need USM-resident calc_device.
class SyclOpticalFlow {
public:
  explicit SyclOpticalFlow(Preset preset = Preset::Fast);
  ~SyclOpticalFlow();

  SyclOpticalFlow(SyclOpticalFlow &&) noexcept;
  SyclOpticalFlow &operator=(SyclOpticalFlow &&) noexcept;
  SyclOpticalFlow(const SyclOpticalFlow &) = delete;
  SyclOpticalFlow &operator=(const SyclOpticalFlow &) = delete;

  // Host path: H→D frames, kernels, D→H flow (includes copies + alloc reuse).
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow) const;
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost) const;

  // Device-resident path: prev/next/flow stay in USM (no host flow readback).
  SyclU8Image create_u8_image(int width, int height) const;
  SyclFlowBuffer create_flow_buffer(int width, int height) const;
  void upload_u8(SyclU8Image &dst, const ImageView &src) const;
  void download_flow(const SyclFlowBuffer &src, FlowField &dst) const;
  void calc_device(const SyclU8Image &prev, const SyclU8Image &next, SyclFlowBuffer &flow) const;
  void finish() const;

  Preset preset() const;

private:
  void calc_impl(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost,
                 bool want_cost) const;

  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace optical_flow_sdk

#endif // OPTICALFLOW_HAS_SYCL
