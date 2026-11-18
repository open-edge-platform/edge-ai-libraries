// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/optical_flow.hpp"

#include "optical_flow_sdk/cpu_optical_flow.hpp"
#include "optical_flow_sdk/farneback.hpp"
#include "optical_flow_sdk/sea_raft.hpp"

#if OPTICALFLOW_HAS_OPENCL
#include "optical_flow_sdk/opencl_farneback.hpp"
#include "optical_flow_sdk/opencl_optical_flow.hpp"
#endif
#if OPTICALFLOW_HAS_SYCL
#include "optical_flow_sdk/sycl_optical_flow.hpp"
#endif

#include <stdexcept>
#include <utility>

namespace optical_flow_sdk {

struct OpticalFlow::Impl {
  Backend backend = Backend::Cpu;
  Preset preset = Preset::Fast;
  Algorithm algorithm = Algorithm::Dis;
  std::unique_ptr<CpuOpticalFlow> cpu_dis;
  std::unique_ptr<FarnebackOpticalFlow> cpu_farneback;
  std::unique_ptr<SeaRaftOpticalFlow> sea_raft;
#if OPTICALFLOW_HAS_OPENCL
  std::unique_ptr<OpenCLOpticalFlow> opencl;
  std::unique_ptr<OpenCLFarnebackOpticalFlow> opencl_farneback;
#endif
#if OPTICALFLOW_HAS_SYCL
  std::unique_ptr<SyclOpticalFlow> sycl;
#endif
};

OpticalFlow::OpticalFlow(Backend backend, Preset preset, Algorithm algorithm)
    : impl_(std::make_unique<Impl>()) {
  impl_->backend = resolve_backend(backend);
  impl_->preset = preset;
  impl_->algorithm = algorithm;

  if (algorithm == Algorithm::SeaRaft) {
    impl_->sea_raft = std::make_unique<SeaRaftOpticalFlow>();
    return;
  }

  if (algorithm == Algorithm::Farneback) {
#if OPTICALFLOW_HAS_OPENCL
    if (impl_->backend == Backend::OpenCL) {
      impl_->opencl_farneback = std::make_unique<OpenCLFarnebackOpticalFlow>(preset);
      return;
    }
#endif
    impl_->cpu_farneback = std::make_unique<FarnebackOpticalFlow>(preset);
    return;
  }

  switch (impl_->backend) {
  case Backend::Cpu:
    impl_->cpu_dis = std::make_unique<CpuOpticalFlow>(preset);
    break;
  case Backend::OpenCL:
#if OPTICALFLOW_HAS_OPENCL
    impl_->opencl = std::make_unique<OpenCLOpticalFlow>(preset);
#else
    throw std::runtime_error("OpenCL backend was not enabled at build time");
#endif
    break;
  case Backend::Sycl:
#if OPTICALFLOW_HAS_SYCL
    impl_->sycl = std::make_unique<SyclOpticalFlow>(preset);
#else
    throw std::runtime_error("SYCL backend was not enabled at build time");
#endif
    break;
  case Backend::Auto:
    throw std::logic_error("resolve_backend left Auto unresolved");
  }
}

OpticalFlow::~OpticalFlow() = default;
OpticalFlow::OpticalFlow(OpticalFlow &&) noexcept = default;
OpticalFlow &OpticalFlow::operator=(OpticalFlow &&) noexcept = default;

Backend OpticalFlow::backend() const { return impl_->backend; }
Preset OpticalFlow::preset() const { return impl_->preset; }
Algorithm OpticalFlow::algorithm() const { return impl_->algorithm; }

void OpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow) {
  CostMap cost;
  calc(prev, next, flow, cost);
}

void OpticalFlow::calc(const ImageView &prev, const ImageView &next, FlowField &flow,
                       CostMap &cost) {
  if (impl_->algorithm == Algorithm::SeaRaft) {
    impl_->sea_raft->calc(prev, next, flow, cost);
    return;
  }
  if (impl_->algorithm == Algorithm::Farneback) {
#if OPTICALFLOW_HAS_OPENCL
    if (impl_->opencl_farneback) {
      impl_->opencl_farneback->calc(prev, next, flow, cost);
      return;
    }
#endif
    impl_->cpu_farneback->calc(prev, next, flow, cost);
    return;
  }

  switch (impl_->backend) {
  case Backend::Cpu:
    impl_->cpu_dis->calc(prev, next, flow, cost);
    break;
  case Backend::OpenCL:
#if OPTICALFLOW_HAS_OPENCL
    impl_->opencl->calc(prev, next, flow, cost);
#else
    throw std::runtime_error("OpenCL backend was not enabled at build time");
#endif
    break;
  case Backend::Sycl:
#if OPTICALFLOW_HAS_SYCL
    impl_->sycl->calc(prev, next, flow, cost);
#else
    throw std::runtime_error("SYCL backend was not enabled at build time");
#endif
    break;
  case Backend::Auto:
    throw std::logic_error("resolve_backend left Auto unresolved");
  }
}

void OpticalFlow::calcBoth(const ImageView &prev, const ImageView &next, FlowField &fwd,
                           FlowField &bwd) {
  CostMap cost_fwd;
  CostMap cost_bwd;
  calc(prev, next, fwd, cost_fwd);
  calc(next, prev, bwd, cost_bwd);
}

} // namespace optical_flow_sdk
