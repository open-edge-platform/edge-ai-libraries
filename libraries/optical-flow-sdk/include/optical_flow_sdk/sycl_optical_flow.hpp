// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/types.hpp"
#include "optical_flow_sdk/version.hpp"

#include <memory>

#if OPTICALFLOW_HAS_SYCL

namespace optical_flow_sdk {

// SYCL DIS backend: device-resident pyramid + patch inverse search + densify.
class SyclOpticalFlow {
public:
  explicit SyclOpticalFlow(Preset preset = Preset::Fast);
  ~SyclOpticalFlow();

  SyclOpticalFlow(SyclOpticalFlow &&) noexcept;
  SyclOpticalFlow &operator=(SyclOpticalFlow &&) noexcept;
  SyclOpticalFlow(const SyclOpticalFlow &) = delete;
  SyclOpticalFlow &operator=(const SyclOpticalFlow &) = delete;

  void calc(const ImageView &prev, const ImageView &next, FlowField &flow) const;
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost) const;

  Preset preset() const;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace optical_flow_sdk

#endif // OPTICALFLOW_HAS_SYCL
