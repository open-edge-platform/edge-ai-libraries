// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#pragma once

// Shared OpenCL SIFT match kernel source (extractor residency + OpenCLMatcher).
inline constexpr const char *kOpenCLSiftMatchKernelSource = R"CLC(
#define TILE 16
#define DESCRIPTOR_SIZE 128

__kernel void match_sift_descriptors(
    __global const float *query_desc,
    __global const float *train_desc,
    __global const float *train_xy,
    __global int *match_index,
    __global float *best_score,
    __global float *ambiguity,
    __global float *match_x,
    __global float *match_y,
    const int query_count,
    const int train_count) {
  __local float train_tile[TILE * DESCRIPTOR_SIZE];
  const int lane = get_local_id(0);
  const int query_index = get_group_id(0) * TILE + lane;

  float query[DESCRIPTOR_SIZE];
  float best = -1.0f;
  float second = -1.0f;
  int best_index = -1;

  if (query_index < query_count) {
    const int base = query_index * DESCRIPTOR_SIZE;
    for (int d = 0; d < DESCRIPTOR_SIZE; d += 4) {
      query[d + 0] = query_desc[base + d + 0];
      query[d + 1] = query_desc[base + d + 1];
      query[d + 2] = query_desc[base + d + 2];
      query[d + 3] = query_desc[base + d + 3];
    }
  }

  for (int base = 0; base < train_count; base += TILE) {
    const int load_index = base + lane;
    if (load_index < train_count) {
      const int src = load_index * DESCRIPTOR_SIZE;
      const int dst = lane * DESCRIPTOR_SIZE;
      for (int d = 0; d < DESCRIPTOR_SIZE; d += 4) {
        train_tile[dst + d + 0] = train_desc[src + d + 0];
        train_tile[dst + d + 1] = train_desc[src + d + 1];
        train_tile[dst + d + 2] = train_desc[src + d + 2];
        train_tile[dst + d + 3] = train_desc[src + d + 3];
      }
    }
    barrier(CLK_LOCAL_MEM_FENCE);

    const int tile_count = min(TILE, train_count - base);
    if (query_index < query_count) {
      for (int candidate = 0; candidate < tile_count; ++candidate) {
        float dot = 0.0f;
        const int cand_base = candidate * DESCRIPTOR_SIZE;
        for (int d = 0; d < DESCRIPTOR_SIZE; d += 4) {
          float4 q = (float4)(query[d + 0], query[d + 1], query[d + 2],
                              query[d + 3]);
          float4 t = (float4)(train_tile[cand_base + d + 0],
                              train_tile[cand_base + d + 1],
                              train_tile[cand_base + d + 2],
                              train_tile[cand_base + d + 3]);
          float4 p = q * t;
          dot += p.x + p.y + p.z + p.w;
        }
        if (dot > best) {
          second = best;
          best = dot;
          best_index = base + candidate;
        } else if (dot > second) {
          second = dot;
        }
      }
    }
    barrier(CLK_LOCAL_MEM_FENCE);
  }

  if (query_index < query_count) {
    match_index[query_index] = best_index;
    best_score[query_index] = best;
    ambiguity[query_index] =
        (second >= 0.0f) ? (second / (best + 1.0e-6f)) : 1.0f;
    match_x[query_index] =
        (best_index >= 0) ? train_xy[best_index * 2 + 0] : 0.0f;
    match_y[query_index] =
        (best_index >= 0) ? train_xy[best_index * 2 + 1] : 0.0f;
  }
}
)CLC";
