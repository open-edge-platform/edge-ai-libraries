// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "optical_flow_sdk/types.hpp"

#include <string>

namespace optical_flow_sdk {

struct EpeStats {
  double mean = 0.0;
  double mean_s0_10 = 0.0;
  double mean_s10_40 = 0.0;
  double mean_s40p = 0.0;
  std::size_t count = 0;
  std::size_t count_s0_10 = 0;
  std::size_t count_s10_40 = 0;
  std::size_t count_s40p = 0;
};

// Endpoint error vs ground-truth flow. Pixels with |gt| NaN/Inf are skipped.
EpeStats endpoint_error(const FlowField &pred, const FlowField &gt, int border = 0);

// Middlebury .flo I/O (little-endian). Used by offline accuracy harnesses.
FlowField read_flo(const std::string &path);
void write_flo(const std::string &path, const FlowField &flow);

} // namespace optical_flow_sdk
