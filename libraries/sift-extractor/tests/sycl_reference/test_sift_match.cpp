// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#include "syclSift.h"
#include "syclutils.h"

#include <cmath>
#include <cstdio>

namespace {

bool Check(bool condition, const char *message) {
  std::printf("%s: %s\n", condition ? "PASS" : "FAIL", message);
  return condition;
}

void SetBasisDescriptor(SiftPoint &point, int dimension, float x, float y) {
  point = {};
  point.xpos = x;
  point.ypos = y;
  point.data[dimension] = 1.0f;
}

} // namespace

int main() {
  constexpr int count = 4;
  InitSycl(0);

  SiftData first;
  SiftData second;
  InitSiftData(first, count, true, true);
  InitSiftData(second, count, true, true);

  for (int i = 0; i < count; ++i) {
    SetBasisDescriptor(first.h_data[i], i, static_cast<float>(i + 1),
                       static_cast<float>(i + 2));
    SetBasisDescriptor(second.h_data[i], i, static_cast<float>(10 + i),
                       static_cast<float>(20 + i));
  }
  first.numPts = count;
  second.numPts = count;

  auto &queue = GetSyclQueue();
  queue.memcpy(first.d_data, first.h_data, sizeof(SiftPoint) * count).wait();
  queue.memcpy(second.d_data, second.h_data, sizeof(SiftPoint) * count).wait();

  MatchSiftData(first, second);

  bool passed = true;
  for (int i = 0; i < count; ++i) {
    passed &= Check(first.h_data[i].match == i,
                    "orthogonal descriptors match their identical basis");
    passed &= Check(std::abs(first.h_data[i].score - 1.0f) < 1e-5f,
                    "best descriptor score is one");
    passed &= Check(first.h_data[i].match_xpos == second.h_data[i].xpos &&
                        first.h_data[i].match_ypos == second.h_data[i].ypos,
                    "matched keypoint coordinates are copied");
  }

  FreeSiftData(first);
  FreeSiftData(second);
  return passed ? 0 : 1;
}
