// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-FileCopyrightText: Copyright (c) 2017 Mårten Björkman
// SPDX-License-Identifier: Apache-2.0 AND MIT
// SYCL reference backend (mechanics baseline).
#include "syclSift.h"
#include "syclutils.h"
#include "syclSiftH.h"
#include <sycl/sycl.hpp>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {

struct MatchHostFields {
  float score;
  float ambiguity;
  int match;
  float match_xpos;
  float match_ypos;
};

struct MatchOpts {
  // Arc sweep (SXGA/1080p): vec4 ~3x vs scalar; tile16 edged tile32/64;
  // host full/slim/none differed by <1 ms. Default = best measured combo.
  int tile = 16;          // 16 / 32 / 64
  bool vec4 = true;       // float4 dots + private query cache
  int host_mode = 1;      // 0=full AoS memcpy, 1=slim match fields, 2=none
};

MatchOpts ParseMatchOpts() {
  MatchOpts opts;
  const char *env = std::getenv("SIFT_MATCH_OPTS");
  if (!env || !*env)
    return opts;
  // Comma-separated tokens: tile16|tile32|tile64, scalar|vec4, full|slim|none
  char buf[256];
  std::strncpy(buf, env, sizeof(buf) - 1);
  buf[sizeof(buf) - 1] = '\0';
  for (char *tok = std::strtok(buf, ","); tok; tok = std::strtok(nullptr, ",")) {
    if (std::strcmp(tok, "tile16") == 0)
      opts.tile = 16;
    else if (std::strcmp(tok, "tile32") == 0)
      opts.tile = 32;
    else if (std::strcmp(tok, "tile64") == 0)
      opts.tile = 64;
    else if (std::strcmp(tok, "scalar") == 0)
      opts.vec4 = false;
    else if (std::strcmp(tok, "vec4") == 0)
      opts.vec4 = true;
    else if (std::strcmp(tok, "full") == 0)
      opts.host_mode = 0;
    else if (std::strcmp(tok, "slim") == 0)
      opts.host_mode = 1;
    else if (std::strcmp(tok, "none") == 0)
      opts.host_mode = 2;
  }
  return opts;
}

void ClearMatchFields(sycl::queue &queue, SiftPoint *points, int count) {
  if (!points || count <= 0)
    return;
  queue.submit([&](sycl::handler &command_group) {
    command_group.parallel_for(sycl::range<1>(count), [=](sycl::id<1> id) {
      SiftPoint &point = points[id[0]];
      point.score = 0.0f;
      point.ambiguity = 1.0f;
      point.match = -1;
      point.match_xpos = 0.0f;
      point.match_ypos = 0.0f;
      point.match_error = 0.0f;
    });
  });
  queue.wait();
}

