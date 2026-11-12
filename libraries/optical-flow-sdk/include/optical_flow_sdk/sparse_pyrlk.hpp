// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/backend.hpp"
#include "optical_flow_sdk/types.hpp"

#include <cstdint>
#include <vector>

namespace optical_flow_sdk {

struct Point2f {
  float x = 0.0f;
  float y = 0.0f;
};

struct SparsePyrLKOptions {
  int max_level = 3;
  int win_size = 21;
  int max_iters = 20;
  float epsilon = 0.01f;
  float min_eig = 1e-4f;
};

// Sparse pyramidal Lucas-Kanade tracker (Bouguet). Backend::OpenCL uses the
// device path when OPTICALFLOW_HAS_OPENCL; Auto prefers OpenCL then CPU.
class SparsePyrLK {
public:
  SparsePyrLK();
  explicit SparsePyrLK(SparsePyrLKOptions options, Backend backend = Backend::Auto);

  void calc(const ImageView &prev, const ImageView &next, const std::vector<Point2f> &prev_pts,
            std::vector<Point2f> &next_pts, std::vector<std::uint8_t> &status,
            std::vector<float> &err) const;

  const SparsePyrLKOptions &options() const { return options_; }
  Backend backend() const { return backend_; }

private:
  SparsePyrLKOptions options_;
  Backend backend_ = Backend::Cpu;
  void calc_cpu(const ImageView &prev, const ImageView &next, const std::vector<Point2f> &prev_pts,
                std::vector<Point2f> &next_pts, std::vector<std::uint8_t> &status,
                std::vector<float> &err) const;
};

} // namespace optical_flow_sdk
