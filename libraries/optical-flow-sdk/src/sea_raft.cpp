// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/sea_raft.hpp"

#include <cstdlib>
#include <stdexcept>
#include <utility>

namespace optical_flow_sdk {

struct SeaRaftOpticalFlow::Impl {
  std::string model_path;
};

namespace {

std::string resolve_model_path(std::string requested) {
  if (!requested.empty())
    return requested;
  if (const char *env = std::getenv("OPTICALFLOW_SEA_RAFT_MODEL")) {
    if (env[0] != '\0')
      return std::string(env);
  }
  return {};
}

[[noreturn]] void throw_unavailable(const std::string &model) {
  throw std::runtime_error(
      "SEA-RAFT OpenVINO path is not available in this build"
      " (need -DOPTICALFLOW_ENABLE_OPENVINO=ON + OpenVINO Runtime)."
      " Model path=" +
      (model.empty() ? std::string("<unset; export OPTICALFLOW_SEA_RAFT_MODEL>") : model) +
      ". P2 gate: measure KITTI train Fl-all vs NVOFA Medium on Series 2 iGPU after enabling.");
}

} // namespace

SeaRaftOpticalFlow::SeaRaftOpticalFlow(std::string model_path) : impl_(std::make_unique<Impl>()) {
  impl_->model_path = resolve_model_path(std::move(model_path));
#if !OPTICALFLOW_HAS_OPENVINO
  throw_unavailable(impl_->model_path);
#else
  // OpenVINO-linked builds still require a concrete IR/ONNX until the loader lands.
  if (impl_->model_path.empty())
    throw_unavailable(impl_->model_path);
  throw std::runtime_error(
      "SEA-RAFT OpenVINO loader stub: OpenVINO is enabled but model load/infer is not "
      "implemented yet. model=" +
      impl_->model_path);
#endif
}

SeaRaftOpticalFlow::~SeaRaftOpticalFlow() = default;
SeaRaftOpticalFlow::SeaRaftOpticalFlow(SeaRaftOpticalFlow &&) noexcept = default;
SeaRaftOpticalFlow &SeaRaftOpticalFlow::operator=(SeaRaftOpticalFlow &&) noexcept = default;

const std::string &SeaRaftOpticalFlow::model_path() const { return impl_->model_path; }

bool SeaRaftOpticalFlow::openvino_enabled() const {
#if OPTICALFLOW_HAS_OPENVINO
  return true;
#else
  return false;
#endif
}

void SeaRaftOpticalFlow::calc(const ImageView &, const ImageView &, FlowField &) const {
  throw_unavailable(impl_->model_path);
}

void SeaRaftOpticalFlow::calc(const ImageView &, const ImageView &, FlowField &, CostMap &) const {
  throw_unavailable(impl_->model_path);
}

} // namespace optical_flow_sdk
