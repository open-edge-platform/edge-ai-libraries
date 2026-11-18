// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "optical_flow_sdk/metrics.hpp"

#include <cmath>
#include <cstdint>
#include <fstream>
#include <stdexcept>
#include <vector>

namespace optical_flow_sdk {
namespace {

constexpr float kFloMagic = 202021.25f;

bool finite2(float a, float b) { return std::isfinite(a) && std::isfinite(b); }

} // namespace

EpeStats endpoint_error(const FlowField &pred, const FlowField &gt, int border) {
  if (pred.width != gt.width || pred.height != gt.height)
    throw std::invalid_argument("pred/gt flow shapes must match");
  if (border < 0 || border * 2 >= pred.width || border * 2 >= pred.height)
    throw std::invalid_argument("invalid EPE border");

  EpeStats stats;
  double sum = 0.0, s0 = 0.0, s1 = 0.0, s2 = 0.0;
  for (int y = border; y < pred.height - border; ++y) {
    for (int x = border; x < pred.width - border; ++x) {
      const float gu = gt.dx(x, y);
      const float gv = gt.dy(x, y);
      if (!finite2(gu, gv))
        continue;
      const float pu = pred.dx(x, y);
      const float pv = pred.dy(x, y);
      if (!finite2(pu, pv))
        continue;
      const double epe = std::sqrt(static_cast<double>((pu - gu) * (pu - gu) + (pv - gv) * (pv - gv)));
      const double mag = std::sqrt(static_cast<double>(gu * gu + gv * gv));
      sum += epe;
      ++stats.count;
      if (mag < 10.0) {
        s0 += epe;
        ++stats.count_s0_10;
      } else if (mag < 40.0) {
        s1 += epe;
        ++stats.count_s10_40;
      } else {
        s2 += epe;
        ++stats.count_s40p;
      }
    }
  }
  if (stats.count)
    stats.mean = sum / static_cast<double>(stats.count);
  if (stats.count_s0_10)
    stats.mean_s0_10 = s0 / static_cast<double>(stats.count_s0_10);
  if (stats.count_s10_40)
    stats.mean_s10_40 = s1 / static_cast<double>(stats.count_s10_40);
  if (stats.count_s40p)
    stats.mean_s40p = s2 / static_cast<double>(stats.count_s40p);
  return stats;
}

FlowField read_flo(const std::string &path) {
  std::ifstream in(path, std::ios::binary);
  if (!in)
    throw std::runtime_error("failed to open .flo: " + path);
  float magic = 0.0f;
  in.read(reinterpret_cast<char *>(&magic), sizeof(magic));
  if (magic != kFloMagic)
    throw std::runtime_error("invalid .flo magic in " + path);
  std::int32_t width = 0, height = 0;
  in.read(reinterpret_cast<char *>(&width), sizeof(width));
  in.read(reinterpret_cast<char *>(&height), sizeof(height));
  if (width <= 0 || height <= 0)
    throw std::runtime_error("invalid .flo dimensions in " + path);
  FlowField flow;
  flow.allocate(width, height);
  in.read(reinterpret_cast<char *>(flow.data.data()),
          static_cast<std::streamsize>(flow.data.size() * sizeof(float)));
  if (!in)
    throw std::runtime_error("truncated .flo payload in " + path);
  return flow;
}

void write_flo(const std::string &path, const FlowField &flow) {
  if (flow.width <= 0 || flow.height <= 0 ||
      flow.data.size() != static_cast<std::size_t>(flow.width) * flow.height * 2u)
    throw std::invalid_argument("FlowField is empty or inconsistent");
  std::ofstream out(path, std::ios::binary);
  if (!out)
    throw std::runtime_error("failed to create .flo: " + path);
  out.write(reinterpret_cast<const char *>(&kFloMagic), sizeof(kFloMagic));
  const std::int32_t width = flow.width;
  const std::int32_t height = flow.height;
  out.write(reinterpret_cast<const char *>(&width), sizeof(width));
  out.write(reinterpret_cast<const char *>(&height), sizeof(height));
  out.write(reinterpret_cast<const char *>(flow.data.data()),
            static_cast<std::streamsize>(flow.data.size() * sizeof(float)));
  if (!out)
    throw std::runtime_error("failed writing .flo: " + path);
}

} // namespace optical_flow_sdk
