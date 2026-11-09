// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/types.hpp"

#include <memory>

namespace optical_flow_sdk {

// NVOFA-shaped dense optical-flow facade. Classical algorithms: DIS (default)
// and Farneback. Slow preset may map to neural accuracy in a later phase.
class OpticalFlow {
public:
  explicit OpticalFlow(Backend backend = Backend::Auto, Preset preset = Preset::Fast,
                       Algorithm algorithm = Algorithm::Dis);
  ~OpticalFlow();

  OpticalFlow(const OpticalFlow &) = delete;
  OpticalFlow &operator=(const OpticalFlow &) = delete;
  OpticalFlow(OpticalFlow &&) noexcept;
  OpticalFlow &operator=(OpticalFlow &&) noexcept;

  Backend backend() const;
  Preset preset() const;
  Algorithm algorithm() const;

  void calc(const ImageView &prev, const ImageView &next, FlowField &flow);
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost);
  void calcBoth(const ImageView &prev, const ImageView &next, FlowField &fwd, FlowField &bwd);

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace optical_flow_sdk
