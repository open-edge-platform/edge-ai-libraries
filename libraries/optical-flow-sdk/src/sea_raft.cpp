// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/sea_raft.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <utility>
#include <vector>

#if OPTICALFLOW_HAS_OPENVINO
#include <openvino/openvino.hpp>
#endif

namespace optical_flow_sdk {

struct SeaRaftOpticalFlow::Impl {
  std::string model_path;
#if OPTICALFLOW_HAS_OPENVINO
  ov::Core core;
  ov::CompiledModel compiled;
  ov::InferRequest request;
  int model_h = 0;
  int model_w = 0;
#endif
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
      ". See docs/sea_raft.md and benchmarks/README.md.");
}

#if OPTICALFLOW_HAS_OPENVINO

void fill_nchw_rgb_from_gray(const ImageView &gray, int dst_h, int dst_w, float *dst_nchw) {
  // Nearest-neighbor resize gray → RGB replicate into NCHW float 0..255.
  for (int y = 0; y < dst_h; ++y) {
    const int sy = std::min(gray.height - 1, y * gray.height / dst_h);
    const auto *row = gray.row(sy);
    for (int x = 0; x < dst_w; ++x) {
      const int sx = std::min(gray.width - 1, x * gray.width / dst_w);
      const float v = static_cast<float>(row[sx]);
      const int hw = dst_h * dst_w;
      const int ix = y * dst_w + x;
      dst_nchw[0 * hw + ix] = v;
      dst_nchw[1 * hw + ix] = v;
      dst_nchw[2 * hw + ix] = v;
    }
  }
}

#endif

} // namespace

SeaRaftOpticalFlow::SeaRaftOpticalFlow(std::string model_path) : impl_(std::make_unique<Impl>()) {
  impl_->model_path = resolve_model_path(std::move(model_path));
#if !OPTICALFLOW_HAS_OPENVINO
  throw_unavailable(impl_->model_path);
#else
  if (impl_->model_path.empty())
    throw_unavailable(impl_->model_path);

  const char *device = std::getenv("OPTICALFLOW_SEA_RAFT_DEVICE");
  const std::string device_name = (device && device[0] != '\0') ? device : "GPU";
  try {
    auto model = impl_->core.read_model(impl_->model_path);
    impl_->compiled = impl_->core.compile_model(model, device_name);
  } catch (const std::exception &ex) {
    // Fall back to CPU if GPU plugin is unavailable.
    try {
      auto model = impl_->core.read_model(impl_->model_path);
      impl_->compiled = impl_->core.compile_model(model, "CPU");
    } catch (...) {
      throw std::runtime_error(std::string("SEA-RAFT OpenVINO compile failed: ") + ex.what());
    }
  }
  impl_->request = impl_->compiled.create_infer_request();
  const auto input = impl_->compiled.input(0);
  const auto shape = input.get_shape();
  if (shape.size() != 4)
    throw std::runtime_error("SEA-RAFT model input must be NCHW 4D");
  impl_->model_h = static_cast<int>(shape[2]);
  impl_->model_w = static_cast<int>(shape[3]);
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

void SeaRaftOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow) const {
  CostMap unused;
  calc(prev, next, flow, unused);
}

void SeaRaftOpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                              CostMap &cost) const {
#if !OPTICALFLOW_HAS_OPENVINO
  (void)prev;
  (void)next;
  (void)flow;
  (void)cost;
  throw_unavailable(impl_->model_path);
#else
  prev.validate();
  next.validate();
  if (prev.width != next.width || prev.height != next.height)
    throw std::invalid_argument("SEA-RAFT prev/next size mismatch");

  const int mh = impl_->model_h;
  const int mw = impl_->model_w;
  const std::size_t plane = static_cast<std::size_t>(mh) * mw;
  std::vector<float> prev_nchw(3 * plane), next_nchw(3 * plane);
  fill_nchw_rgb_from_gray(prev, mh, mw, prev_nchw.data());
  fill_nchw_rgb_from_gray(next, mh, mw, next_nchw.data());

  ov::Tensor t0(ov::element::f32, {1, 3, static_cast<size_t>(mh), static_cast<size_t>(mw)},
                prev_nchw.data());
  ov::Tensor t1(ov::element::f32, {1, 3, static_cast<size_t>(mh), static_cast<size_t>(mw)},
                next_nchw.data());
  impl_->request.set_input_tensor(0, t0);
  impl_->request.set_input_tensor(1, t1);
  impl_->request.infer();

  const ov::Tensor out = impl_->request.get_output_tensor(0);
  const auto out_shape = out.get_shape();
  // Expect NCHW flow: 1x2xH'xW'
  if (out_shape.size() != 4 || out_shape[1] != 2)
    throw std::runtime_error("SEA-RAFT output must be 1x2xHxW flow");
  const int oh = static_cast<int>(out_shape[2]);
  const int ow = static_cast<int>(out_shape[3]);
  const float *odata = out.data<const float>();

  flow.allocate(prev.width, prev.height);
  cost.allocate(prev.width, prev.height);
  const float sx = static_cast<float>(prev.width) / static_cast<float>(ow);
  const float sy = static_cast<float>(prev.height) / static_cast<float>(oh);
  for (int y = 0; y < prev.height; ++y) {
    const int oy = std::min(oh - 1, static_cast<int>(y / sy));
    for (int x = 0; x < prev.width; ++x) {
      const int ox = std::min(ow - 1, static_cast<int>(x / sx));
      const float u = odata[0 * oh * ow + oy * ow + ox] * sx;
      const float v = odata[1 * oh * ow + oy * ow + ox] * sy;
      flow.dx(x, y) = u;
      flow.dy(x, y) = v;
      cost.at(x, y) = 0;
    }
  }
#endif
}

} // namespace optical_flow_sdk
