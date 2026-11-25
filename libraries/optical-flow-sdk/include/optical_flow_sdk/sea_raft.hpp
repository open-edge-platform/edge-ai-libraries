// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/types.hpp"
#include "optical_flow_sdk/version.hpp"

#include <memory>
#include <string>

namespace optical_flow_sdk {

// SEA-RAFT-S via OpenVINO — P2 accuracy tier under Preset::Slow / Algorithm::SeaRaft.
// Build with -DOPTICALFLOW_ENABLE_OPENVINO=ON and provide an IR/ONNX model path
// (env OPTICALFLOW_SEA_RAFT_MODEL or constructor arg). Without OpenVINO, construction
// throws with install guidance; do not claim the NVOFA Fl-all gate until measured.
class SeaRaftOpticalFlow {
public:
  explicit SeaRaftOpticalFlow(std::string model_path = {});
  ~SeaRaftOpticalFlow();

  SeaRaftOpticalFlow(SeaRaftOpticalFlow &&) noexcept;
  SeaRaftOpticalFlow &operator=(SeaRaftOpticalFlow &&) noexcept;
  SeaRaftOpticalFlow(const SeaRaftOpticalFlow &) = delete;
  SeaRaftOpticalFlow &operator=(const SeaRaftOpticalFlow &) = delete;

  void calc(const ImageView &prev, const ImageView &next, FlowField &flow) const;
  void calc(const ImageView &prev, const ImageView &next, FlowField &flow, CostMap &cost) const;

  const std::string &model_path() const;
  bool openvino_enabled() const;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

inline bool sea_raft_available() {
#if OPTICALFLOW_HAS_OPENVINO
  return true;
#else
  return false;
#endif
}

} // namespace optical_flow_sdk