template <int TileSize, bool UseVec4>
void MatchSiftDataSYCL(sycl::queue &queue, SiftPoint *first, SiftPoint *second,
                       int first_count, int second_count) {
  queue.submit([&](sycl::handler &command_group) {
    sycl::local_accessor<float, 1> second_tile(TileSize * 128, command_group);

    command_group.parallel_for(
        sycl::nd_range<1>(
            sycl::range<1>(iDivUp(first_count, TileSize) * TileSize),
            sycl::range<1>(TileSize)),
        [=](sycl::nd_item<1> item) {
          const int lane = static_cast<int>(item.get_local_id(0));
          const int first_index =
              static_cast<int>(item.get_group(0)) * TileSize + lane;
          float best_score = -1.0f;
          float second_score = -1.0f;
          int best_index = -1;

          // Cache the query descriptor once in private memory.
          alignas(16) float query[128];
          if (first_index < first_count) {
            const float *src = first[first_index].data;
            if constexpr (UseVec4) {
              for (int i = 0; i < 32; ++i) {
                const int base_dim = i * 4;
                query[base_dim + 0] = src[base_dim + 0];
                query[base_dim + 1] = src[base_dim + 1];
                query[base_dim + 2] = src[base_dim + 2];
                query[base_dim + 3] = src[base_dim + 3];
              }
            } else {
              for (int dimension = 0; dimension < 128; ++dimension)
                query[dimension] = src[dimension];
            }
          }

          for (int base = 0; base < second_count; base += TileSize) {
            const int load_index = base + lane;
            if (load_index < second_count) {
              const float *src = second[load_index].data;
              if constexpr (UseVec4) {
                for (int i = 0; i < 32; ++i) {
                  const int src_dim = i * 4;
                  const int base_dim = lane * 128 + src_dim;
                  second_tile[base_dim + 0] = src[src_dim + 0];
                  second_tile[base_dim + 1] = src[src_dim + 1];
                  second_tile[base_dim + 2] = src[src_dim + 2];
                  second_tile[base_dim + 3] = src[src_dim + 3];
                }
              } else {
                for (int dimension = 0; dimension < 128; ++dimension)
                  second_tile[lane * 128 + dimension] = src[dimension];
              }
            }
            item.barrier(sycl::access::fence_space::local_space);

            const int tile_count = sycl::min(TileSize, second_count - base);
            if (first_index < first_count) {
              for (int candidate = 0; candidate < tile_count; ++candidate) {
                float dot = 0.0f;
                if constexpr (UseVec4) {
                  sycl::float4 acc(0.0f);
                  for (int i = 0; i < 32; ++i) {
                    const int q_dim = i * 4;
                    const int base_dim = candidate * 128 + q_dim;
                    const sycl::float4 q(query[q_dim + 0], query[q_dim + 1],
                                         query[q_dim + 2], query[q_dim + 3]);
                    const sycl::float4 c(second_tile[base_dim + 0],
                                         second_tile[base_dim + 1],
                                         second_tile[base_dim + 2],
                                         second_tile[base_dim + 3]);
                    acc += q * c;
                  }
                  dot = acc.x() + acc.y() + acc.z() + acc.w();
                } else {
                  for (int dimension = 0; dimension < 128; ++dimension)
                    dot += query[dimension] *
                           second_tile[candidate * 128 + dimension];
                }

                if (dot > best_score) {
                  second_score = best_score;
                  best_score = dot;
                  best_index = base + candidate;
                } else if (dot > second_score) {
                  second_score = dot;
                }
              }
            }
            item.barrier(sycl::access::fence_space::local_space);
          }

          if (first_index < first_count) {
            first[first_index].score = best_score;
            first[first_index].match = best_index;
            first[first_index].match_xpos =
                best_index >= 0 ? second[best_index].xpos : 0.0f;
            first[first_index].match_ypos =
                best_index >= 0 ? second[best_index].ypos : 0.0f;
            // Without a second neighbor the Lowe ratio is undefined — treat as
            // maximally ambiguous so callers reject the match.
            first[first_index].ambiguity =
                (second_score >= 0.0f)
                    ? second_score / (best_score + 1e-6f)
                    : 1.0f;
          }
        });
  });
  queue.wait();
}

void DispatchMatchKernel(sycl::queue &queue, SiftPoint *first, SiftPoint *second,
                         int first_count, int second_count,
                         const MatchOpts &opts) {
  if (opts.vec4) {
    if (opts.tile == 16)
      MatchSiftDataSYCL<16, true>(queue, first, second, first_count,
                                  second_count);
    else if (opts.tile == 64)
      MatchSiftDataSYCL<64, true>(queue, first, second, first_count,
                                  second_count);
    else
      MatchSiftDataSYCL<32, true>(queue, first, second, first_count,
                                  second_count);
  } else {
    if (opts.tile == 16)
      MatchSiftDataSYCL<16, false>(queue, first, second, first_count,
                                   second_count);
    else if (opts.tile == 64)
      MatchSiftDataSYCL<64, false>(queue, first, second, first_count,
                                   second_count);
    else
      MatchSiftDataSYCL<32, false>(queue, first, second, first_count,
                                   second_count);
  }
}

