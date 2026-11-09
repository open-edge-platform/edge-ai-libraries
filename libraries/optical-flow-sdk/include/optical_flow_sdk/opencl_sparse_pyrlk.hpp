// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/sparse_pyrlk.hpp"
#include "optical_flow_sdk/version.hpp"

#include <memory>

#if OPTICALFLOW_HAS_OPENCL

namespace optical_flow_sdk {

// OpenCL sparse pyramidal Lucas-Kanade (same options as CPU SparsePyrLK).
class OpenCLSparsePyrLK {
public:
  OpenCLSparsePyrLK();
  explicit OpenCLSparsePyrLK(SparsePyrLKOptions options);
  ~OpenCLSparsePyrLK();

  OpenCLSparsePyrLK(OpenCLSparsePyrLK &&) noexcept;
  OpenCLSparsePyrLK &operator=(OpenCLSparsePyrLK &&) noexcept;
  OpenCLSparsePyrLK(const OpenCLSparsePyrLK &) = delete;
  OpenCLSparsePyrLK &operator=(const OpenCLSparsePyrLK &) = delete;

  void calc(const ImageView &prev, const ImageView &next, const std::vector<Point2f> &prev_pts,
            std::vector<Point2f> &next_pts, std::vector<std::uint8_t> &status,
            std::vector<float> &err) const;

  const SparsePyrLKOptions &options() const;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

} // namespace optical_flow_sdk

#endif