struct SlimScratch {
  MatchHostFields *device = nullptr;
  MatchHostFields *host = nullptr;
  int capacity = 0;
};

SlimScratch &GetSlimScratch() {
  static SlimScratch scratch;
  return scratch;
}

void EnsureSlimScratch(sycl::queue &queue, int capacity) {
  SlimScratch &scratch = GetSlimScratch();
  if (scratch.capacity >= capacity)
    return;
  if (scratch.device)
    sycl::free(scratch.device, queue);
  std::free(scratch.host);
  scratch.device = sycl::malloc_device<MatchHostFields>(capacity, queue);
  scratch.host = static_cast<MatchHostFields *>(
      std::malloc(sizeof(MatchHostFields) * static_cast<size_t>(capacity)));
  scratch.capacity = capacity;
}

void SyncMatchResultsHost(sycl::queue &queue, SiftData &first,
                          const MatchOpts &opts) {
  if (!first.h_data || !first.d_data || first.numPts <= 0)
    return;
  if (opts.host_mode == 2)
    return;
  if (opts.host_mode == 0) {
    queue.memcpy(first.h_data, first.d_data, sizeof(SiftPoint) * first.numPts)
        .wait();
    return;
  }

  // Slim path: pack only match metadata (~5 words/pt) instead of full AoS
  // descriptors (~576 B/pt). Scratch is reused across calls.
  EnsureSlimScratch(queue, first.numPts);
  SlimScratch &scratch = GetSlimScratch();
  MatchHostFields *device_fields = scratch.device;
  SiftPoint *device_points = first.d_data;
  const int count = first.numPts;
  queue.submit([&](sycl::handler &command_group) {
    command_group.parallel_for(sycl::range<1>(count), [=](sycl::id<1> id) {
      const int index = static_cast<int>(id[0]);
      const SiftPoint &point = device_points[index];
      device_fields[index].score = point.score;
      device_fields[index].ambiguity = point.ambiguity;
      device_fields[index].match = point.match;
      device_fields[index].match_xpos = point.match_xpos;
      device_fields[index].match_ypos = point.match_ypos;
    });
  });
  queue.memcpy(scratch.host, device_fields, sizeof(MatchHostFields) * count)
      .wait();
  for (int index = 0; index < count; ++index) {
    first.h_data[index].score = scratch.host[index].score;
    first.h_data[index].ambiguity = scratch.host[index].ambiguity;
    first.h_data[index].match = scratch.host[index].match;
    first.h_data[index].match_xpos = scratch.host[index].match_xpos;
    first.h_data[index].match_ypos = scratch.host[index].match_ypos;
  }
}

} // namespace

double MatchSiftData(SiftData &first, SiftData &second) {
  TimerGPU timer;
  auto &queue = GetSyclQueue();
  const MatchOpts opts = ParseMatchOpts();

  if (first.numPts == 0) {
    return 0.0;
  }
  if (second.numPts == 0) {
    if (first.d_data)
      ClearMatchFields(queue, first.d_data, first.numPts);
    if (first.h_data) {
      for (int index = 0; index < first.numPts; ++index) {
        first.h_data[index].score = 0.0f;
        first.h_data[index].ambiguity = 1.0f;
        first.h_data[index].match = -1;
        first.h_data[index].match_xpos = 0.0f;
        first.h_data[index].match_ypos = 0.0f;
        first.h_data[index].match_error = 0.0f;
      }
    }
    return 0.0;
  }

  DispatchMatchKernel(queue, first.d_data, second.d_data, first.numPts,
                      second.numPts, opts);
  SyncMatchResultsHost(queue, first, opts);

  const double elapsed_ms = timer.read();
  std::printf("MatchSiftData time =          %.2f ms\n", elapsed_ms);
  return elapsed_ms;
}
