// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
#define CL_TARGET_OPENCL_VERSION 120

#include "opencl_extrema.hpp"
#include "opencl_match_kernel.hpp"

#include <CL/cl.h>
#include <CL/cl_ext.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

namespace sift_extractor::detail {
namespace {

constexpr size_t candidate_block_size = 64;

struct LocationHash {
  size_t operator()(const std::array<float, 3> &location) const noexcept {
    size_t result = 0;
    for (float coordinate : location)
      result ^= std::hash<float>{}(coordinate) + 0x9e3779b9U + (result << 6) + (result >> 2);
    return result;
  }
};

constexpr const char *kernel_source = R"CLC(
#ifdef cl_intel_subgroups
#pragma OPENCL EXTENSION cl_intel_subgroups : enable
#endif
#ifdef cl_intel_required_subgroup_size
#pragma OPENCL EXTENSION cl_intel_required_subgroup_size : enable
#endif

inline uchar dog_extremum(__global const float *dog, const int x,
              const int y, const int scale, const int width,
              const int height, const float threshold) {
  const int plane_size = width * height;
  const int center_index = scale * plane_size + y * width + x;
  const float value = dog[center_index];

  if (fabs(value) < threshold) {
    return (uchar)0;
  }

  const int is_max = value > 0.0f;
  for (int scale_offset = -1; scale_offset <= 1; ++scale_offset) {
    const int neighbor_scale = scale + scale_offset;
    const int scale_base = neighbor_scale * plane_size;
    for (int y_offset = -1; y_offset <= 1; ++y_offset) {
      const int row_base = scale_base + (y + y_offset) * width;
      for (int x_offset = -1; x_offset <= 1; ++x_offset) {
        if (scale_offset == 0 && y_offset == 0 && x_offset == 0)
          continue;
        const float neighbor = dog[row_base + x + x_offset];
        if ((is_max && value <= neighbor) || (!is_max && value >= neighbor)) {
          return (uchar)0;
        }
      }
    }
  }
  return (uchar)1;
}

__kernel void find_dog_extrema(__global const float *dog,
                               __global uchar *candidate_mask,
                               const int width, const int height,
                               const int scale_count,
                               const float threshold) {
  const int x = (int)get_global_id(0) + 1;
  const int y = (int)get_global_id(1) + 1;
  const int scale = (int)get_global_id(2) + 1;
  const int mask_index = ((scale - 1) * (height - 2) + y - 1) * (width - 2) + x - 1;
  candidate_mask[mask_index] = dog_extremum(dog, x, y, scale, width, height, threshold);
}

__kernel void find_and_count_dog_extrema(__global const float *dog,
                                         __global uchar *mask,
                                         __global uint *counts,
                                         const int width, const int height,
                                         const int mask_count,
                                         const float threshold) {
  __local uint count;
  if (get_local_id(0) == 0) count = 0;
  barrier(CLK_LOCAL_MEM_FENCE);
  if (get_global_id(0) < (size_t)mask_count) {
    const int index = (int)get_global_id(0);
    const int x = index % (width - 2) + 1;
    const int row = index / (width - 2);
    const int y = row % (height - 2) + 1;
    const int scale = row / (height - 2) + 1;
    const uchar candidate = dog_extremum(dog, x, y, scale, width, height, threshold);
    mask[index] = candidate;
    if (candidate) atomic_inc(&count);
  }
  barrier(CLK_LOCAL_MEM_FENCE);
  if (get_local_id(0) == 0) counts[get_group_id(0)] = count;
}

typedef struct {
  int x;
  int y;
  int scale;
  float response;
} ExtremaCandidateData;

__kernel void compact_dog_candidates(__global const float *dog,
                                      __global const uchar *mask,
                                      __global const uint *offsets,
                                      __global ExtremaCandidateData *candidates,
                                      const int width, const int height,
                                      const int mask_count,
                                      const int candidate_capacity) {
  const int block = (int)get_global_id(0);
  const int begin = block * SIFT_CANDIDATE_BLOCK_SIZE;
  uint destination = offsets[block];
  for (int offset = 0; offset < min(SIFT_CANDIDATE_BLOCK_SIZE, mask_count - begin); ++offset) {
    const int index = begin + offset;
    if (!mask[index]) continue;
    const int x = index % (width - 2) + 1;
    const int row = index / (width - 2);
    const int y = row % (height - 2) + 1;
    const int scale = row / (height - 2) + 1;
    ExtremaCandidateData candidate = {x, y, scale,
        dog[(scale * height + y) * width + x]};
    if (destination < (uint)candidate_capacity) candidates[destination] = candidate;
    ++destination;
  }
}

__kernel void scan_dog_counts(__global uint *offsets, const int block_count) {
  __local uint totals[256];
  const int lane = (int)get_local_id(0);
  const int span = (block_count + 255) / 256;
  const int begin = lane * span;
  const int end = min(begin + span, block_count);
  uint sum = 0;
  for (int block = begin; block < end; ++block) sum += offsets[block];
  totals[lane] = sum;
  barrier(CLK_LOCAL_MEM_FENCE);
  for (int stride = 1; stride < 256; stride *= 2) {
    const uint previous = lane >= stride ? totals[lane - stride] : 0;
    barrier(CLK_LOCAL_MEM_FENCE);
    totals[lane] += previous;
    barrier(CLK_LOCAL_MEM_FENCE);
  }
  uint prefix = lane > 0 ? totals[lane - 1] : 0;
  for (int block = begin; block < end; ++block) {
    const uint count = offsets[block];
    offsets[block] = prefix;
    prefix += count;
  }
  if (lane == 255) offsets[block_count] = totals[lane];
}

inline void refine_dog_candidate(__global const float *dog,
                                  const ExtremaCandidateData candidate,
                                  __global float *refined, const int index,
                                  const int width, const int height,
                                  const int scale_count,
                                  const float contrast_threshold,
                                  const float edge_limit) {
  int x = candidate.x;
  int y = candidate.y;
  int scale = candidate.scale;
  const int output = index * 6;
  const int plane_size = width * height;
  for (int iteration = 0; iteration < 5; ++iteration) {
    if (x < 1 || x >= width - 1 || y < 1 || y >= height - 1 ||
        scale < 1 || scale >= scale_count - 1) {
      refined[output + 5] = 0.0f;
      return;
    }

    const int center = scale * plane_size + y * width + x;
    const float value = dog[center];
    const float gx = 0.5f * (dog[center + 1] - dog[center - 1]);
    const float gy = 0.5f * (dog[center + width] - dog[center - width]);
    const float gs = 0.5f * (dog[center + plane_size] - dog[center - plane_size]);
    const float dxx = dog[center + 1] + dog[center - 1] - 2.0f * value;
    const float dyy = dog[center + width] + dog[center - width] - 2.0f * value;
    const float dss = dog[center + plane_size] + dog[center - plane_size] - 2.0f * value;
    const float dxy = 0.25f * (dog[center + width + 1] - dog[center + width - 1] -
                               dog[center - width + 1] + dog[center - width - 1]);
    const float dxs = 0.25f * (dog[center + plane_size + 1] -
                               dog[center + plane_size - 1] -
                               dog[center - plane_size + 1] +
                               dog[center - plane_size - 1]);
    const float dys = 0.25f * (dog[center + plane_size + width] -
                               dog[center + plane_size - width] -
                               dog[center - plane_size + width] +
                               dog[center - plane_size - width]);

    const float a11 = dyy * dss - dys * dys;
    const float a12 = dxs * dys - dxy * dss;
    const float a13 = dxy * dys - dyy * dxs;
    const float a22 = dxx * dss - dxs * dxs;
    const float a23 = dxy * dxs - dxx * dys;
    const float a33 = dxx * dyy - dxy * dxy;
    const float determinant = dxx * a11 + dxy * a12 + dxs * a13;
    if (!isfinite(determinant) || fabs(determinant) < 1e-10f) {
      refined[output + 5] = 0.0f;
      return;
    }

    const float offset_x = -(a11 * gx + a12 * gy + a13 * gs) / determinant;
    const float offset_y = -(a12 * gx + a22 * gy + a23 * gs) / determinant;
    const float offset_s = -(a13 * gx + a23 * gy + a33 * gs) / determinant;
    if (!isfinite(offset_x) || !isfinite(offset_y) || !isfinite(offset_s)) {
      refined[output + 5] = 0.0f;
      return;
    }
    if (fabs(offset_x) > 0.5f || fabs(offset_y) > 0.5f || fabs(offset_s) > 0.5f) {
      refined[output + 5] = 0.0f;
      x += (offset_x > 0.5f) - (offset_x < -0.5f);
      y += (offset_y > 0.5f) - (offset_y < -0.5f);
      scale += (offset_s > 0.5f) - (offset_s < -0.5f);
      continue;
    }

    const float interpolated_response =
        value + 0.5f * (gx * offset_x + gy * offset_y + gs * offset_s);
    const float spatial_determinant = dxx * dyy - dxy * dxy;
    const float trace = dxx + dyy;
    if (!isfinite(interpolated_response) ||
        fabs(interpolated_response) < contrast_threshold ||
        spatial_determinant <= 0.0f ||
        trace * trace / spatial_determinant >= edge_limit) {
      refined[output + 5] = 0.0f;
      return;
    }

    refined[output + 0] = (float)x + offset_x;
    refined[output + 1] = (float)y + offset_y;
    refined[output + 2] = (float)scale + offset_s;
    refined[output + 3] = interpolated_response;
    refined[output + 4] = trace * trace / spatial_determinant;
    refined[output + 5] = 1.0f;
    return;
  }
}

__kernel void refine_dog_extrema(__global const float *dog,
                                 __global const ExtremaCandidateData *candidates,
                                 __global float *refined,
                                 const int width, const int height,
                                 const int scale_count, const int candidate_count,
                                 const float contrast_threshold, const float edge_limit) {
  const int index = (int)get_global_id(0);
  if (index >= candidate_count) return;
  refine_dog_candidate(dog, candidates[index], refined, index, width, height,
    scale_count, contrast_threshold, edge_limit);
}

__kernel void refine_compacted_candidates(__global const float *dog,
                                          __global const uchar *mask,
                                          __global float *refined,
                                          const int width, const int height,
                                          const int scale_count, const int capacity,
                                          const float contrast_threshold, const float edge_limit,
                                          __global const uint *offsets, const int mask_count) {
  const int begin = (int)get_global_id(0) * SIFT_CANDIDATE_BLOCK_SIZE;
  uint destination = offsets[get_global_id(0)];
  for (int position = 0; position < min(SIFT_CANDIDATE_BLOCK_SIZE, mask_count - begin); ++position) {
    const int index = begin + position;
    if (!mask[index]) continue;
    if (destination < (uint)capacity) {
      const int x = index % (width - 2) + 1;
      const int row = index / (width - 2);
      const int y = row % (height - 2) + 1;
      const int scale = row / (height - 2) + 1;
      const ExtremaCandidateData candidate = {x, y, scale, dog[(scale * height + y) * width + x]};
      refine_dog_candidate(dog, candidate, refined, (int)destination, width, height,
        scale_count, contrast_threshold, edge_limit);
    }
    ++destination;
  }
}

__kernel void sift_gradients(__global const float *image,
                             __global float *magnitude,
                             __global float *orientation,
                             const int width, const int height,
                             const int image_offset) {
  const int x = (int)get_global_id(0);
  const int y = (int)get_global_id(1);
  if (x >= width || y >= height)
    return;
  const int index = y * width + x;
  magnitude += image_offset;
  orientation += image_offset;
  if (x == 0 || y == 0 || x >= width - 1 || y >= height - 1) {
    magnitude[index] = 0.0f;
    orientation[index] = 0.0f;
    return;
  }
  const float gx = image[index + 1] - image[index - 1];
  const float gy = image[index + width] - image[index - width];
  magnitude[index] = hypot(gx, gy);
  orientation[index] = atan2(gy, gx);
}

__kernel void sift_packed_gradients(__global const float *image,
                                    __global float *magnitude,
                                    __global float *orientation,
                                    __constant const int *layout,
                                    const int level_count,
                                    const int pixel_count) {
  if (get_global_id(0) >= (size_t)pixel_count) return;
  const int index = (int)get_global_id(0);
  const int block_start = (int)(get_group_id(0) * get_local_size(0));
  int lower_level = 0;
  int upper_level = level_count;
  while (lower_level + 1 < upper_level) {
    const int middle = lower_level + (upper_level - lower_level) / 2;
    if (block_start >= layout[middle * 4 + 3]) lower_level = middle;
    else upper_level = middle;
  }
  const int width = layout[lower_level * 4];
  const int height = layout[lower_level * 4 + 1];
  const int source_offset = layout[lower_level * 4 + 2];
  const int local_index = index - layout[lower_level * 4 + 3];
  if (local_index >= width * height) return;
  const int pixel_x = local_index % width;
  const int pixel_y = local_index / width;
  if (pixel_x == 0 || pixel_y == 0 || pixel_x >= width - 1 || pixel_y >= height - 1) {
    magnitude[index] = 0.0f;
    orientation[index] = 0.0f;
    return;
  }
  const int source_index = source_offset + local_index;
  const float gradient_x = image[source_index + 1] - image[source_index - 1];
  const float gradient_y = image[source_index + width] - image[source_index - width];
  magnitude[index] = hypot(gradient_x, gradient_y);
  orientation[index] = atan2(gradient_y, gradient_x);
}

#if defined(cl_intel_subgroups) && defined(cl_intel_required_subgroup_size) && defined(SIFT_ORIENTATION_SUBGROUP32)
__attribute__((intel_reqd_sub_group_size(32)))
#endif
__kernel void sift_orientations(__global const float *magnitude,
                                __global const float *gradient_orientation,
                                __global const float *points,
                                __global float *output,
                                const int fixed_width, const int fixed_height,
                                __global const int *layout,
                                __global uint *counts) {
  #if SIFT_DESCRIPTOR_LANES > 1
  const int index = (int)get_group_id(0);
  const int lane = (int)get_local_id(0);
  __local float hist[36];
  #else
  const int index = (int)get_global_id(0);
  const int lane = 0;
  float hist[36];
  #endif
  const int width = fixed_width > 0 ? fixed_width : layout[index * 3];
  const int height = fixed_width > 0 ? fixed_height : layout[index * 3 + 1];
  const int image_offset = fixed_width > 0 ? 0 : layout[index * 3 + 2];
  magnitude += image_offset;
  gradient_orientation += image_offset;
  const float cx = points[index * 4];
  const float cy = points[index * 4 + 1];
  const float sigma = 1.5f * points[index * 4 + 2];
  const int radius = min((int)ceil(3.0f * sigma), max(width, height));
  const int center_x = (int)floor(cx + 0.5f);
  const int center_y = (int)floor(cy + 0.5f);
  float smoothed[36];
  #if SIFT_DESCRIPTOR_LANES > 1
  float sum = 0.0f;
  #ifdef cl_intel_subgroups
  const int subgroup_lane = (int)get_sub_group_local_id();
  const int subgroup_size = (int)get_sub_group_size();
  const int begin_x = max(1, center_x - radius);
  const int end_x = min(width - 2, center_x + radius);
  for (int sample_y = max(1, center_y - radius);
       sample_y <= min(height - 2, center_y + radius); ++sample_y) {
    for (int begin = begin_x; begin <= end_x; begin += subgroup_size) {
      const int sample_x = begin + subgroup_lane;
      int lower_bin = 0;
      float sample_fraction = 0.0f;
      float sample_magnitude = 0.0f;
      if (sample_x <= end_x) {
        float sample_angle = gradient_orientation[sample_y * width + sample_x] *
          (18.0f / 3.14159265358979323846f);
        if (sample_angle < 0.0f) sample_angle += 36.0f;
        lower_bin = (int)floor(sample_angle);
        sample_fraction = sample_angle - (float)lower_bin;
        const float rx = (float)sample_x - cx;
        const float ry = (float)sample_y - cy;
        const float weight = exp(-(rx * rx + ry * ry) / (2.0f * sigma * sigma));
        sample_magnitude = magnitude[sample_y * width + sample_x] * weight;
      }
      for (int source_lane = 0; source_lane < min(subgroup_size, end_x - begin + 1); ++source_lane) {
        const int lower = intel_sub_group_shuffle(lower_bin, (uint)source_lane);
        const float fraction = intel_sub_group_shuffle(sample_fraction, (uint)source_lane);
        const float weighted_magnitude = intel_sub_group_shuffle(sample_magnitude, (uint)source_lane);
        if (lower % 36 == lane || (lower + 1) % 36 == lane)
          sum += weighted_magnitude * (lower % 36 == lane ? 1.0f - fraction : fraction);
      }
    }
  }
  #else
  if (lane < 36) {
    for (int dy = max(-radius, 1 - center_y);
         dy <= min(radius, height - 2 - center_y); ++dy) {
      for (int dx = max(-radius, 1 - center_x);
           dx <= min(radius, width - 2 - center_x); ++dx) {
        const int x = center_x + dx;
        const int y = center_y + dy;
        float angle = gradient_orientation[y * width + x] *
          (18.0f / 3.14159265358979323846f);
        if (angle < 0.0f) angle += 36.0f;
        const int lower = (int)floor(angle);
        if (lower % 36 != lane && (lower + 1) % 36 != lane) continue;
        const float fraction = angle - (float)lower;
        const float rx = (float)x - cx;
        const float ry = (float)y - cy;
        const float weight = exp(-(rx * rx + ry * ry) / (2.0f * sigma * sigma));
        const float weighted_magnitude = magnitude[y * width + x] * weight;
        sum += weighted_magnitude * (lower % 36 == lane ? 1.0f - fraction : fraction);
      }
    }
  }
  #endif
  if (lane < 36) hist[lane] = sum;
  barrier(CLK_LOCAL_MEM_FENCE);
  #else
  for (int bin = 0; bin < 36; ++bin)
    hist[bin] = 0.0f;
  for (int dy = max(-radius, 1 - center_y);
       dy <= min(radius, height - 2 - center_y); ++dy) {
    for (int dx = max(-radius, 1 - center_x);
         dx <= min(radius, width - 2 - center_x); ++dx) {
      const int x = center_x + dx;
      const int y = center_y + dy;
      const float rx = (float)x - cx;
      const float ry = (float)y - cy;
      const float weight = exp(-(rx * rx + ry * ry) / (2.0f * sigma * sigma));
      float angle = gradient_orientation[y * width + x] *
            (18.0f / 3.14159265358979323846f);
      if (angle < 0.0f) angle += 36.0f;
      const int lower = (int)floor(angle);
      const float fraction = angle - (float)lower;
      const float weighted_magnitude = magnitude[y * width + x] * weight;
      hist[lower % 36] += weighted_magnitude * (1.0f - fraction);
      hist[(lower + 1) % 36] += weighted_magnitude * fraction;
    }
  }
  #endif
  if (lane == 0) {
  for (int pass = 0; pass < 6; ++pass) {
    for (int bin = 0; bin < 36; ++bin)
      smoothed[bin] = (hist[(bin + 35) % 36] + hist[bin] +
                       hist[(bin + 1) % 36]) / 3.0f;
    for (int bin = 0; bin < 36; ++bin) hist[bin] = smoothed[bin];
  }
  float peak = 0.0f;
  for (int bin = 0; bin < 36; ++bin) peak = fmax(peak, hist[bin]);
  uint orientation_count = 0;
  for (int bin = 0; bin < 36; ++bin) {
    output[index * 36 + bin] = -1.0f;
    const float left = hist[(bin + 35) % 36];
    const float right = hist[(bin + 1) % 36];
    if (peak > 0.0f && hist[bin] >= 0.8f * peak &&
        hist[bin] > left && hist[bin] >= right) {
      const float denominator = left - 2.0f * hist[bin] + right;
      const float offset = fabs(denominator) > 1e-20f ?
                            0.5f * (left - right) / denominator : 0.0f;
      output[index * 36 + bin] = fmod(((float)bin + offset + 36.0f) * 10.0f, 360.0f);
      ++orientation_count;
    }
  }
  if (counts) counts[index] = orientation_count;
  }
}

__kernel void sift_descriptors(__global const float *magnitude,
                               __global const float *gradient_orientation,
                               __global const float *points,
                               __global float *output,
                               const int fixed_width, const int fixed_height,
                               __global const int *layout,
                               __global const uint *counts, const int count_offset) {
  const int lane = (int)get_local_id(0);
  const int index = (int)get_group_id(0);
  if (counts && (uint)index >= counts[count_offset]) return;
  const int width = fixed_width > 0 ? fixed_width : layout[index * 3];
  const int height = fixed_width > 0 ? fixed_height : layout[index * 3 + 1];
  const int image_offset = fixed_width > 0 ? 0 : layout[index * 3 + 2];
  magnitude += image_offset;
  gradient_orientation += image_offset;
  const float cx = points[index * 4];
  const float cy = points[index * 4 + 1];
  const float bin_width = 3.0f * points[index * 4 + 2];
  const float angle = points[index * 4 + 3] * (3.14159265358979323846f / 180.0f);
  const float cosine = cos(angle);
  const float sine = sin(angle);
  const int radius = min((int)ceil(3.53553390593f * bin_width), max(width, height));
  const int center_x = (int)floor(cx + 0.5f);
  const int center_y = (int)floor(cy + 0.5f);
  #if SIFT_DESCRIPTOR_LANES == 32
  __local float hist[128];
  const float inverse_bin_width = 1.0f / bin_width;
  const int cell = lane / 2;
  const int first_bin = (lane % 2) * 4;
  const int row_bin = cell / 4;
  const int column_bin = cell % 4;
  const float column_center = (float)column_bin - 1.5f;
  const float row_center = (float)row_bin - 1.5f;
  const float sample_x = cx + bin_width * (cosine * column_center - sine * row_center);
  const float sample_y = cy + bin_width * (sine * column_center + cosine * row_center);
  const float extent = bin_width * (fabs(cosine) + fabs(sine));
  const int begin_x = max(max(1, center_x - radius),
    convert_int_sat_rtn(sample_x - extent - 1.0f));
  const int end_x = min(min(width - 2, center_x + radius),
    convert_int_sat_rtp(sample_x + extent + 1.0f));
  const int begin_y = max(max(1, center_y - radius),
    convert_int_sat_rtn(sample_y - extent - 1.0f));
  const int end_y = min(min(height - 2, center_y + radius),
    convert_int_sat_rtp(sample_y + extent + 1.0f));
  float sums[4] = {0.0f};
  for (int sample_y_index = begin_y; sample_y_index <= end_y; ++sample_y_index) {
    for (int sample_x_index = begin_x; sample_x_index <= end_x; ++sample_x_index) {
      const float rx = (float)sample_x_index - cx;
      const float ry = (float)sample_y_index - cy;
      const float column = (cosine * rx + sine * ry) * inverse_bin_width;
      const float row = (-sine * rx + cosine * ry) * inverse_bin_width;
      const float rb = row + 1.5f;
      const float cb = column + 1.5f;
      if (rb <= -1.0f || rb >= 4.0f || cb <= -1.0f || cb >= 4.0f) continue;
      const int ri = (int)floor(rb);
      const int ci = (int)floor(cb);
      if (row_bin < ri || row_bin > ri + 1 || column_bin < ci || column_bin > ci + 1) continue;
      const int sample = sample_y_index * width + sample_x_index;
      float ob = (gradient_orientation[sample] - angle) * (4.0f / 3.14159265358979323846f);
      ob += 16.0f;
      ob -= ob >= 16.0f ? 16.0f : (ob >= 8.0f ? 8.0f : 0.0f);
      const int oi = (int)floor(ob);
      const float rf = rb - (float)ri;
      const float cf = cb - (float)ci;
      const float of = ob - (float)oi;
      const float weighted_magnitude = magnitude[sample] * exp(-(row * row + column * column) / 8.0f);
      const float spatial_weight = weighted_magnitude * (row_bin == ri ? 1.0f - rf : rf) *
        (column_bin == ci ? 1.0f - cf : cf);
      const int lower = oi % 8 - first_bin;
      const int upper = (oi + 1) % 8 - first_bin;
      if (lower >= 0 && lower < 4) sums[lower] += spatial_weight * (1.0f - of);
      if (upper >= 0 && upper < 4) sums[upper] += spatial_weight * of;
    }
  }
  for (int bin = 0; bin < 4; ++bin) hist[cell * 8 + first_bin + bin] = sums[bin];
  barrier(CLK_LOCAL_MEM_FENCE);
  #else
  float hist[128];
  for (int bin = 0; bin < 128; ++bin) hist[bin] = 0.0f;
  for (int dy = max(-radius, 1 - center_y);
       dy <= min(radius, height - 2 - center_y); ++dy) {
        for (int dx = max(-radius, 1 - center_x) + lane;
          dx <= min(radius, width - 2 - center_x); dx += SIFT_DESCRIPTOR_LANES) {
      const int x = center_x + dx;
      const int y = center_y + dy;
      const float rx = (float)x - cx;
      const float ry = (float)y - cy;
      const float column = (cosine * rx + sine * ry) / bin_width;
      const float row = (-sine * rx + cosine * ry) / bin_width;
      const float rb = row + 1.5f;
      const float cb = column + 1.5f;
      if (rb <= -1.0f || rb >= 4.0f || cb <= -1.0f || cb >= 4.0f) continue;
        const int sample = y * width + x;
        float ob = (gradient_orientation[sample] - angle) *
             (4.0f / 3.14159265358979323846f);
      ob = fmod(ob + 16.0f, 8.0f);
        const float weighted_magnitude = magnitude[sample] *
          exp(-(row * row + column * column) / 8.0f);
      const int ri = (int)floor(rb);
      const int ci = (int)floor(cb);
      const int oi = (int)floor(ob);
      const float rf = rb - (float)ri;
      const float cf = cb - (float)ci;
      const float of = ob - (float)oi;
      for (int rr = 0; rr <= 1; ++rr) {
        const int row_bin = ri + rr;
        if (row_bin < 0 || row_bin >= 4) continue;
        for (int cc = 0; cc <= 1; ++cc) {
          const int column_bin = ci + cc;
          if (column_bin < 0 || column_bin >= 4) continue;
          for (int oo = 0; oo <= 1; ++oo)
            hist[(row_bin * 4 + column_bin) * 8 + (oi + oo) % 8] +=
              weighted_magnitude * (rr ? rf : 1.0f - rf) *
                (cc ? cf : 1.0f - cf) * (oo ? of : 1.0f - of);
        }
      }
    }
  }
  #endif
  if (lane == 0) {
  float norm = 0.0f;
  for (int bin = 0; bin < 128; ++bin) norm += hist[bin] * hist[bin];
  const float inverse_norm = norm > 0.0f ? rsqrt(norm) : 0.0f;
  norm = 0.0f;
  for (int bin = 0; bin < 128; ++bin) {
    hist[bin] = fmin(hist[bin] * inverse_norm, 0.2f);
    norm += hist[bin] * hist[bin];
  }
  const float inverse_clipped_norm = norm > 0.0f ? rsqrt(norm) : 0.0f;
  for (int bin = 0; bin < 128; ++bin)
    output[index * 128 + bin] = hist[bin] * inverse_clipped_norm;
  }
}

typedef struct {
  uint point;
  float angle;
} OrientationSourceData;

uint location_hash(__global const float *point) {
  uint result = 2166136261U;
  for (int coordinate = 0; coordinate < 3; ++coordinate)
    result = (result ^ as_uint(point[coordinate] == 0.0f ? 0.0f : point[coordinate])) * 16777619U;
  result = (result ^ (result >> 16)) * 0x7feb352dU;
  result = (result ^ (result >> 15)) * 0x846ca68bU;
  return result ^ (result >> 16);
}

int same_location(__global const float *first, __global const float *second) {
  return first[0] == second[0] && first[1] == second[1] && first[2] == second[2];
}

__kernel void claim_locations(__global const float *refined,
                               volatile __global uint *owners,
                               const uint candidate_count, const uint table_mask) {
  const uint index = (uint)get_global_id(0);
  if (index >= candidate_count || refined[index * 6 + 5] == 0.0f) return;
  __global const float *point = refined + index * 6;
  uint slot = location_hash(point) & table_mask;
  for (;;) {
    const uint owner = atomic_cmpxchg(owners + slot, 0xffffffffU, index);
    if (owner == 0xffffffffU) return;
    if (same_location(point, refined + owner * 6)) {
      atomic_min(owners + slot, index);
      return;
    }
    slot = (slot + 1U) & table_mask;
  }
}

__kernel void mark_unique_locations(__global const float *refined,
                                     __global const uint *owners,
                                     __global uint *keep,
                                     const uint candidate_count, const uint table_mask) {
  const uint index = (uint)get_global_id(0);
  if (index >= candidate_count) return;
  if (refined[index * 6 + 5] == 0.0f) {
    keep[index] = 0;
    return;
  }
  __global const float *point = refined + index * 6;
  uint slot = location_hash(point) & table_mask;
  for (;;) {
    const uint owner = owners[slot];
    if (same_location(point, refined + owner * 6)) {
      keep[index] = owner == index ? 1U : 0U;
      return;
    }
    slot = (slot + 1U) & table_mask;
  }
}

__kernel void scatter_feature_records(__global const float *refined,
                                       __global const uint *keep_offsets,
                                       __global const uint *keep,
                                       __global float *records,
                                       __global int *groups,
                                       const uint candidate_count,
                                       const int intervals,
                                       const int octave,
                                       const float base_sigma) {
  const uint index = (uint)get_global_id(0);
  if (index >= candidate_count || keep[index] == 0U) return;
  const uint destination = keep_offsets[index];
  __global const float *point = refined + index * 6;
  const float image_factor = ldexp(1.0f, octave);
  const float octave_sigma = base_sigma * exp2((point[2] + 0.5f) / (float)intervals);
  const int level = clamp((int)round(point[2]), 0, intervals + 2);
  records[destination * 8 + 0] = point[0];
  records[destination * 8 + 1] = point[1];
  records[destination * 8 + 2] = point[2];
  records[destination * 8 + 3] = point[3];
  records[destination * 8 + 4] = point[4];
  records[destination * 8 + 5] = octave_sigma;
  records[destination * 8 + 6] = point[0] * image_factor;
  records[destination * 8 + 7] = point[1] * image_factor;
  groups[destination] = octave * (intervals + 3) + level;
}

__kernel void gather_dispatch_features(__global const float *unique_records,
                                        __global const int *unique_groups,
                                        __global const int *source_indices,
                                        __global const float *host_sigmas,
                                        __global const int *level_meta,
                                        __global float *points,
                                        __global int *layout,
                                        const int count,
                                        const int level_count) {
  const int index = (int)get_global_id(0);
  if (index >= count) return;
  const int source = source_indices[index];
  __global const float *record = unique_records + source * 8;
  points[index * 4 + 0] = record[0];
  points[index * 4 + 1] = record[1];
  // Host std::exp2 sigma: device exp2 can differ by 1 ULP.
  points[index * 4 + 2] = host_sigmas[index];
  points[index * 4 + 3] = 0.0f;
  const int group = unique_groups[source];
  if (group < 0 || group >= level_count) {
    layout[index * 3 + 0] = 0;
    layout[index * 3 + 1] = 0;
    layout[index * 3 + 2] = 0;
    return;
  }
  layout[index * 3 + 0] = level_meta[group * 3 + 0];
  layout[index * 3 + 1] = level_meta[group * 3 + 1];
  layout[index * 3 + 2] = level_meta[group * 3 + 2];
}

// After stable_group_reorder, source index == dispatch order index.
__kernel void gather_identity_features(__global const float *unique_records,
                                       __global const int *unique_groups,
                                       __global const float *host_sigmas,
                                       __global const int *level_meta,
                                       __global float *points,
                                       __global int *layout,
                                       const int count,
                                       const int level_count) {
  const int index = (int)get_global_id(0);
  if (index >= count) return;
  __global const float *record = unique_records + index * 8;
  points[index * 4 + 0] = record[0];
  points[index * 4 + 1] = record[1];
  points[index * 4 + 2] = host_sigmas[index];
  points[index * 4 + 3] = 0.0f;
  const int group = unique_groups[index];
  if (group < 0 || group >= level_count) {
    layout[index * 3 + 0] = 0;
    layout[index * 3 + 1] = 0;
    layout[index * 3 + 2] = 0;
    return;
  }
  layout[index * 3 + 0] = level_meta[group * 3 + 0];
  layout[index * 3 + 1] = level_meta[group * 3 + 1];
  layout[index * 3 + 2] = level_meta[group * 3 + 2];
}

// Single-WI partial selection matching host stable_sort by |response| desc + resize.
__kernel void stable_response_cap(__global float *records,
                                  __global int *groups,
                                  const int count,
                                  const int max_features) {
  if (get_global_id(0) != 0 || max_features <= 0 || count <= max_features) return;
  for (int i = 0; i < max_features; ++i) {
    int best = i;
    float best_abs = fabs(records[i * 8 + 3]);
    for (int j = i + 1; j < count; ++j) {
      const float candidate_abs = fabs(records[j * 8 + 3]);
      if (candidate_abs > best_abs) {
        best = j;
        best_abs = candidate_abs;
      }
    }
    if (best == i) continue;
    for (int k = 0; k < 8; ++k) {
      const float tmp = records[i * 8 + k];
      records[i * 8 + k] = records[best * 8 + k];
      records[best * 8 + k] = tmp;
    }
    const int group_tmp = groups[i];
    groups[i] = groups[best];
    groups[best] = group_tmp;
  }
}

// Stable group order: preserves concat index order within each group (host bucket order).
__kernel void stable_group_reorder(__global const float *in_records,
                                   __global const int *in_groups,
                                   __global float *out_records,
                                   __global int *out_groups,
                                   __global uint *group_counts,
                                   __global uint *group_cursors,
                                   const int count,
                                   const int level_count) {
  if (get_global_id(0) != 0) return;
  for (int group = 0; group < level_count; ++group) group_counts[group] = 0;
  for (int index = 0; index < count; ++index) {
    const int group = in_groups[index];
    if (group >= 0 && group < level_count) group_counts[group]++;
  }
  uint running = 0;
  for (int group = 0; group < level_count; ++group) {
    group_cursors[group] = running;
    running += group_counts[group];
  }
  for (int index = 0; index < count; ++index) {
    const int group = in_groups[index];
    if (group < 0 || group >= level_count) continue;
    const uint destination = group_cursors[group]++;
    for (int k = 0; k < 8; ++k)
      out_records[destination * 8 + k] = in_records[index * 8 + k];
    out_groups[destination] = group;
  }
}

__kernel void pack_orientations(__global const float *points,
                                 __global const float *angles,
                                 __global const int *layout,
                                 __global const uint *offsets,
                                 __global float *packed,
                                 __global int *packed_layout,
                                 const int point_count, const int capacity,
                                 __global OrientationSourceData *sources) {
  const int index = (int)get_global_id(0);
  if (index >= point_count) return;
  uint destination = offsets[index];
  for (int bin = 0; bin < 36; ++bin) {
    const float angle = angles[index * 36 + bin];
    if (!(angle >= 0.0f)) continue;
    if (destination < (uint)capacity) {
      for (int coordinate = 0; coordinate < 3; ++coordinate) {
        packed[destination * 4 + coordinate] = points[index * 4 + coordinate];
        packed_layout[destination * 3 + coordinate] = layout[index * 3 + coordinate];
      }
      packed[destination * 4 + 3] = angle;
      sources[destination].point = (uint)index;
      sources[destination].angle = angle;
    }
    ++destination;
  }
}
)CLC";

void check_opencl(cl_int status, const char *operation) {
  if (status != CL_SUCCESS) {
    throw std::runtime_error(std::string(operation) + " failed with OpenCL status " +
                             std::to_string(status));
  }
}

cl_device_id select_intel_gpu() {
  cl_uint platform_count = 0;
  const cl_int platform_status =
      clGetPlatformIDs(0, nullptr, &platform_count);
  if (platform_status == CL_PLATFORM_NOT_FOUND_KHR || platform_count == 0)
    throw std::runtime_error("No OpenCL platforms are available");
  check_opencl(platform_status, "clGetPlatformIDs(count)");
  std::vector<cl_platform_id> platforms(platform_count);
  check_opencl(clGetPlatformIDs(platform_count, platforms.data(), nullptr),
               "clGetPlatformIDs(list)");

  for (cl_platform_id platform : platforms) {
    size_t vendor_size = 0;
    if (clGetPlatformInfo(platform, CL_PLATFORM_VENDOR, 0, nullptr,
                          &vendor_size) != CL_SUCCESS)
      continue;
    std::vector<char> vendor(vendor_size);
    if (clGetPlatformInfo(platform, CL_PLATFORM_VENDOR, vendor.size(),
                          vendor.data(), nullptr) != CL_SUCCESS)
      continue;
    if (std::string(vendor.data()).find("Intel") == std::string::npos)
      continue;

    cl_uint device_count = 0;
    const cl_int device_status = clGetDeviceIDs(
        platform, CL_DEVICE_TYPE_GPU, 0, nullptr, &device_count);
    if (device_status == CL_DEVICE_NOT_FOUND || device_count == 0)
      continue;
    check_opencl(device_status, "clGetDeviceIDs(count)");
    std::vector<cl_device_id> devices(device_count);
    check_opencl(clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, device_count,
                                devices.data(), nullptr),
                 "clGetDeviceIDs(list)");
    return devices.front();
  }

  throw std::runtime_error("No Intel OpenCL GPU is available");
}

} // namespace

struct OpenCLDoGExtrema::Impl {
  struct OrientationSource {
    cl_uint point;
    cl_float angle;
  };
  static_assert(sizeof(OrientationSource) == sizeof(cl_uint) + sizeof(cl_float));
  struct Buffer {
    cl_mem memory = nullptr;
    size_t capacity = 0;
  };
  struct FeatureScratch {
    Buffer magnitude, orientation, points, output, layout;
    Buffer gradient_layout;
    Buffer counts, descriptor_points, descriptor_layout, descriptors, orientation_sources;
    Buffer unique_records, unique_groups, unique_records_alt, unique_groups_alt;
    Buffer group_counts, group_cursors, source_indices, host_sigmas, level_meta;
    size_t descriptor_capacity = 0;
    size_t unique_record_count = 0;
    bool resident_orientation_points = false;
    bool identity_sources = false;
    cl_event event = nullptr;
    cl_event descriptor_event = nullptr;
    cl_event gradient_event = nullptr;
    ~FeatureScratch() {
      for (auto *buffer : {&magnitude, &orientation, &points, &output, &layout, &gradient_layout,
               &counts, &descriptor_points, &descriptor_layout, &descriptors, &orientation_sources,
               &unique_records, &unique_groups, &unique_records_alt, &unique_groups_alt,
               &group_counts, &group_cursors, &source_indices, &host_sigmas, &level_meta})
        if (buffer->memory) clReleaseMemObject(buffer->memory);
      if (event) clReleaseEvent(event);
      if (descriptor_event) clReleaseEvent(descriptor_event);
      if (gradient_event) clReleaseEvent(gradient_event);
    }
  };
  std::vector<std::unique_ptr<FeatureScratch>> feature_scratch;
  struct DetectionScratch {
    Buffer volume, mask, offsets, refined, owners, keep, keep_offsets, records, groups;
    std::vector<cl_uint> host_offsets;
    std::vector<float> output;
    std::vector<float> unique_records;
    std::vector<int> unique_groups;
    cl_event events[4]{};
    cl_event count_event = nullptr;
    cl_event refine_event = nullptr;
    cl_event scatter_event = nullptr;
    cl_uint candidate_count = 0;
    cl_uint unique_count = 0;
    size_t candidate_capacity = 8;
    ~DetectionScratch() {
      for (auto *buffer : {&volume, &mask, &offsets, &refined, &owners, &keep, &keep_offsets,
               &records, &groups})
        if (buffer->memory) clReleaseMemObject(buffer->memory);
      for (auto event : events)
        if (event) clReleaseEvent(event);
      if (count_event) clReleaseEvent(count_event);
      if (refine_event) clReleaseEvent(refine_event);
      if (scatter_event) clReleaseEvent(scatter_event);
    }
  };
  std::vector<std::unique_ptr<DetectionScratch>> detection_scratch;
  struct IndexedKeypoint {
    ScaleSpaceKeypoint point;
    int source_index = -1;
  };
  struct FeatureDispatch {
    std::vector<ScaleSpaceKeypoint> ordered_points;
    std::vector<int> source_indices;
    std::vector<float> host_sigmas;
    std::vector<float> packed;
    std::vector<int> layout;
    std::vector<int> level_meta;
    std::vector<int> image_offsets;
    std::vector<char> occupied;
    size_t gradient_count = 0;
    size_t feature_groups = 0;
    bool identity_sources = false;
  };

  cl_context context = nullptr;
  cl_command_queue queue = nullptr;
  cl_program program = nullptr;
  cl_kernel kernel = nullptr;
  cl_kernel refine_kernel = nullptr;
  cl_kernel count_kernel = nullptr;
  cl_kernel compact_kernel = nullptr;
  cl_kernel scan_kernel = nullptr;
  cl_kernel bounded_refine_kernel = nullptr;
  cl_kernel claim_kernel = nullptr;
  cl_kernel mark_unique_kernel = nullptr;
  cl_kernel scatter_feature_kernel = nullptr;
  cl_kernel gather_dispatch_kernel = nullptr;
  cl_kernel gather_identity_kernel = nullptr;
  cl_kernel stable_response_cap_kernel = nullptr;
  cl_kernel stable_group_reorder_kernel = nullptr;
  cl_kernel match_kernel = nullptr;
  Buffer match_descriptors;
  Buffer match_xy;
  Buffer match_index;
  Buffer match_score;
  Buffer match_ambiguity;
  Buffer match_x;
  Buffer match_y;
  size_t resident_match_count = 0;
  bool resident_match_uses_extract_descriptors = false;
  Buffer dog_volume;
  Buffer candidate_mask;
  Buffer block_offsets;
  Buffer compact_candidates;
  Buffer refined_candidates;
  cl_kernel gradient_kernel = nullptr;
  cl_kernel packed_gradient_kernel = nullptr;
  cl_kernel orientation_kernel = nullptr;
  cl_kernel descriptor_kernel = nullptr;
  cl_kernel orientation_pack_kernel = nullptr;
  size_t descriptor_lanes = 32;
  size_t orientation_lanes = 64;
  bool profile_features = false;
  Buffer feature_image;
  Buffer feature_points;
  Buffer feature_output;
  Buffer gradient_magnitude;
  Buffer gradient_orientation;
  std::vector<float> cached_gradient_pixels;
  int cached_gradient_width = 0;
  int cached_gradient_height = 0;
  bool gradients_ready = false;
  cl_mem cached_gradient_device = nullptr;
  std::unique_ptr<OpenCLGaussianPyramid> pyramid;

  cl_mem ensure_buffer(Buffer &buffer, cl_mem_flags flags, size_t bytes) {
    if (buffer.memory && buffer.capacity >= bytes)
      return buffer.memory;
    cl_int status = CL_SUCCESS;
    cl_mem replacement = clCreateBuffer(context, flags, bytes, nullptr, &status);
    check_opencl(status, "clCreateBuffer(feature scratch)");
    if (buffer.memory)
      clReleaseMemObject(buffer.memory);
    buffer.memory = replacement;
    buffer.capacity = bytes;
    return buffer.memory;
  }

  static void apply_response_cap(std::vector<IndexedKeypoint> &keypoints, int max_features) {
    if (max_features <= 0 || keypoints.size() <= static_cast<size_t>(max_features)) return;
    std::stable_sort(keypoints.begin(), keypoints.end(), [](const auto &first, const auto &second) {
      return std::abs(first.point.local.response) > std::abs(second.point.local.response);
    });
    keypoints.resize(static_cast<size_t>(max_features));
  }

  FeatureDispatch build_feature_dispatch(std::vector<IndexedKeypoint> keypoints,
      const std::vector<GaussianLevel> &gaussian, int intervals, int max_features,
      bool already_capped_and_ordered = false) {
    if (!already_capped_and_ordered)
      apply_response_cap(keypoints, max_features);
    FeatureDispatch dispatch;
    dispatch.identity_sources = already_capped_and_ordered;
    dispatch.image_offsets.assign(gaussian.size(), 0);
    dispatch.occupied.assign(gaussian.size(), 0);
    dispatch.level_meta.assign(gaussian.size() * 3, 0);
    std::vector<std::vector<IndexedKeypoint>> groups(gaussian.size());
    for (const auto &entry : keypoints) {
      const int level = std::clamp(static_cast<int>(std::lround(entry.point.local.scale)),
                                    0, intervals + 2);
      groups[static_cast<size_t>(entry.point.octave) * (intervals + 3) + level].push_back(entry);
    }
    dispatch.packed.reserve(keypoints.size() * 4);
    dispatch.layout.reserve(keypoints.size() * 3);
    dispatch.ordered_points.reserve(keypoints.size());
    dispatch.source_indices.reserve(keypoints.size());
    dispatch.host_sigmas.reserve(keypoints.size());
    for (size_t group = 0; group < groups.size(); ++group) {
      if (groups[group].empty()) continue;
      const size_t count = static_cast<size_t>(gaussian[group].width) * gaussian[group].height;
      if (count > static_cast<size_t>(std::numeric_limits<int>::max()) - dispatch.gradient_count)
        throw std::overflow_error("Packed gradient volume exceeds kernel indexing range");
      const size_t padded_count = (count + 255) / 256 * 256;
      if (padded_count > static_cast<size_t>(std::numeric_limits<int>::max()) - dispatch.gradient_count)
        throw std::overflow_error("Aligned gradient volume exceeds kernel indexing range");
      dispatch.image_offsets[group] = static_cast<int>(dispatch.gradient_count);
      dispatch.gradient_count += padded_count;
      dispatch.occupied[group] = 1;
      ++dispatch.feature_groups;
      dispatch.level_meta[group * 3 + 0] = gaussian[group].width;
      dispatch.level_meta[group * 3 + 1] = gaussian[group].height;
      dispatch.level_meta[group * 3 + 2] = dispatch.image_offsets[group];
      for (const auto &entry : groups[group]) {
        dispatch.ordered_points.push_back(entry.point);
        if (!dispatch.identity_sources)
          dispatch.source_indices.push_back(entry.source_index);
        dispatch.host_sigmas.push_back(entry.point.octave_sigma);
        dispatch.packed.insert(dispatch.packed.end(),
          {entry.point.local.x, entry.point.local.y, entry.point.octave_sigma, 0.0f});
        // Host layout retained for size checks / non-resident paths; extract
        // gathers the same triples on-device from level_meta[unique_groups].
        dispatch.layout.insert(dispatch.layout.end(),
          {gaussian[group].width, gaussian[group].height, dispatch.image_offsets[group]});
      }
    }
    return dispatch;
  }

  void emit_unique_feature_records(DetectionScratch &scratch, int intervals, int octave,
                                   float base_sigma) {
    scratch.unique_count = 0;
    scratch.unique_records.clear();
    scratch.unique_groups.clear();
    if (scratch.candidate_count == 0) return;
    for (auto entry : {std::make_pair(&claim_kernel, "claim_locations"),
                       std::make_pair(&mark_unique_kernel, "mark_unique_locations"),
                       std::make_pair(&scatter_feature_kernel, "scatter_feature_records")}) {
      if (*entry.first) continue;
      cl_int status = CL_SUCCESS;
      *entry.first = clCreateKernel(program, entry.second, &status);
      check_opencl(status, "clCreateKernel(feature boundary)");
    }
    if (!scan_kernel) {
      cl_int status = CL_SUCCESS;
      scan_kernel = clCreateKernel(program, "scan_dog_counts", &status);
      check_opencl(status, "clCreateKernel(scan_dog_counts)");
    }
    size_t table_size = 1;
    while (table_size < static_cast<size_t>(scratch.candidate_count) * 2) table_size *= 2;
    if (table_size > std::numeric_limits<cl_uint>::max())
      throw std::overflow_error("Location membership table exceeds kernel indexing range");
    const size_t candidate_count = scratch.candidate_count;
    const cl_uint candidate_count_u = static_cast<cl_uint>(candidate_count);
    cl_mem refined = ensure_buffer(scratch.refined, CL_MEM_READ_WRITE,
      scratch.candidate_capacity * 6 * sizeof(float));
    cl_mem owners = ensure_buffer(scratch.owners, CL_MEM_READ_WRITE, table_size * sizeof(cl_uint));
    cl_mem keep = ensure_buffer(scratch.keep, CL_MEM_READ_WRITE, candidate_count * sizeof(cl_uint));
    cl_mem keep_offsets = ensure_buffer(scratch.keep_offsets, CL_MEM_READ_WRITE,
      (candidate_count + 1) * sizeof(cl_uint));
    const cl_uint empty = std::numeric_limits<cl_uint>::max();
    check_opencl(clEnqueueFillBuffer(queue, owners, &empty, sizeof(empty), 0,
      table_size * sizeof(cl_uint), 0, nullptr, nullptr), "feature boundary membership clear");
    const cl_uint table_mask = static_cast<cl_uint>(table_size - 1);
    check_opencl(clSetKernelArg(claim_kernel, 0, sizeof(refined), &refined), "feature boundary claim refined");
    check_opencl(clSetKernelArg(claim_kernel, 1, sizeof(owners), &owners), "feature boundary claim owners");
    check_opencl(clSetKernelArg(claim_kernel, 2, sizeof(candidate_count_u), &candidate_count_u),
      "feature boundary claim count");
    check_opencl(clSetKernelArg(claim_kernel, 3, sizeof(table_mask), &table_mask),
      "feature boundary claim mask");
    check_opencl(clEnqueueNDRangeKernel(queue, claim_kernel, 1, nullptr, &candidate_count,
      nullptr, 0, nullptr, nullptr), "feature boundary claim launch");
    check_opencl(clSetKernelArg(mark_unique_kernel, 0, sizeof(refined), &refined), "feature boundary mark refined");
    check_opencl(clSetKernelArg(mark_unique_kernel, 1, sizeof(owners), &owners), "feature boundary mark owners");
    check_opencl(clSetKernelArg(mark_unique_kernel, 2, sizeof(keep), &keep), "feature boundary mark keep");
    check_opencl(clSetKernelArg(mark_unique_kernel, 3, sizeof(candidate_count_u), &candidate_count_u),
      "feature boundary mark count");
    check_opencl(clSetKernelArg(mark_unique_kernel, 4, sizeof(table_mask), &table_mask),
      "feature boundary mark mask");
    check_opencl(clEnqueueNDRangeKernel(queue, mark_unique_kernel, 1, nullptr, &candidate_count,
      nullptr, 0, nullptr, nullptr), "feature boundary mark launch");
    check_opencl(clEnqueueCopyBuffer(queue, keep, keep_offsets, 0, 0,
      candidate_count * sizeof(cl_uint), 0, nullptr, nullptr), "feature boundary keep copy");
    const int scan_count = static_cast<int>(candidate_count);
    check_opencl(clSetKernelArg(scan_kernel, 0, sizeof(keep_offsets), &keep_offsets),
      "feature boundary keep scan");
    check_opencl(clSetKernelArg(scan_kernel, 1, sizeof(scan_count), &scan_count),
      "feature boundary keep count");
    const size_t scan_size = 256;
    check_opencl(clEnqueueNDRangeKernel(queue, scan_kernel, 1, nullptr, &scan_size, &scan_size,
      0, nullptr, nullptr), "feature boundary keep scan launch");
    // Blocking count read replaces clFinish; unique body stays on device and is
    // concatenated once for a single host materialization in extract_image.
    check_opencl(clEnqueueReadBuffer(queue, keep_offsets, CL_TRUE, candidate_count * sizeof(cl_uint),
      sizeof(scratch.unique_count), &scratch.unique_count, 0, nullptr, nullptr),
      "feature boundary unique count readback");
    if (scratch.unique_count == 0) return;
    if (scratch.unique_count > static_cast<cl_uint>(std::numeric_limits<int>::max()) / 8)
      throw std::overflow_error("Too many unique feature records");
    cl_mem records = ensure_buffer(scratch.records, CL_MEM_READ_WRITE,
      scratch.unique_count * 8 * sizeof(float));
    cl_mem groups = ensure_buffer(scratch.groups, CL_MEM_READ_WRITE,
      scratch.unique_count * sizeof(cl_int));
    check_opencl(clSetKernelArg(scatter_feature_kernel, 0, sizeof(refined), &refined),
      "feature boundary scatter refined");
    check_opencl(clSetKernelArg(scatter_feature_kernel, 1, sizeof(keep_offsets), &keep_offsets),
      "feature boundary scatter offsets");
    check_opencl(clSetKernelArg(scatter_feature_kernel, 2, sizeof(keep), &keep),
      "feature boundary scatter keep");
    check_opencl(clSetKernelArg(scatter_feature_kernel, 3, sizeof(records), &records),
      "feature boundary scatter records");
    check_opencl(clSetKernelArg(scatter_feature_kernel, 4, sizeof(groups), &groups),
      "feature boundary scatter groups");
    check_opencl(clSetKernelArg(scatter_feature_kernel, 5, sizeof(candidate_count_u), &candidate_count_u),
      "feature boundary scatter count");
    check_opencl(clSetKernelArg(scatter_feature_kernel, 6, sizeof(intervals), &intervals),
      "feature boundary scatter intervals");
    check_opencl(clSetKernelArg(scatter_feature_kernel, 7, sizeof(octave), &octave),
      "feature boundary scatter octave");
    check_opencl(clSetKernelArg(scatter_feature_kernel, 8, sizeof(base_sigma), &base_sigma),
      "feature boundary scatter sigma");
    if (scratch.scatter_event) {
      clReleaseEvent(scratch.scatter_event);
      scratch.scatter_event = nullptr;
    }
    check_opencl(clEnqueueNDRangeKernel(queue, scatter_feature_kernel, 1, nullptr, &candidate_count,
      nullptr, 0, nullptr, &scratch.scatter_event), "feature boundary scatter launch");
    scratch.unique_records.clear();
    scratch.unique_groups.clear();
  }

  void materialize_concatenated_unique_host(FeatureScratch &scratch,
                                            std::vector<float> &records,
                                            std::vector<int> &groups) {
    records.clear();
    groups.clear();
    if (scratch.unique_record_count == 0 || !scratch.unique_records.memory ||
        !scratch.unique_groups.memory)
      return;
    records.resize(scratch.unique_record_count * 8);
    groups.resize(scratch.unique_record_count);
    check_opencl(clEnqueueReadBuffer(queue, scratch.unique_records.memory, CL_FALSE, 0,
      records.size() * sizeof(float), records.data(), 0, nullptr, nullptr),
      "concatenated unique records readback");
    check_opencl(clEnqueueReadBuffer(queue, scratch.unique_groups.memory, CL_TRUE, 0,
      groups.size() * sizeof(int), groups.data(), 0, nullptr, nullptr),
      "concatenated unique groups readback");
  }

  std::vector<IndexedKeypoint> keypoints_from_concatenated_unique(
      const std::vector<float> &records, const std::vector<int> &groups,
      int intervals, float base_sigma, bool identity_sources) {
    if (records.size() != groups.size() * 8)
      throw std::logic_error("Concatenated unique host buffers are incomplete");
    const size_t total = groups.size();
    std::vector<IndexedKeypoint> keypoints;
    keypoints.reserve(total);
    for (size_t index = 0; index < total; ++index) {
      const float *values = records.data() + index * 8;
      const int group = groups[index];
      const int levels_per_octave = intervals + 3;
      if (levels_per_octave <= 0 || group < 0)
        throw std::logic_error("Feature boundary group mapping mismatch");
      const int octave = group / levels_per_octave;
      const int level = group % levels_per_octave;
      const float image_factor = std::ldexp(1.0f, octave);
      // Recompute sigma on the host so extract matches detect_* / host-reference
      // numerics. Device exp2 can differ by 1 ULP from std::exp2.
      const float octave_sigma =
          base_sigma * std::exp2((values[2] + 0.5f) / static_cast<float>(intervals));
      const float image_sigma = octave_sigma * image_factor;
      if (!std::isfinite(octave_sigma) || !std::isfinite(image_sigma))
        throw std::overflow_error("Scale-space keypoint sigma overflow");
      const int expected_level =
          std::clamp(static_cast<int>(std::lround(values[2])), 0, intervals + 2);
      if (level != expected_level)
        throw std::logic_error("Feature boundary group mapping mismatch");
      (void)identity_sources;
      keypoints.push_back({{{values[0], values[1], values[2], values[3], values[4]},
                            octave, values[0] * image_factor, values[1] * image_factor,
                            octave_sigma, image_sigma},
                           static_cast<int>(index)});
    }
    return keypoints;
  }

  void device_cap_and_group_order(FeatureScratch &scratch, int level_count,
                                  int max_features) {
    scratch.identity_sources = false;
    if (scratch.unique_record_count == 0 || !scratch.unique_records.memory ||
        !scratch.unique_groups.memory)
      return;
    for (auto entry :
         {std::make_pair(&stable_response_cap_kernel, "stable_response_cap"),
          std::make_pair(&stable_group_reorder_kernel, "stable_group_reorder")}) {
      if (*entry.first) continue;
      cl_int status = CL_SUCCESS;
      *entry.first = clCreateKernel(program, entry.second, &status);
      check_opencl(status, "clCreateKernel(device unique order)");
    }
    const int count = static_cast<int>(scratch.unique_record_count);
    if (max_features > 0 && count > max_features) {
      cl_mem records = scratch.unique_records.memory;
      cl_mem groups = scratch.unique_groups.memory;
      check_opencl(clSetKernelArg(stable_response_cap_kernel, 0, sizeof(records), &records),
                   "response cap records");
      check_opencl(clSetKernelArg(stable_response_cap_kernel, 1, sizeof(groups), &groups),
                   "response cap groups");
      check_opencl(clSetKernelArg(stable_response_cap_kernel, 2, sizeof(count), &count),
                   "response cap count");
      check_opencl(clSetKernelArg(stable_response_cap_kernel, 3, sizeof(max_features), &max_features),
                   "response cap max");
      const size_t one = 1;
      check_opencl(clEnqueueNDRangeKernel(queue, stable_response_cap_kernel, 1, nullptr, &one,
                                          nullptr, 0, nullptr, nullptr),
                   "response cap launch");
      scratch.unique_record_count = static_cast<size_t>(max_features);
    }
    const int ordered_count = static_cast<int>(scratch.unique_record_count);
    if (ordered_count == 0) return;
    cl_mem in_records = scratch.unique_records.memory;
    cl_mem in_groups = scratch.unique_groups.memory;
    cl_mem out_records = ensure_buffer(scratch.unique_records_alt, CL_MEM_READ_WRITE,
                                       static_cast<size_t>(ordered_count) * 8 * sizeof(float));
    cl_mem out_groups = ensure_buffer(scratch.unique_groups_alt, CL_MEM_READ_WRITE,
                                      static_cast<size_t>(ordered_count) * sizeof(int));
    cl_mem counts = ensure_buffer(scratch.group_counts, CL_MEM_READ_WRITE,
                                  static_cast<size_t>(level_count) * sizeof(cl_uint));
    cl_mem cursors = ensure_buffer(scratch.group_cursors, CL_MEM_READ_WRITE,
                                   static_cast<size_t>(level_count) * sizeof(cl_uint));
    check_opencl(clSetKernelArg(stable_group_reorder_kernel, 0, sizeof(in_records), &in_records),
                 "group reorder in records");
    check_opencl(clSetKernelArg(stable_group_reorder_kernel, 1, sizeof(in_groups), &in_groups),
                 "group reorder in groups");
    check_opencl(clSetKernelArg(stable_group_reorder_kernel, 2, sizeof(out_records), &out_records),
                 "group reorder out records");
    check_opencl(clSetKernelArg(stable_group_reorder_kernel, 3, sizeof(out_groups), &out_groups),
                 "group reorder out groups");
    check_opencl(clSetKernelArg(stable_group_reorder_kernel, 4, sizeof(counts), &counts),
                 "group reorder counts");
    check_opencl(clSetKernelArg(stable_group_reorder_kernel, 5, sizeof(cursors), &cursors),
                 "group reorder cursors");
    check_opencl(clSetKernelArg(stable_group_reorder_kernel, 6, sizeof(ordered_count), &ordered_count),
                 "group reorder count");
    check_opencl(clSetKernelArg(stable_group_reorder_kernel, 7, sizeof(level_count), &level_count),
                 "group reorder levels");
    const size_t one = 1;
    check_opencl(clEnqueueNDRangeKernel(queue, stable_group_reorder_kernel, 1, nullptr, &one,
                                        nullptr, 0, nullptr, nullptr),
                 "group reorder launch");
    std::swap(scratch.unique_records, scratch.unique_records_alt);
    std::swap(scratch.unique_groups, scratch.unique_groups_alt);
    scratch.identity_sources = true;
  }

  void concatenate_unique_records(FeatureScratch &scratch,
                                  const std::vector<DetectionScratch*> &octaves) {
    size_t total = 0;
    for (const auto *octave : octaves) total += octave ? octave->unique_count : 0;
    scratch.unique_record_count = total;
    scratch.identity_sources = false;
    if (total == 0) return;
    cl_mem combined = ensure_buffer(scratch.unique_records, CL_MEM_READ_WRITE,
                                    total * 8 * sizeof(float));
    cl_mem combined_groups = ensure_buffer(scratch.unique_groups, CL_MEM_READ_WRITE,
                                           total * sizeof(int));
    size_t destination = 0;
    cl_event last_copy = nullptr;
    for (const auto *octave : octaves) {
      if (!octave || octave->unique_count == 0) continue;
      const size_t record_bytes = static_cast<size_t>(octave->unique_count) * 8 * sizeof(float);
      const size_t group_bytes = static_cast<size_t>(octave->unique_count) * sizeof(int);
      check_opencl(clEnqueueCopyBuffer(queue, octave->records.memory, combined, 0,
        destination * 8 * sizeof(float), record_bytes, 0, nullptr, nullptr),
        "concatenate unique feature records");
      if (last_copy) clReleaseEvent(last_copy);
      check_opencl(clEnqueueCopyBuffer(queue, octave->groups.memory, combined_groups, 0,
        destination * sizeof(int), group_bytes, 0, nullptr, &last_copy),
        "concatenate unique feature groups");
      destination += octave->unique_count;
    }
    // Device cap/reorder may follow immediately; wait for the last concat copy.
    if (last_copy) {
      check_opencl(clWaitForEvents(1, &last_copy), "concatenate unique completion");
      clReleaseEvent(last_copy);
    }
  }

  void gather_resident_orientation_points(FeatureScratch &scratch, const FeatureDispatch &dispatch) {
    scratch.resident_orientation_points = false;
    if (dispatch.ordered_points.empty()) return;
    if (dispatch.host_sigmas.size() != dispatch.ordered_points.size() ||
        dispatch.layout.size() != dispatch.ordered_points.size() * 3 ||
        dispatch.level_meta.size() % 3 != 0 || dispatch.level_meta.empty())
      throw std::logic_error("Feature dispatch source mapping is incomplete");
    if (!dispatch.identity_sources &&
        dispatch.source_indices.size() != dispatch.ordered_points.size())
      throw std::logic_error("Feature dispatch source mapping is incomplete");
    if (scratch.unique_record_count == 0 || !scratch.unique_groups.memory)
      throw std::logic_error("Missing device-resident unique feature records");
    const int count = static_cast<int>(dispatch.ordered_points.size());
    const int level_count = static_cast<int>(dispatch.level_meta.size() / 3);
    cl_mem points = ensure_buffer(scratch.points, CL_MEM_READ_WRITE,
                                  dispatch.ordered_points.size() * 4 * sizeof(float));
    cl_mem layout = ensure_buffer(scratch.layout, CL_MEM_READ_WRITE,
                                  dispatch.layout.size() * sizeof(int));
    cl_mem sigmas = ensure_buffer(scratch.host_sigmas, CL_MEM_READ_ONLY,
                                  dispatch.host_sigmas.size() * sizeof(float));
    cl_mem level_meta = ensure_buffer(scratch.level_meta, CL_MEM_READ_ONLY,
                                      dispatch.level_meta.size() * sizeof(int));
    check_opencl(clEnqueueWriteBuffer(queue, sigmas, CL_FALSE, 0,
      dispatch.host_sigmas.size() * sizeof(float), dispatch.host_sigmas.data(), 0, nullptr, nullptr),
      "resident host sigma upload");
    check_opencl(clEnqueueWriteBuffer(queue, level_meta, CL_FALSE, 0,
      dispatch.level_meta.size() * sizeof(int), dispatch.level_meta.data(), 0, nullptr, nullptr),
      "resident level meta upload");
    cl_mem records = scratch.unique_records.memory;
    cl_mem groups = scratch.unique_groups.memory;
    const size_t global = static_cast<size_t>(count);
    if (dispatch.identity_sources) {
      if (!gather_identity_kernel) {
        cl_int status = CL_SUCCESS;
        gather_identity_kernel = clCreateKernel(program, "gather_identity_features", &status);
        check_opencl(status, "clCreateKernel(gather identity features)");
      }
      check_opencl(clSetKernelArg(gather_identity_kernel, 0, sizeof(records), &records),
        "identity gather records");
      check_opencl(clSetKernelArg(gather_identity_kernel, 1, sizeof(groups), &groups),
        "identity gather groups");
      check_opencl(clSetKernelArg(gather_identity_kernel, 2, sizeof(sigmas), &sigmas),
        "identity gather sigmas");
      check_opencl(clSetKernelArg(gather_identity_kernel, 3, sizeof(level_meta), &level_meta),
        "identity gather level meta");
      check_opencl(clSetKernelArg(gather_identity_kernel, 4, sizeof(points), &points),
        "identity gather points");
      check_opencl(clSetKernelArg(gather_identity_kernel, 5, sizeof(layout), &layout),
        "identity gather layout");
      check_opencl(clSetKernelArg(gather_identity_kernel, 6, sizeof(count), &count),
        "identity gather count");
      check_opencl(clSetKernelArg(gather_identity_kernel, 7, sizeof(level_count), &level_count),
        "identity gather level count");
      check_opencl(clEnqueueNDRangeKernel(queue, gather_identity_kernel, 1, nullptr, &global,
        nullptr, 0, nullptr, nullptr), "identity gather launch");
    } else {
      if (!gather_dispatch_kernel) {
        cl_int status = CL_SUCCESS;
        gather_dispatch_kernel = clCreateKernel(program, "gather_dispatch_features", &status);
        check_opencl(status, "clCreateKernel(gather dispatch features)");
      }
      cl_mem sources = ensure_buffer(scratch.source_indices, CL_MEM_READ_ONLY,
                                     dispatch.source_indices.size() * sizeof(int));
      check_opencl(clEnqueueWriteBuffer(queue, sources, CL_FALSE, 0,
        dispatch.source_indices.size() * sizeof(int), dispatch.source_indices.data(), 0, nullptr, nullptr),
        "resident source index upload");
      check_opencl(clSetKernelArg(gather_dispatch_kernel, 0, sizeof(records), &records),
        "gather records");
      check_opencl(clSetKernelArg(gather_dispatch_kernel, 1, sizeof(groups), &groups),
        "gather groups");
      check_opencl(clSetKernelArg(gather_dispatch_kernel, 2, sizeof(sources), &sources),
        "gather sources");
      check_opencl(clSetKernelArg(gather_dispatch_kernel, 3, sizeof(sigmas), &sigmas),
        "gather sigmas");
      check_opencl(clSetKernelArg(gather_dispatch_kernel, 4, sizeof(level_meta), &level_meta),
        "gather level meta");
      check_opencl(clSetKernelArg(gather_dispatch_kernel, 5, sizeof(points), &points),
        "gather points");
      check_opencl(clSetKernelArg(gather_dispatch_kernel, 6, sizeof(layout), &layout),
        "gather layout");
      check_opencl(clSetKernelArg(gather_dispatch_kernel, 7, sizeof(count), &count),
        "gather count");
      check_opencl(clSetKernelArg(gather_dispatch_kernel, 8, sizeof(level_count), &level_count),
        "gather level count");
      check_opencl(clEnqueueNDRangeKernel(queue, gather_dispatch_kernel, 1, nullptr, &global,
        nullptr, 0, nullptr, nullptr), "gather dispatch launch");
    }
    scratch.resident_orientation_points = true;
  }

  cl_kernel get_feature_kernel(const char *name) {
    cl_kernel *slot = nullptr;
    if (std::string(name) == "sift_orientations")
      slot = &orientation_kernel;
    else if (std::string(name) == "sift_descriptors")
      slot = &descriptor_kernel;
    else
      throw std::invalid_argument("Unsupported feature kernel");
    if (!*slot) {
      cl_int status = CL_SUCCESS;
      *slot = clCreateKernel(program, name, &status);
      check_opencl(status, "clCreateKernel(feature)");
    }
    return *slot;
  }

    void prepare_gradients(const GaussianLevel &level, cl_mem device_image,
                           FeatureScratch *scratch = nullptr, int image_offset = 0) {
    const size_t image_bytes = static_cast<size_t>(level.width) * level.height * sizeof(float);
    cl_mem image_buffer = device_image ? device_image :
      ensure_buffer(feature_image, CL_MEM_READ_ONLY, image_bytes);
    cl_mem magnitude_buffer = ensure_buffer(scratch ? scratch->magnitude : gradient_magnitude,
      CL_MEM_READ_WRITE, image_bytes);
    cl_mem orientation_buffer = ensure_buffer(scratch ? scratch->orientation : gradient_orientation,
      CL_MEM_READ_WRITE, image_bytes);
    if (!gradient_kernel) {
      cl_int status = CL_SUCCESS;
      gradient_kernel = clCreateKernel(program, "sift_gradients", &status);
      check_opencl(status, "clCreateKernel(sift_gradients)");
    }
    if (!device_image) check_opencl(clEnqueueWriteBuffer(queue, image_buffer, CL_TRUE, 0,
      image_bytes, level.pixels.data(), 0, nullptr, nullptr),
      "clEnqueueWriteBuffer(gradient image)");
    check_opencl(clSetKernelArg(gradient_kernel, 0, sizeof(cl_mem),
      &image_buffer), "gradient image arg");
    check_opencl(clSetKernelArg(gradient_kernel, 1, sizeof(cl_mem),
      &magnitude_buffer), "gradient magnitude arg");
    check_opencl(clSetKernelArg(gradient_kernel, 2, sizeof(cl_mem),
      &orientation_buffer), "gradient orientation arg");
    check_opencl(clSetKernelArg(gradient_kernel, 3, sizeof(level.width),
      &level.width), "gradient width arg");
    check_opencl(clSetKernelArg(gradient_kernel, 4, sizeof(level.height),
      &level.height), "gradient height arg");
    check_opencl(clSetKernelArg(gradient_kernel, 5, sizeof(image_offset),
      &image_offset), "gradient image offset arg");
    const size_t global_size[2] = {static_cast<size_t>(level.width),
                     static_cast<size_t>(level.height)};
    check_opencl(clEnqueueNDRangeKernel(queue, gradient_kernel, 2, nullptr,
      global_size, nullptr, 0, nullptr, nullptr),
      "clEnqueueNDRangeKernel(gradients)");
    cached_gradient_pixels = level.pixels;
    cached_gradient_device = device_image;
    cached_gradient_width = level.width;
    cached_gradient_height = level.height;
    gradients_ready = true;
    }

  OpenCLGaussianPyramid &get_pyramid() {
    if (!pyramid)
      pyramid = std::make_unique<OpenCLGaussianPyramid>(queue);
    return *pyramid;
  }

  void report_feature_profile(const char *name) {
    if (!profile_features) return;
    double device_ms = 0.0;
    size_t groups = 0, scratch_bytes = 0;
    for (auto &scratch : feature_scratch) {
      if (!scratch) continue;
      scratch_bytes += scratch->magnitude.capacity + scratch->orientation.capacity +
        scratch->points.capacity + scratch->output.capacity + scratch->layout.capacity +
        scratch->gradient_layout.capacity + scratch->counts.capacity +
        scratch->descriptor_points.capacity + scratch->descriptor_layout.capacity + scratch->descriptors.capacity +
        scratch->orientation_sources.capacity;
      auto &event = std::string(name) == "sift_packed_gradients" ? scratch->gradient_event :
        std::string(name) == "sift_descriptors" && scratch->descriptor_event
          ? scratch->descriptor_event : scratch->event;
      if (!event) continue;
      cl_ulong start = 0, end = 0;
      check_opencl(clGetEventProfilingInfo(event, CL_PROFILING_COMMAND_START,
        sizeof(start), &start, nullptr), "profile batch start");
      check_opencl(clGetEventProfilingInfo(event, CL_PROFILING_COMMAND_END,
        sizeof(end), &end, nullptr), "profile batch end");
      device_ms += static_cast<double>(end - start) * 1.0e-6;
      ++groups;
      clReleaseEvent(event);
      event = nullptr;
    }
    std::fprintf(stderr, "OPENCL_BATCH_FEATURE_PROFILE kernel=%s groups=%zu device_ms=%.3f scratch_bytes=%zu\n",
      name, groups, device_ms, scratch_bytes);
  }

  std::vector<float> run_feature_kernel(const char *name,
      const GaussianLevel &level, const std::vector<float> &points,
      size_t output_stride, cl_mem device_image = nullptr,
      FeatureScratch *scratch = nullptr, const std::vector<int> *layout = nullptr,
      bool read_output = true) {
    const auto feature_start = std::chrono::steady_clock::now();
    const bool profiling = profile_features;
    struct ProfileEvent {
      cl_event value = nullptr;
      ~ProfileEvent() { if (value) clReleaseEvent(value); }
    } feature_event;
    if (level.width < 3 || level.height < 3 ||
        (!device_image && level.pixels.size() != static_cast<size_t>(level.width) * level.height))
      throw std::invalid_argument("Invalid Gaussian image for feature sampling");
    for (float value : level.pixels) {
      if (!std::isfinite(value))
        throw std::invalid_argument("Gaussian image must contain finite values");
    }
    const size_t count = points.size() / 4;
    if (count == 0) return {};
    if (count > static_cast<size_t>(std::numeric_limits<int>::max()) / output_stride)
      throw std::overflow_error("Too many feature points");
    if (layout && (!scratch || layout->size() != count * 3))
      throw std::invalid_argument("Invalid packed feature layout");
    cl_int status = CL_SUCCESS;
    cl_kernel feature_kernel = get_feature_kernel(name);
    const bool reusable_gradients = std::string(name) == "sift_descriptors" &&
      (scratch || (gradients_ready &&
      cached_gradient_width == level.width &&
      cached_gradient_height == level.height &&
      cached_gradient_device == device_image &&
      (device_image || cached_gradient_pixels == level.pixels)));
    if (!reusable_gradients && !layout)
      prepare_gradients(level, device_image, scratch);
    const size_t image_bytes = static_cast<size_t>(level.width) * level.height * sizeof(float);
    cl_mem magnitude_buffer = layout ? scratch->magnitude.memory : ensure_buffer(scratch ? scratch->magnitude : gradient_magnitude,
      CL_MEM_READ_WRITE, image_bytes);
    cl_mem orientation_buffer = layout ? scratch->orientation.memory : ensure_buffer(scratch ? scratch->orientation : gradient_orientation,
      CL_MEM_READ_WRITE, image_bytes);
    const bool resident_points = scratch && scratch->resident_orientation_points && layout;
    if (resident_points && (!scratch->points.memory || !scratch->layout.memory))
      throw std::logic_error("Resident orientation points were not materialized");
    cl_mem points_buffer = resident_points ? scratch->points.memory :
      ensure_buffer(scratch ? scratch->points : feature_points, CL_MEM_READ_ONLY,
                        points.size() * sizeof(float));
    std::vector<float> output(read_output ? count * output_stride : 0);
    cl_mem output_buffer = ensure_buffer(scratch ? scratch->output : feature_output, CL_MEM_READ_WRITE,
              count * output_stride * sizeof(float));
    cl_mem layout_buffer = layout ? (resident_points ? scratch->layout.memory :
      ensure_buffer(scratch->layout, CL_MEM_READ_ONLY, layout->size() * sizeof(int))) : points_buffer;
    try {
    if (layout && !resident_points)
      check_opencl(clEnqueueWriteBuffer(queue, layout_buffer, CL_FALSE, 0,
        layout->size() * sizeof(int), layout->data(), 0, nullptr, nullptr), "feature layout upload");
    if (!resident_points)
      check_opencl(clEnqueueWriteBuffer(queue, points_buffer, CL_FALSE, 0,
        points.size() * sizeof(float), points.data(), 0, nullptr, nullptr),
        "clEnqueueWriteBuffer(feature points)");
    const auto points_ready = std::chrono::steady_clock::now();
    check_opencl(clSetKernelArg(feature_kernel, 0, sizeof(cl_mem), &magnitude_buffer), "feature magnitude arg");
    check_opencl(clSetKernelArg(feature_kernel, 1, sizeof(cl_mem), &orientation_buffer), "feature orientation arg");
    check_opencl(clSetKernelArg(feature_kernel, 2, sizeof(cl_mem), &points_buffer), "feature points arg");
    check_opencl(clSetKernelArg(feature_kernel, 3, sizeof(cl_mem), &output_buffer), "feature output arg");
    const int fixed_width = layout ? 0 : level.width;
    check_opencl(clSetKernelArg(feature_kernel, 4, sizeof(int), &fixed_width), "feature width arg");
    check_opencl(clSetKernelArg(feature_kernel, 5, sizeof(int), &level.height), "feature height arg");
    check_opencl(clSetKernelArg(feature_kernel, 6, sizeof(cl_mem), &layout_buffer), "feature layout arg");
    const bool descriptors = std::string(name) == "sift_descriptors";
    cl_mem counts = !descriptors && scratch ? ensure_buffer(scratch->counts, CL_MEM_READ_WRITE,
      (count + 1) * sizeof(cl_uint)) : nullptr;
    check_opencl(clSetKernelArg(feature_kernel, 7, sizeof(counts), &counts), "feature count buffer");
    if (descriptors) {
      const int count_offset = 0;
      check_opencl(clSetKernelArg(feature_kernel, 8, sizeof(count_offset), &count_offset), "feature count offset");
    }
    const size_t local_size = descriptors ? descriptor_lanes : orientation_lanes;
    const size_t global_size = count * local_size;
    if (scratch && scratch->event) {
      clReleaseEvent(scratch->event);
      scratch->event = nullptr;
    }
    check_opencl(clEnqueueNDRangeKernel(queue, feature_kernel, 1, nullptr,
      &global_size, &local_size, 0, nullptr,
      profiling ? (scratch ? &scratch->event : &feature_event.value) : nullptr), "feature kernel launch");
    if (read_output) check_opencl(clEnqueueReadBuffer(queue, output_buffer, scratch ? CL_FALSE : CL_TRUE, 0,
        output.size() * sizeof(float), output.data(), 0, nullptr, nullptr), "feature readback");
    if (profiling && !scratch) {
      cl_ulong start = 0, end = 0;
      check_opencl(clGetEventProfilingInfo(feature_event.value, CL_PROFILING_COMMAND_START,
        sizeof(start), &start, nullptr), "profile feature start");
      check_opencl(clGetEventProfilingInfo(feature_event.value, CL_PROFILING_COMMAND_END,
        sizeof(end), &end, nullptr), "profile feature end");
      std::fprintf(stderr, "OPENCL_FEATURE_PROFILE kernel=%s points=%zu prepare_ms=%.3f device_ms=%.3f execute_read_ms=%.3f\n",
        name, count, std::chrono::duration<double, std::milli>(points_ready - feature_start).count(),
        static_cast<double>(end - start) * 1.0e-6,
        std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - points_ready).count());
    }
    if (std::string(name) == "sift_descriptors")
      gradients_ready = false;
    return output;
    } catch (...) {
      clFinish(queue);
      throw;
    }
  }

  std::vector<float> resident_descriptors(FeatureScratch &scratch, size_t point_count,
      std::vector<OrientationSource> &sources) {
    const size_t limit = static_cast<size_t>(std::numeric_limits<int>::max()) / 128;
    if (point_count > static_cast<size_t>(std::numeric_limits<int>::max()) / 36)
      throw std::overflow_error("Too many resident orientation points");
    std::vector<float> output;
    cl_uint total = 0;
    cl_event total_event = nullptr;
    try {
      for (auto entry : {std::make_pair(&orientation_pack_kernel, "pack_orientations"),
                         std::make_pair(&scan_kernel, "scan_dog_counts")}) {
        if (*entry.first) continue;
        cl_int status = CL_SUCCESS;
        *entry.first = clCreateKernel(program, entry.second, &status);
        check_opencl(status, "clCreateKernel(resident orientations)");
      }
      cl_mem counts = scratch.counts.memory;
      const int count = static_cast<int>(point_count);
      check_opencl(clSetKernelArg(scan_kernel, 0, sizeof(counts), &counts), "orientation scan buffer");
      check_opencl(clSetKernelArg(scan_kernel, 1, sizeof(count), &count), "orientation scan points");
      const size_t scan_size = 256;
      check_opencl(clEnqueueNDRangeKernel(queue, scan_kernel, 1, nullptr,
        &scan_size, &scan_size, 0, nullptr, nullptr), "orientation scan launch");
      // Overlap pack/descriptor with the oriented-count read. If the first
      // capacity guess is short, retry without downloading the undersized buffers.
      check_opencl(clEnqueueReadBuffer(queue, counts, CL_FALSE, point_count * sizeof(cl_uint),
        sizeof(total), &total, 0, nullptr, &total_event), "oriented count readback");
      // Seed above keypoint count: multi-orientation features are common, and a
      // short first guess forces a full pack/descriptor relaunch.
      const size_t guessed = point_count + point_count / 2 + 1;
      scratch.descriptor_capacity =
          std::min(limit, std::max(scratch.descriptor_capacity, guessed));
      for (int attempt = 0; attempt < 2; ++attempt) {
        const int capacity = static_cast<int>(scratch.descriptor_capacity);
        cl_mem points = ensure_buffer(scratch.descriptor_points, CL_MEM_READ_WRITE,
          scratch.descriptor_capacity * 4 * sizeof(float));
        cl_mem layout = ensure_buffer(scratch.descriptor_layout, CL_MEM_READ_WRITE,
          scratch.descriptor_capacity * 3 * sizeof(int));
        // READ_WRITE: retained for extract→match residency after host readback.
        cl_mem descriptors = ensure_buffer(scratch.descriptors, CL_MEM_READ_WRITE,
          scratch.descriptor_capacity * 128 * sizeof(float));
        cl_mem source_records = ensure_buffer(scratch.orientation_sources, CL_MEM_WRITE_ONLY,
          scratch.descriptor_capacity * sizeof(OrientationSource));
        const cl_mem memories[] = {scratch.points.memory, scratch.output.memory, scratch.layout.memory,
                                  counts, points, layout};
        for (cl_uint argument = 0; argument < 6; ++argument)
          check_opencl(clSetKernelArg(orientation_pack_kernel, argument, sizeof(cl_mem),
            &memories[argument]), "orientation packing memory");
        check_opencl(clSetKernelArg(orientation_pack_kernel, 6, sizeof(count), &count), "orientation packing count");
        check_opencl(clSetKernelArg(orientation_pack_kernel, 7, sizeof(capacity), &capacity), "orientation packing capacity");
        check_opencl(clSetKernelArg(orientation_pack_kernel, 8, sizeof(source_records), &source_records),
          "orientation source records");
        check_opencl(clEnqueueNDRangeKernel(queue, orientation_pack_kernel, 1, nullptr,
          &point_count, nullptr, 0, nullptr, nullptr), "orientation packing launch");
        cl_kernel descriptor = get_feature_kernel("sift_descriptors");
        const cl_mem descriptor_memories[] = {scratch.magnitude.memory, scratch.orientation.memory, points, descriptors};
        for (cl_uint argument = 0; argument < 4; ++argument)
          check_opencl(clSetKernelArg(descriptor, argument, sizeof(cl_mem), &descriptor_memories[argument]),
            "resident descriptor memory");
        const int zero = 0;
        check_opencl(clSetKernelArg(descriptor, 4, sizeof(zero), &zero), "resident descriptor width");
        check_opencl(clSetKernelArg(descriptor, 5, sizeof(zero), &zero), "resident descriptor height");
        check_opencl(clSetKernelArg(descriptor, 6, sizeof(layout), &layout), "resident descriptor layout");
        check_opencl(clSetKernelArg(descriptor, 7, sizeof(counts), &counts), "resident descriptor counts");
        check_opencl(clSetKernelArg(descriptor, 8, sizeof(count), &count), "resident descriptor count offset");
        const size_t global_size = scratch.descriptor_capacity * descriptor_lanes;
        if (scratch.descriptor_event) {
          clReleaseEvent(scratch.descriptor_event);
          scratch.descriptor_event = nullptr;
        }
        check_opencl(clEnqueueNDRangeKernel(queue, descriptor, 1, nullptr, &global_size,
          &descriptor_lanes, 0, nullptr, profile_features ? &scratch.descriptor_event : nullptr),
          "resident descriptor launch");
        if (total_event) {
          check_opencl(clWaitForEvents(1, &total_event), "oriented count completion");
          clReleaseEvent(total_event);
          total_event = nullptr;
        }
        if (total > scratch.descriptor_capacity) {
          if (total > limit) throw std::overflow_error("Too many resident descriptors");
          scratch.descriptor_capacity = total;
          continue; // grow and relaunch; skip host download of truncated buffers
        }
        sources.resize(total);
        output.resize(static_cast<size_t>(total) * 128);
        if (total == 0) return output;
        check_opencl(clEnqueueReadBuffer(queue, source_records, CL_FALSE, 0,
          sources.size() * sizeof(OrientationSource), sources.data(), 0, nullptr, nullptr),
          "orientation source readback");
        check_opencl(clEnqueueReadBuffer(queue, descriptors, CL_TRUE, 0,
          output.size() * sizeof(float), output.data(), 0, nullptr, nullptr),
          "resident descriptor readback");
        return output;
      }
      throw std::logic_error("Resident descriptor capacity retry failed");
    } catch (...) {
      if (total_event) clReleaseEvent(total_event);
      clFinish(queue);
      throw;
    }
  }

  std::vector<RefinedKeypoint> detect_refine(const DoGLevel *levels,
      int scale_count, float threshold, float edge_limit,
      const cl_mem *device_levels = nullptr, DetectionScratch *scratch = nullptr,
      bool refine_phase = false, bool read_refined = true) {
    if (scratch && !refine_phase) {
      scratch->host_offsets.clear();
      scratch->output.clear();
      scratch->candidate_count = 0;
      for (auto &event : scratch->events) {
        if (event) clReleaseEvent(event);
        event = nullptr;
      }
    }
    const auto event_for = [&](size_t stage) -> cl_event * {
      if (profile_features && scratch && scratch->events[stage]) {
        clReleaseEvent(scratch->events[stage]);
        scratch->events[stage] = nullptr;
      }
      return profile_features && scratch ? &scratch->events[stage] : nullptr;
    };
    const int width = levels[0].width;
    const int height = levels[0].height;
    if (width < 3 || height < 3 || scale_count < 3) return {};
    const size_t plane_size = static_cast<size_t>(width) * height;
    if (plane_size > static_cast<size_t>(std::numeric_limits<int>::max()) / scale_count)
      throw std::overflow_error("DoG volume exceeds kernel index range");
    for (int scale = 0; scale < scale_count; ++scale) {
      const auto &level = levels[scale];
      if (level.width != width || level.height != height ||
          level.octave != levels[0].octave || level.scale != scale ||
          (!device_levels && level.pixels.size() != plane_size))
        throw std::invalid_argument("DoG levels must form one contiguous octave");
    }
    if (!count_kernel) {
      cl_int status = CL_SUCCESS;
      count_kernel = clCreateKernel(program, "find_and_count_dog_extrema", &status);
      check_opencl(status, "clCreateKernel(find_and_count_dog_extrema)");
    }
    if (!compact_kernel) {
      cl_int status = CL_SUCCESS;
      compact_kernel = clCreateKernel(program, "compact_dog_candidates", &status);
      check_opencl(status, "clCreateKernel(compact_dog_candidates)");
    }
    const int mask_count = (scale_count - 2) * (height - 2) * (width - 2);
    const size_t block_count = (static_cast<size_t>(mask_count) + candidate_block_size - 1) / candidate_block_size;
    cl_mem shared_volume = nullptr;
    if (device_levels) {
      bool contiguous = true;
      for (int scale = 0; scale < scale_count; ++scale) {
        cl_mem parent = nullptr;
        size_t offset = 0;
        check_opencl(clGetMemObjectInfo(device_levels[scale], CL_MEM_ASSOCIATED_MEMOBJECT,
          sizeof(parent), &parent, nullptr), "DoG parent buffer");
        check_opencl(clGetMemObjectInfo(device_levels[scale], CL_MEM_OFFSET,
          sizeof(offset), &offset, nullptr), "DoG level offset");
        if (scale == 0) shared_volume = parent;
        if (!parent || parent != shared_volume || offset != static_cast<size_t>(scale) * plane_size * sizeof(float))
          contiguous = false;
      }
      if (!contiguous) shared_volume = nullptr;
    }
    cl_mem volume = shared_volume ? shared_volume : ensure_buffer(scratch ? scratch->volume : dog_volume,
      CL_MEM_READ_ONLY, plane_size * scale_count * sizeof(float));
    cl_mem mask = ensure_buffer(scratch ? scratch->mask : candidate_mask, CL_MEM_READ_WRITE, mask_count);
    cl_mem offsets = ensure_buffer(scratch ? scratch->offsets : block_offsets, CL_MEM_READ_WRITE,
                                   (block_count + 1) * sizeof(cl_uint));
    std::vector<cl_uint> local_offsets;
    std::vector<float> local_output;
    auto &host_offsets = scratch ? scratch->host_offsets : local_offsets;
    auto &output = scratch ? scratch->output : local_output;
    if (!scratch) host_offsets.resize(block_count);
    try {
      if (!refine_phase) {
      for (int scale = 0; scale < scale_count; ++scale) {
        if (shared_volume) break;
        const size_t bytes = plane_size * sizeof(float);
        if (device_levels) {
          check_opencl(clEnqueueCopyBuffer(queue, device_levels[scale], volume,
              0, static_cast<size_t>(scale) * bytes, bytes, 0, nullptr, nullptr),
              "clEnqueueCopyBuffer(resident DoG)");
        } else {
          check_opencl(clEnqueueWriteBuffer(queue, volume, CL_FALSE,
              static_cast<size_t>(scale) * bytes, bytes, levels[scale].pixels.data(),
              0, nullptr, nullptr), "clEnqueueWriteBuffer(combined DoG)");
        }
      }
        check_opencl(clSetKernelArg(count_kernel, 0, sizeof(volume), &volume), "combined extrema volume");
        check_opencl(clSetKernelArg(count_kernel, 1, sizeof(mask), &mask), "combined extrema mask");
        check_opencl(clSetKernelArg(count_kernel, 2, sizeof(offsets), &offsets), "candidate count output");
        check_opencl(clSetKernelArg(count_kernel, 3, sizeof(width), &width), "combined extrema width");
        check_opencl(clSetKernelArg(count_kernel, 4, sizeof(height), &height), "combined extrema height");
        check_opencl(clSetKernelArg(count_kernel, 5, sizeof(mask_count), &mask_count), "candidate mask count");
        check_opencl(clSetKernelArg(count_kernel, 6, sizeof(threshold), &threshold), "combined extrema threshold");
        const size_t local_size = candidate_block_size;
        const size_t global_size = block_count * local_size;
      check_opencl(clEnqueueNDRangeKernel(queue, count_kernel, 1, nullptr,
          &global_size, &local_size, 0, nullptr, event_for(0)), "combined extrema count launch");
        if (scratch) {
          if (!scan_kernel) {
            cl_int status = CL_SUCCESS;
            scan_kernel = clCreateKernel(program, "scan_dog_counts", &status);
            check_opencl(status, "clCreateKernel(scan_dog_counts)");
          }
          const int count = static_cast<int>(block_count);
          check_opencl(clSetKernelArg(scan_kernel, 0, sizeof(offsets), &offsets), "scan offsets");
          check_opencl(clSetKernelArg(scan_kernel, 1, sizeof(count), &count), "scan block count");
          const size_t scan_size = 256;
          check_opencl(clEnqueueNDRangeKernel(queue, scan_kernel, 1, nullptr, &scan_size,
            &scan_size, 0, nullptr, event_for(1)), "candidate scan launch");
          if (scratch->count_event) {
            clReleaseEvent(scratch->count_event);
            scratch->count_event = nullptr;
          }
          check_opencl(clEnqueueReadBuffer(queue, offsets, CL_FALSE, block_count * sizeof(cl_uint),
            sizeof(scratch->candidate_count), &scratch->candidate_count, 0, nullptr,
            &scratch->count_event),
            "candidate total readback");
        } else {
          check_opencl(clEnqueueReadBuffer(queue, offsets, CL_TRUE, 0,
            block_count * sizeof(cl_uint), host_offsets.data(), 0, nullptr, nullptr),
            "candidate block counts readback");
        }
        }
      size_t candidate_count = scratch ? scratch->candidate_capacity : 0;
      for (auto &offset : host_offsets) {
        const cl_uint count = offset;
        offset = static_cast<cl_uint>(candidate_count);
        candidate_count += count;
      }
      if (candidate_count == 0) return {};
      if (candidate_count > static_cast<size_t>(std::numeric_limits<int>::max()) / 6)
        throw std::overflow_error("Too many refined candidates");
      static_assert(sizeof(ExtremaCandidate) == sizeof(cl_int) * 3 + sizeof(cl_float));
        cl_mem candidates = scratch ? mask : ensure_buffer(compact_candidates, CL_MEM_READ_WRITE,
          candidate_count * sizeof(ExtremaCandidate));
        cl_mem refined = ensure_buffer(scratch ? scratch->refined : refined_candidates,
          scratch ? CL_MEM_READ_WRITE : CL_MEM_WRITE_ONLY,
          candidate_count * 6 * sizeof(float));
        if (!scratch) check_opencl(clEnqueueWriteBuffer(queue, offsets, CL_FALSE, 0,
          block_count * sizeof(cl_uint), host_offsets.data(), 0, nullptr, nullptr),
          "candidate offsets upload");
      const int count = static_cast<int>(candidate_count);
      if (!scratch) {
      check_opencl(clSetKernelArg(compact_kernel, 0, sizeof(volume), &volume), "compact volume");
      check_opencl(clSetKernelArg(compact_kernel, 1, sizeof(mask), &mask), "compact mask");
      check_opencl(clSetKernelArg(compact_kernel, 2, sizeof(offsets), &offsets), "compact offsets");
      check_opencl(clSetKernelArg(compact_kernel, 3, sizeof(candidates), &candidates), "compact candidates");
      check_opencl(clSetKernelArg(compact_kernel, 4, sizeof(width), &width), "compact width");
      check_opencl(clSetKernelArg(compact_kernel, 5, sizeof(height), &height), "compact height");
      check_opencl(clSetKernelArg(compact_kernel, 6, sizeof(mask_count), &mask_count), "compact mask count");
      check_opencl(clSetKernelArg(compact_kernel, 7, sizeof(count), &count), "compact capacity");
      check_opencl(clEnqueueNDRangeKernel(queue, compact_kernel, 1, nullptr,
          &block_count, nullptr, 0, nullptr, event_for(2)), "compact candidates launch");
      }
      if (scratch && !bounded_refine_kernel) {
        cl_int status = CL_SUCCESS;
        bounded_refine_kernel = clCreateKernel(program, "refine_compacted_candidates", &status);
        check_opencl(status, "clCreateKernel(refine_compacted_candidates)");
      }
      cl_kernel refinement = scratch ? bounded_refine_kernel : refine_kernel;
      check_opencl(clSetKernelArg(refinement, 0, sizeof(volume), &volume), "combined refine volume");
      check_opencl(clSetKernelArg(refinement, 1, sizeof(candidates), &candidates), "combined refine candidates");
      check_opencl(clSetKernelArg(refinement, 2, sizeof(refined), &refined), "combined refine output");
      check_opencl(clSetKernelArg(refinement, 3, sizeof(width), &width), "combined refine width");
      check_opencl(clSetKernelArg(refinement, 4, sizeof(height), &height), "combined refine height");
      check_opencl(clSetKernelArg(refinement, 5, sizeof(scale_count), &scale_count), "combined refine scales");
      check_opencl(clSetKernelArg(refinement, 6, sizeof(count), &count), "combined refine count");
      check_opencl(clSetKernelArg(refinement, 7, sizeof(threshold), &threshold), "combined refine threshold");
      check_opencl(clSetKernelArg(refinement, 8, sizeof(edge_limit), &edge_limit), "combined refine edge");
      if (scratch) {
        check_opencl(clSetKernelArg(refinement, 9, sizeof(offsets), &offsets), "bounded refine counts");
        check_opencl(clSetKernelArg(refinement, 10, sizeof(mask_count), &mask_count), "bounded refine mask count");
      }
      const size_t refinement_size = scratch ? block_count : candidate_count;
      cl_event *refine_wait = event_for(3);
      if (!refine_wait && scratch && !read_refined) {
        if (scratch->refine_event) {
          clReleaseEvent(scratch->refine_event);
          scratch->refine_event = nullptr;
        }
        refine_wait = &scratch->refine_event;
      }
      check_opencl(clEnqueueNDRangeKernel(queue, refinement, 1, nullptr,
          &refinement_size, nullptr, 0, nullptr, refine_wait), "combined refinement launch");
      if (!read_refined) {
        if (scratch) return {};
        throw std::logic_error("Skipping refinement readback requires detection scratch");
      }
        output.resize(candidate_count * 6);
        check_opencl(clEnqueueReadBuffer(queue, refined, scratch ? CL_FALSE : CL_TRUE, 0,
          output.size() * sizeof(float), output.data(), 0, nullptr, nullptr),
          "combined refinement readback");
        if (scratch) return {};
      std::vector<RefinedKeypoint> result;
      for (size_t index = 0; index < candidate_count; ++index) {
        const float *values = output.data() + index * 6;
        if (values[5] != 0.0f)
          result.push_back({values[0], values[1], values[2], values[3], values[4]});
      }
      return result;
    } catch (...) {
      clFinish(queue);
      throw;
    }
  }

  explicit Impl(bool serial_descriptors) {
    descriptor_lanes = serial_descriptors ? 1 : 32;
    orientation_lanes = serial_descriptors ? 1 : 64;
    profile_features = std::getenv("SIFT_OPENCL_PROFILE") != nullptr;
    cl_int status = CL_SUCCESS;
    const cl_device_id device = select_intel_gpu();
    std::string build_options = serial_descriptors
      ? "-cl-std=CL1.2 -DSIFT_DESCRIPTOR_LANES=1"
      : "-cl-std=CL1.2 -DSIFT_DESCRIPTOR_LANES=32";
    build_options += " -DSIFT_CANDIDATE_BLOCK_SIZE=" + std::to_string(candidate_block_size);
    size_t subgroup_bytes = 0;
    if (!serial_descriptors && clGetDeviceInfo(device, CL_DEVICE_SUB_GROUP_SIZES_INTEL,
        0, nullptr, &subgroup_bytes) == CL_SUCCESS && subgroup_bytes > 0 &&
        subgroup_bytes % sizeof(size_t) == 0) {
      std::vector<size_t> subgroup_sizes(subgroup_bytes / sizeof(size_t));
      if (clGetDeviceInfo(device, CL_DEVICE_SUB_GROUP_SIZES_INTEL, subgroup_bytes,
          subgroup_sizes.data(), nullptr) == CL_SUCCESS &&
          std::find(subgroup_sizes.begin(), subgroup_sizes.end(), size_t{32}) != subgroup_sizes.end())
        build_options += " -DSIFT_ORIENTATION_SUBGROUP32=1";
    }
    context = clCreateContext(nullptr, 1, &device, nullptr, nullptr, &status);
    check_opencl(status, "clCreateContext");
    queue = clCreateCommandQueue(context, device,
      profile_features ? CL_QUEUE_PROFILING_ENABLE : 0, &status);
    if (status != CL_SUCCESS) {
      clReleaseContext(context);
      context = nullptr;
      check_opencl(status, "clCreateCommandQueue");
    }

    const char *sources[] = {kernel_source, kOpenCLSiftMatchKernelSource};
    const size_t source_lengths[] = {
        std::char_traits<char>::length(kernel_source),
        std::char_traits<char>::length(kOpenCLSiftMatchKernelSource)};
    program = clCreateProgramWithSource(context, 2, sources, source_lengths, &status);
    if (status != CL_SUCCESS) {
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      queue = nullptr;
      context = nullptr;
      check_opencl(status, "clCreateProgramWithSource");
    }

    status = clBuildProgram(program, 1, &device, build_options.c_str(), nullptr,
                            nullptr);
    if (status != CL_SUCCESS) {
      size_t log_size = 0;
      clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, 0, nullptr,
                            &log_size);
      std::vector<char> log(log_size + 1, '\0');
      clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, log_size,
                            log.data(), nullptr);
      clReleaseProgram(program);
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      program = nullptr;
      queue = nullptr;
      context = nullptr;
      throw std::runtime_error(std::string("OpenCL extrema kernel build failed: ") +
                               log.data());
    }

    kernel = clCreateKernel(program, "find_dog_extrema", &status);
    if (status != CL_SUCCESS) {
      clReleaseProgram(program);
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      program = nullptr;
      queue = nullptr;
      context = nullptr;
      check_opencl(status, "clCreateKernel(find_dog_extrema)");
    }

    refine_kernel = clCreateKernel(program, "refine_dog_extrema", &status);
    if (status != CL_SUCCESS) {
      clReleaseKernel(kernel);
      clReleaseProgram(program);
      clReleaseCommandQueue(queue);
      clReleaseContext(context);
      kernel = nullptr;
      program = nullptr;
      queue = nullptr;
      context = nullptr;
      check_opencl(status, "clCreateKernel(refine_dog_extrema)");
    }
  }

  ~Impl() {
    if (claim_kernel) clReleaseKernel(claim_kernel);
    if (mark_unique_kernel) clReleaseKernel(mark_unique_kernel);
    if (scatter_feature_kernel) clReleaseKernel(scatter_feature_kernel);
    if (gather_dispatch_kernel) clReleaseKernel(gather_dispatch_kernel);
    if (gather_identity_kernel) clReleaseKernel(gather_identity_kernel);
    if (stable_response_cap_kernel) clReleaseKernel(stable_response_cap_kernel);
    if (stable_group_reorder_kernel) clReleaseKernel(stable_group_reorder_kernel);
    if (match_kernel) clReleaseKernel(match_kernel);
    if (orientation_pack_kernel) clReleaseKernel(orientation_pack_kernel);
    if (scan_kernel) clReleaseKernel(scan_kernel);
    if (bounded_refine_kernel) clReleaseKernel(bounded_refine_kernel);
    if (packed_gradient_kernel) clReleaseKernel(packed_gradient_kernel);
    for (auto *buffer : {&dog_volume, &candidate_mask, &block_offsets,
                         &compact_candidates, &refined_candidates,
                         &match_descriptors, &match_xy, &match_index, &match_score,
                         &match_ambiguity, &match_x, &match_y})
      if (buffer->memory) clReleaseMemObject(buffer->memory);
    if (count_kernel) clReleaseKernel(count_kernel);
    if (compact_kernel) clReleaseKernel(compact_kernel);
    if (gradient_orientation.memory)
      clReleaseMemObject(gradient_orientation.memory);
    if (gradient_magnitude.memory)
      clReleaseMemObject(gradient_magnitude.memory);
    if (feature_output.memory)
      clReleaseMemObject(feature_output.memory);
    if (feature_points.memory)
      clReleaseMemObject(feature_points.memory);
    if (feature_image.memory)
      clReleaseMemObject(feature_image.memory);
    if (descriptor_kernel)
      clReleaseKernel(descriptor_kernel);
    if (orientation_kernel)
      clReleaseKernel(orientation_kernel);
    if (gradient_kernel)
      clReleaseKernel(gradient_kernel);
    if (refine_kernel)
      clReleaseKernel(refine_kernel);
    if (kernel)
      clReleaseKernel(kernel);
    if (program)
      clReleaseProgram(program);
    if (queue)
      clReleaseCommandQueue(queue);
    if (context)
      clReleaseContext(context);
  }

  void clear_resident_match() {
    resident_match_count = 0;
    resident_match_uses_extract_descriptors = false;
  }

  void publish_resident_match(FeatureScratch *scratch,
                              const std::vector<SiftFeature> &features,
                              bool device_descriptors_aligned) {
    clear_resident_match();
    if (features.empty()) return;
    std::vector<float> xy(features.size() * 2);
    for (size_t i = 0; i < features.size(); ++i) {
      xy[i * 2 + 0] = features[i].point.keypoint.image_x;
      xy[i * 2 + 1] = features[i].point.keypoint.image_y;
    }
    ensure_buffer(match_xy, CL_MEM_READ_ONLY, xy.size() * sizeof(float));
    check_opencl(clEnqueueWriteBuffer(queue, match_xy.memory, CL_TRUE, 0,
      xy.size() * sizeof(float), xy.data(), 0, nullptr, nullptr),
      "resident match xy upload");
    if (device_descriptors_aligned && scratch && scratch->descriptors.memory &&
        scratch->descriptor_capacity >= features.size()) {
      resident_match_uses_extract_descriptors = true;
    } else {
      std::vector<float> descriptors(features.size() * 128);
      for (size_t i = 0; i < features.size(); ++i)
        std::copy(features[i].descriptor.begin(), features[i].descriptor.end(),
                  descriptors.begin() + i * 128);
      ensure_buffer(match_descriptors, CL_MEM_READ_ONLY,
                    descriptors.size() * sizeof(float));
      check_opencl(clEnqueueWriteBuffer(queue, match_descriptors.memory, CL_TRUE, 0,
        descriptors.size() * sizeof(float), descriptors.data(), 0, nullptr, nullptr),
        "resident match descriptor upload");
      resident_match_uses_extract_descriptors = false;
    }
    resident_match_count = features.size();
  }

  std::vector<SiftMatchResult> run_resident_self_match() {
    if (resident_match_count == 0)
      return {};
    if (!match_kernel) {
      cl_int status = CL_SUCCESS;
      match_kernel = clCreateKernel(program, "match_sift_descriptors", &status);
      check_opencl(status, "clCreateKernel(match_sift_descriptors)");
    }
    cl_mem descriptors = nullptr;
    if (resident_match_uses_extract_descriptors) {
      if (feature_scratch.empty() || !feature_scratch.front()->descriptors.memory)
        throw std::logic_error("Resident extract descriptors missing");
      descriptors = feature_scratch.front()->descriptors.memory;
    } else {
      if (!match_descriptors.memory)
        throw std::logic_error("Resident match descriptors missing");
      descriptors = match_descriptors.memory;
    }
    if (!match_xy.memory)
      throw std::logic_error("Resident match xy missing");
    const int count = static_cast<int>(resident_match_count);
    ensure_buffer(match_index, CL_MEM_WRITE_ONLY, resident_match_count * sizeof(cl_int));
    ensure_buffer(match_score, CL_MEM_WRITE_ONLY, resident_match_count * sizeof(float));
    ensure_buffer(match_ambiguity, CL_MEM_WRITE_ONLY, resident_match_count * sizeof(float));
    ensure_buffer(match_x, CL_MEM_WRITE_ONLY, resident_match_count * sizeof(float));
    ensure_buffer(match_y, CL_MEM_WRITE_ONLY, resident_match_count * sizeof(float));
    check_opencl(clSetKernelArg(match_kernel, 0, sizeof(descriptors), &descriptors),
                 "resident match query");
    check_opencl(clSetKernelArg(match_kernel, 1, sizeof(descriptors), &descriptors),
                 "resident match train");
    check_opencl(clSetKernelArg(match_kernel, 2, sizeof(match_xy.memory), &match_xy.memory),
                 "resident match xy");
    check_opencl(clSetKernelArg(match_kernel, 3, sizeof(match_index.memory), &match_index.memory),
                 "resident match index");
    check_opencl(clSetKernelArg(match_kernel, 4, sizeof(match_score.memory), &match_score.memory),
                 "resident match score");
    check_opencl(clSetKernelArg(match_kernel, 5, sizeof(match_ambiguity.memory),
                                &match_ambiguity.memory),
                 "resident match ambiguity");
    check_opencl(clSetKernelArg(match_kernel, 6, sizeof(match_x.memory), &match_x.memory),
                 "resident match x");
    check_opencl(clSetKernelArg(match_kernel, 7, sizeof(match_y.memory), &match_y.memory),
                 "resident match y");
    check_opencl(clSetKernelArg(match_kernel, 8, sizeof(count), &count),
                 "resident match query count");
    check_opencl(clSetKernelArg(match_kernel, 9, sizeof(count), &count),
                 "resident match train count");
    constexpr size_t tile = 16;
    const size_t groups = (resident_match_count + tile - 1) / tile;
    const size_t global = groups * tile;
    check_opencl(clEnqueueNDRangeKernel(queue, match_kernel, 1, nullptr, &global, &tile,
                                        0, nullptr, nullptr),
                 "resident match launch");
    std::vector<cl_int> indices(resident_match_count);
    std::vector<float> scores(resident_match_count);
    std::vector<float> amb(resident_match_count);
    std::vector<float> mx(resident_match_count);
    std::vector<float> my(resident_match_count);
    check_opencl(clEnqueueReadBuffer(queue, match_index.memory, CL_FALSE, 0,
      indices.size() * sizeof(cl_int), indices.data(), 0, nullptr, nullptr),
      "resident match index read");
    check_opencl(clEnqueueReadBuffer(queue, match_score.memory, CL_FALSE, 0,
      scores.size() * sizeof(float), scores.data(), 0, nullptr, nullptr),
      "resident match score read");
    check_opencl(clEnqueueReadBuffer(queue, match_ambiguity.memory, CL_FALSE, 0,
      amb.size() * sizeof(float), amb.data(), 0, nullptr, nullptr),
      "resident match ambiguity read");
    check_opencl(clEnqueueReadBuffer(queue, match_x.memory, CL_FALSE, 0,
      mx.size() * sizeof(float), mx.data(), 0, nullptr, nullptr),
      "resident match x read");
    check_opencl(clEnqueueReadBuffer(queue, match_y.memory, CL_TRUE, 0,
      my.size() * sizeof(float), my.data(), 0, nullptr, nullptr),
      "resident match y read");
    std::vector<SiftMatchResult> results(resident_match_count);
    for (size_t i = 0; i < resident_match_count; ++i) {
      results[i].match = static_cast<int>(indices[i]);
      results[i].score = scores[i];
      results[i].ambiguity = amb[i];
      results[i].match_x = mx[i];
      results[i].match_y = my[i];
    }
    return results;
  }
};

OpenCLDoGExtrema::OpenCLDoGExtrema() : OpenCLDoGExtrema(false) {}

OpenCLDoGExtrema::OpenCLDoGExtrema(bool serial_descriptors)
  : impl_(new Impl(serial_descriptors)) {}
OpenCLDoGExtrema::~OpenCLDoGExtrema() { delete impl_; }

std::vector<ExtremaCandidate> OpenCLDoGExtrema::detect(
    const std::vector<DoGLevel> &dog_levels, float contrast_threshold) {
  if (!std::isfinite(contrast_threshold) || contrast_threshold < 0.0f)
    throw std::invalid_argument("Contrast threshold must be finite and nonnegative");
  if (dog_levels.size() < 3)
    return {};
  const int width = dog_levels.front().width;
  const int height = dog_levels.front().height;
  if (width < 3 || height < 3)
    return {};

  const int scale_count = static_cast<int>(dog_levels.size());
  const int octave = dog_levels.front().octave;
  std::vector<float> dog_data;
  dog_data.reserve(static_cast<size_t>(scale_count) * width * height);
  for (int scale = 0; scale < scale_count; ++scale) {
    const DoGLevel &level = dog_levels[static_cast<size_t>(scale)];
    if (level.octave != octave || level.scale != scale || level.width != width ||
        level.height != height ||
        level.pixels.size() != static_cast<size_t>(width) * height)
      throw std::invalid_argument("DoG levels must form one contiguous octave");
    dog_data.insert(dog_data.end(), level.pixels.begin(), level.pixels.end());
  }

  const size_t work_item_count = static_cast<size_t>(scale_count - 2) *
                                 (height - 2) * (width - 2);
  const size_t input_bytes = dog_data.size() * sizeof(float);
  cl_int status = CL_SUCCESS;
  cl_mem input = clCreateBuffer(impl_->context,
                                CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
                                input_bytes, dog_data.data(), &status);
  check_opencl(status, "clCreateBuffer(DoG volume)");
  cl_mem mask = clCreateBuffer(impl_->context, CL_MEM_WRITE_ONLY,
                               work_item_count * sizeof(cl_uchar), nullptr,
                               &status);
  if (status != CL_SUCCESS) {
    clReleaseMemObject(input);
    check_opencl(status, "clCreateBuffer(candidate mask)");
  }

  try {
    const int args[] = {width, height, scale_count};
    check_opencl(clSetKernelArg(impl_->kernel, 0, sizeof(input), &input),
                 "clSetKernelArg(DoG volume)");
    check_opencl(clSetKernelArg(impl_->kernel, 1, sizeof(mask), &mask),
                 "clSetKernelArg(candidate mask)");
    for (cl_uint i = 0; i < 3; ++i)
      check_opencl(clSetKernelArg(impl_->kernel, 2 + i, sizeof(args[i]),
                                  &args[i]),
                   "clSetKernelArg(extrema dimensions)");
    check_opencl(clSetKernelArg(impl_->kernel, 5, sizeof(contrast_threshold),
                                &contrast_threshold),
                 "clSetKernelArg(contrast threshold)");

    const size_t global_size[3] = {static_cast<size_t>(width - 2),
                                   static_cast<size_t>(height - 2),
                                   static_cast<size_t>(scale_count - 2)};
    check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->kernel, 3, nullptr,
                                        global_size, nullptr, 0, nullptr, nullptr),
                 "clEnqueueNDRangeKernel(extrema)");

    std::vector<cl_uchar> candidate_mask(work_item_count);
    check_opencl(clEnqueueReadBuffer(impl_->queue, mask, CL_TRUE, 0,
                                     candidate_mask.size() * sizeof(cl_uchar),
                                     candidate_mask.data(), 0, nullptr, nullptr),
                 "clEnqueueReadBuffer(candidate mask)");

    std::vector<ExtremaCandidate> candidates;
    for (size_t i = 0; i < candidate_mask.size(); ++i) {
      if (candidate_mask[i] == 0)
        continue;
      size_t index = i;
      const int x = static_cast<int>(index % static_cast<size_t>(width - 2)) + 1;
      index /= static_cast<size_t>(width - 2);
      const int y = static_cast<int>(index % static_cast<size_t>(height - 2)) + 1;
      const int scale = static_cast<int>(index / static_cast<size_t>(height - 2)) + 1;
      const float response = dog_levels[static_cast<size_t>(scale)]
                                 .pixels[static_cast<size_t>(y) * width + x];
      candidates.push_back({x, y, scale, response});
    }

    clReleaseMemObject(mask);
    clReleaseMemObject(input);
    return candidates;
  } catch (...) {
    clReleaseMemObject(mask);
    clReleaseMemObject(input);
    throw;
  }
}

std::vector<RefinedKeypoint> OpenCLDoGExtrema::refine(
    const std::vector<DoGLevel> &dog_levels,
    const std::vector<ExtremaCandidate> &candidates,
    float contrast_threshold, float edge_limit) {
  if (!std::isfinite(contrast_threshold) || contrast_threshold < 0.0f ||
      !std::isfinite(edge_limit) || edge_limit <= 0.0f)
    throw std::invalid_argument("Refinement thresholds must be finite and positive");
  if (candidates.empty() || dog_levels.size() < 3)
    return {};

  const int width = dog_levels.front().width;
  const int height = dog_levels.front().height;
  const int scale_count = static_cast<int>(dog_levels.size());
  const int octave = dog_levels.front().octave;
  std::vector<float> dog_data;
  dog_data.reserve(static_cast<size_t>(scale_count) * width * height);
  for (int scale = 0; scale < scale_count; ++scale) {
    const DoGLevel &level = dog_levels[static_cast<size_t>(scale)];
    if (level.octave != octave || level.scale != scale || level.width != width ||
        level.height != height ||
        level.pixels.size() != static_cast<size_t>(width) * height)
      throw std::invalid_argument("DoG levels must form one contiguous octave");
    dog_data.insert(dog_data.end(), level.pixels.begin(), level.pixels.end());
  }

  static_assert(sizeof(ExtremaCandidate) == sizeof(int) * 3 + sizeof(float));
  const size_t dog_bytes = dog_data.size() * sizeof(float);
  const size_t candidate_bytes = candidates.size() * sizeof(ExtremaCandidate);
  cl_int status = CL_SUCCESS;
  cl_mem dog_buffer = clCreateBuffer(impl_->context,
                                     CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
                                     dog_bytes, dog_data.data(), &status);
  check_opencl(status, "clCreateBuffer(DoG volume for refinement)");
  cl_mem candidate_buffer = clCreateBuffer(
      impl_->context, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, candidate_bytes,
      const_cast<ExtremaCandidate *>(candidates.data()), &status);
  if (status != CL_SUCCESS) {
    clReleaseMemObject(dog_buffer);
    check_opencl(status, "clCreateBuffer(candidates for refinement)");
  }
  const size_t output_count = candidates.size() * 6;
  cl_mem refined_buffer = clCreateBuffer(
      impl_->context, CL_MEM_WRITE_ONLY, output_count * sizeof(float), nullptr,
      &status);
  if (status != CL_SUCCESS) {
    clReleaseMemObject(candidate_buffer);
    clReleaseMemObject(dog_buffer);
    check_opencl(status, "clCreateBuffer(refined candidates)");
  }

  try {
    const int candidate_count = static_cast<int>(candidates.size());
    check_opencl(clSetKernelArg(impl_->refine_kernel, 0, sizeof(dog_buffer),
                                &dog_buffer),
                 "clSetKernelArg(refinement DoG volume)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 1,
                                sizeof(candidate_buffer), &candidate_buffer),
                 "clSetKernelArg(refinement candidates)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 2, sizeof(refined_buffer),
                                &refined_buffer),
                 "clSetKernelArg(refinement output)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 3, sizeof(width), &width),
                 "clSetKernelArg(refinement width)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 4, sizeof(height), &height),
                 "clSetKernelArg(refinement height)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 5, sizeof(scale_count),
                                &scale_count),
                 "clSetKernelArg(refinement scale count)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 6,
                                sizeof(candidate_count), &candidate_count),
                 "clSetKernelArg(refinement candidate count)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 7,
                                sizeof(contrast_threshold),
                                &contrast_threshold),
                 "clSetKernelArg(refinement contrast threshold)");
    check_opencl(clSetKernelArg(impl_->refine_kernel, 8, sizeof(edge_limit),
                                &edge_limit),
                 "clSetKernelArg(refinement edge limit)");

    const size_t global_size = candidates.size();
    check_opencl(clEnqueueNDRangeKernel(impl_->queue, impl_->refine_kernel, 1,
                                        nullptr, &global_size, nullptr, 0,
                                        nullptr, nullptr),
                 "clEnqueueNDRangeKernel(refinement)");

    std::vector<float> host_output(output_count);
    check_opencl(clEnqueueReadBuffer(impl_->queue, refined_buffer, CL_TRUE, 0,
                                     output_count * sizeof(float),
                                     host_output.data(), 0, nullptr, nullptr),
                 "clEnqueueReadBuffer(refinement)");

    std::vector<RefinedKeypoint> result;
    for (size_t i = 0; i < candidates.size(); ++i) {
      const float *values = host_output.data() + i * 6;
      if (values[5] != 0.0f)
        result.push_back({values[0], values[1], values[2], values[3], values[4]});
    }

    clReleaseMemObject(refined_buffer);
    clReleaseMemObject(candidate_buffer);
    clReleaseMemObject(dog_buffer);
    return result;
  } catch (...) {
    clReleaseMemObject(refined_buffer);
    clReleaseMemObject(candidate_buffer);
    clReleaseMemObject(dog_buffer);
    throw;
  }
}

std::vector<ScaleSpaceKeypoint> OpenCLDoGExtrema::detect_pyramid(
    const std::vector<DoGLevel> &dog_levels, int octave_count, int intervals,
    float base_sigma, float contrast_threshold, float edge_limit) {
  return detect_pyramid_impl(dog_levels, octave_count, intervals, base_sigma,
                contrast_threshold, edge_limit, nullptr);
}

std::vector<ScaleSpaceKeypoint> OpenCLDoGExtrema::detect_pyramid_impl(
  const std::vector<DoGLevel> &dog_levels, int octave_count, int intervals,
  float base_sigma, float contrast_threshold, float edge_limit,
  const std::vector<_cl_mem *> *device_levels) {
  if (octave_count <= 0 || octave_count > 30 || intervals <= 0 ||
      intervals > std::numeric_limits<int>::max() - 2 ||
      !std::isfinite(base_sigma) || base_sigma <= 0.0f ||
      !std::isfinite(contrast_threshold) || contrast_threshold < 0.0f ||
      !std::isfinite(edge_limit) || edge_limit <= 0.0f)
    throw std::invalid_argument("Invalid scale-space detector configuration");
  const size_t levels_per_octave = static_cast<size_t>(intervals) + 2;
  if (dog_levels.size() / levels_per_octave != static_cast<size_t>(octave_count) ||
      dog_levels.size() % levels_per_octave != 0)
    throw std::invalid_argument("DoG level count does not match detector configuration");

  if (device_levels && device_levels->size() != dog_levels.size())
    throw std::invalid_argument("Device DoG level count does not match pyramid");
  for (size_t index = 0; index < dog_levels.size(); ++index) {
    const auto &level = dog_levels[index];
    if (level.octave != static_cast<int>(index / levels_per_octave) ||
        level.scale != static_cast<int>(index % levels_per_octave) ||
        level.width <= 0 || level.height <= 0 ||
        (device_levels ? !(*device_levels)[index] :
         level.pixels.size() != static_cast<size_t>(level.width) * level.height))
      throw std::invalid_argument("DoG pyramid layout is invalid");
  }

  std::vector<ScaleSpaceKeypoint> result;
  if (device_levels) {
    if (impl_->detection_scratch.size() < static_cast<size_t>(octave_count))
      impl_->detection_scratch.resize(octave_count);
    try {
      for (int phase = 0; phase < 2; ++phase) {
        bool submitted = false;
        for (int octave = 0; octave < octave_count; ++octave) {
          auto &scratch = impl_->detection_scratch[octave];
          if (!scratch) scratch = std::make_unique<Impl::DetectionScratch>();
          if (phase == 1) {
            if (scratch->candidate_count <= scratch->candidate_capacity) continue;
            if (scratch->candidate_count > static_cast<size_t>(std::numeric_limits<int>::max()) / 6)
              throw std::overflow_error("Too many refined candidates");
            scratch->candidate_capacity = scratch->candidate_count;
          }
          const size_t offset = static_cast<size_t>(octave) * levels_per_octave;
          impl_->detect_refine(dog_levels.data() + offset,
            static_cast<int>(levels_per_octave), contrast_threshold, edge_limit,
            device_levels->data() + offset, scratch.get(), phase == 1);
          submitted = true;
        }
        if (submitted) check_opencl(clFinish(impl_->queue), "batched detection phase completion");
      }
      for (int octave = 0; octave < octave_count; ++octave) {
        auto &scratch = impl_->detection_scratch[octave];
        scratch->output.resize(static_cast<size_t>(scratch->candidate_count) * 6);
      }
      if (impl_->profile_features) {
        double stage_ms[4]{};
        for (int octave = 0; octave < octave_count; ++octave) {
          for (int stage = 0; stage < 4; ++stage) {
            const auto event = impl_->detection_scratch[static_cast<size_t>(octave)]->events[stage];
            if (!event) continue;
            cl_ulong start = 0, end = 0;
            check_opencl(clGetEventProfilingInfo(event, CL_PROFILING_COMMAND_START,
              sizeof(start), &start, nullptr), "profile detection start");
            check_opencl(clGetEventProfilingInfo(event, CL_PROFILING_COMMAND_END,
              sizeof(end), &end, nullptr), "profile detection end");
            stage_ms[stage] += static_cast<double>(end - start) * 1.0e-6;
          }
        }
        std::fprintf(stderr, "OPENCL_DETECTION_PROFILE extrema_count_device_ms=%.3f scan_device_ms=%.3f compact_device_ms=%.3f refine_device_ms=%.3f\n",
          stage_ms[0], stage_ms[1], stage_ms[2], stage_ms[3]);
      }
    } catch (...) {
      clFinish(impl_->queue);
      throw;
    }
  }
  const auto host_start = impl_->profile_features && device_levels ? std::chrono::steady_clock::now() :
      std::chrono::steady_clock::time_point{};
  for (int octave = 0; octave < octave_count; ++octave) {
    const auto begin = dog_levels.begin() +
                       static_cast<size_t>(octave) * levels_per_octave;
    std::vector<RefinedKeypoint> refined;
    if (device_levels) {
      const auto &output = impl_->detection_scratch[octave]->output;
      refined.reserve(output.size() / 6);
      for (size_t index = 0; index < output.size(); index += 6) {
        const float *values = output.data() + index;
        if (values[5] != 0.0f)
          refined.push_back({values[0], values[1], values[2], values[3], values[4]});
      }
    } else {
      refined = impl_->detect_refine(&*begin, static_cast<int>(levels_per_octave),
        contrast_threshold, edge_limit);
    }
    const float image_factor = std::ldexp(1.0f, octave);
    std::unordered_set<std::array<float, 3>, LocationHash> locations;
    locations.reserve(refined.size());
    for (const auto &point : refined) {
      if (!locations.insert({point.x, point.y, point.scale}).second) continue;
      const float octave_sigma =
          base_sigma * std::exp2((point.scale + 0.5f) / intervals);
      const float image_sigma = octave_sigma * image_factor;
      if (!std::isfinite(image_sigma))
        throw std::overflow_error("Scale-space keypoint sigma overflow");
      result.push_back({point, octave, point.x * image_factor,
                        point.y * image_factor, octave_sigma, image_sigma});
    }
  }
  if (impl_->profile_features && device_levels) {
    const double host_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - host_start).count();
    std::fprintf(stderr, "OPENCL_HOST_DETECTION_PROFILE parse_dedup_map_ms=%.3f keypoints=%zu resident=%d\n",
        host_ms, result.size(), static_cast<int>(device_levels != nullptr));
  }
  return result;
}

std::vector<ScaleSpaceKeypoint> OpenCLDoGExtrema::detect_image(
    const std::vector<float> &image, int width, int height, int octave_count,
    int intervals, float base_sigma, float contrast_threshold, float edge_limit) {
  if (octave_count <= 0 || octave_count > 30 || intervals <= 0 || intervals > 32 ||
      !std::isfinite(base_sigma) || base_sigma < 0.1f || base_sigma > 16.0f ||
      !std::isfinite(contrast_threshold) || contrast_threshold < 0.0f ||
      !std::isfinite(edge_limit) || edge_limit <= 0.0f)
    throw std::invalid_argument("Invalid image detector configuration");
  auto &pyramid = impl_->get_pyramid();
  const auto levels = pyramid.build_with_differences(
      image, width, height, octave_count, intervals, base_sigma, true);
    return detect_pyramid_impl(levels.differences, octave_count, intervals, base_sigma,
               contrast_threshold, edge_limit, &levels.device_differences);
}

std::vector<OrientedKeypoint> OpenCLDoGExtrema::assign_orientations(
    const GaussianLevel &level, const std::vector<ScaleSpaceKeypoint> &points) {
  return assign_orientations_impl(level, points, nullptr);
}

std::vector<OrientedKeypoint> OpenCLDoGExtrema::assign_orientations_impl(
    const GaussianLevel &level, const std::vector<ScaleSpaceKeypoint> &points,
    _cl_mem *device_image) {
  std::vector<float> packed;
  for (const auto &point : points) {
    if (point.octave != level.octave || !std::isfinite(point.local.x) ||
        !std::isfinite(point.local.y) || point.local.x < 0.0f ||
        point.local.y < 0.0f || point.local.x >= level.width ||
        point.local.y >= level.height || !std::isfinite(point.octave_sigma) ||
        point.octave_sigma < 0.1f || point.octave_sigma > 4096.0f)
      throw std::invalid_argument("Invalid orientation sampling point");
    packed.insert(packed.end(), {point.local.x, point.local.y, point.octave_sigma, 0.0f});
  }
  const auto angles = impl_->run_feature_kernel("sift_orientations", level, packed, 36, device_image);
  std::vector<OrientedKeypoint> result;
  for (size_t index = 0; index < points.size(); ++index) {
    for (size_t bin = 0; bin < 36; ++bin) {
      const float angle = angles[index * 36 + bin];
      if (angle >= 0.0f) result.push_back({points[index], angle});
    }
  }
  return result;
}

std::vector<SiftFeature> OpenCLDoGExtrema::compute_descriptors(
    const GaussianLevel &level, const std::vector<OrientedKeypoint> &points) {
  return compute_descriptors_impl(level, points, nullptr);
}

std::vector<SiftFeature> OpenCLDoGExtrema::compute_descriptors_impl(
    const GaussianLevel &level, const std::vector<OrientedKeypoint> &points,
    _cl_mem *device_image) {
  std::vector<float> packed;
  for (const auto &point : points) {
    const auto &keypoint = point.keypoint;
    if (keypoint.octave != level.octave || !std::isfinite(keypoint.local.x) ||
        !std::isfinite(keypoint.local.y) || keypoint.local.x < 0.0f ||
        keypoint.local.y < 0.0f || keypoint.local.x >= level.width ||
        keypoint.local.y >= level.height || !std::isfinite(keypoint.octave_sigma) ||
        keypoint.octave_sigma < 0.1f || keypoint.octave_sigma > 4096.0f ||
        !std::isfinite(point.orientation_degrees) || point.orientation_degrees < 0.0f ||
        point.orientation_degrees >= 360.0f)
      throw std::invalid_argument("Invalid descriptor sampling point");
    packed.insert(packed.end(), {keypoint.local.x, keypoint.local.y,
                                 keypoint.octave_sigma, point.orientation_degrees});
  }
  const auto values = impl_->run_feature_kernel("sift_descriptors", level, packed, 128, device_image);
  std::vector<SiftFeature> result;
  for (size_t index = 0; index < points.size(); ++index) {
    SiftFeature feature;
    feature.point = points[index];
    std::copy_n(values.begin() + index * 128, 128, feature.descriptor.begin());
    result.push_back(feature);
  }
  return result;
}

std::vector<SiftFeature> OpenCLDoGExtrema::extract_image(
    const std::vector<float> &image, int width, int height, int octave_count,
    int intervals, float base_sigma, float contrast_threshold, float edge_limit,
    int max_features) {
  if (octave_count <= 0 || octave_count > 30 || intervals <= 0 || intervals > 32 ||
      !std::isfinite(base_sigma) || base_sigma < 0.1f || base_sigma > 16.0f ||
      !std::isfinite(contrast_threshold) || contrast_threshold < 0.0f ||
      !std::isfinite(edge_limit) || edge_limit <= 0.0f || max_features < 0)
    throw std::invalid_argument("Invalid image extractor configuration");
  const auto profile_start = std::chrono::steady_clock::now();
  impl_->clear_resident_match();
  impl_->gradients_ready = false;
  auto &pyramid = impl_->get_pyramid();
  const auto levels = pyramid.build_with_differences(
      image, width, height, octave_count, intervals, base_sigma, true, false);
  const auto &gaussian = levels.gaussian;
  const auto &differences = levels.differences;
  const auto difference_end = std::chrono::steady_clock::now();
  // Extract path: keep refined records on-device, emit unique mapped records with
  // sigma/group tags, host-cap/group via build_feature_dispatch, then gather
  // group-ordered orientation points and layout from device unique records/groups
  // (no float4 points upload; layout derived from compact level_meta). detect_*
  // APIs retain host hash membership and the refined round trip.
  const size_t levels_per_octave = static_cast<size_t>(intervals) + 2;
  if (differences.size() != static_cast<size_t>(octave_count) * levels_per_octave)
    throw std::invalid_argument("DoG pyramid does not match extractor configuration");
  if (impl_->detection_scratch.size() < static_cast<size_t>(octave_count))
    impl_->detection_scratch.resize(octave_count);
  try {
    for (int phase = 0; phase < 2; ++phase) {
      std::vector<cl_event> waits;
      waits.reserve(static_cast<size_t>(octave_count));
      for (int octave = 0; octave < octave_count; ++octave) {
        auto &scratch = impl_->detection_scratch[octave];
        if (!scratch) scratch = std::make_unique<Impl::DetectionScratch>();
        if (phase == 1) {
          if (scratch->candidate_count <= scratch->candidate_capacity) continue;
          if (scratch->candidate_count > static_cast<size_t>(std::numeric_limits<int>::max()) / 6)
            throw std::overflow_error("Too many refined candidates");
          scratch->candidate_capacity = scratch->candidate_count;
        }
        const size_t offset = static_cast<size_t>(octave) * levels_per_octave;
        impl_->detect_refine(differences.data() + offset,
          static_cast<int>(levels_per_octave), contrast_threshold, edge_limit,
          levels.device_differences.data() + offset, scratch.get(), phase == 1, false);
        if (phase == 0) {
          if (scratch->count_event) waits.push_back(scratch->count_event);
        } else {
          if (scratch->refine_event) waits.push_back(scratch->refine_event);
          else if (scratch->events[3]) waits.push_back(scratch->events[3]);
        }
      }
      // Wait only on count/refine events instead of flushing the whole queue.
      if (!waits.empty())
        check_opencl(clWaitForEvents(static_cast<cl_uint>(waits.size()), waits.data()),
                     "extract detection phase completion");
    }
    // Always wait for the last refine launch (phase 0 always refines; phase 1 may skip).
    {
      std::vector<cl_event> refine_waits;
      refine_waits.reserve(static_cast<size_t>(octave_count));
      for (int octave = 0; octave < octave_count; ++octave) {
        auto *scratch = impl_->detection_scratch[octave].get();
        if (!scratch) continue;
        if (scratch->refine_event) refine_waits.push_back(scratch->refine_event);
        else if (scratch->events[3]) refine_waits.push_back(scratch->events[3]);
      }
      if (!refine_waits.empty())
        check_opencl(clWaitForEvents(static_cast<cl_uint>(refine_waits.size()), refine_waits.data()),
                     "extract detection refine completion");
    }
    for (int octave = 0; octave < octave_count; ++octave)
      impl_->emit_unique_feature_records(*impl_->detection_scratch[octave], intervals, octave,
                                         base_sigma);
    std::vector<cl_event> scatter_waits;
    scatter_waits.reserve(static_cast<size_t>(octave_count));
    for (int octave = 0; octave < octave_count; ++octave) {
      auto *scratch = impl_->detection_scratch[octave].get();
      if (scratch && scratch->scatter_event) scatter_waits.push_back(scratch->scatter_event);
    }
    if (!scatter_waits.empty())
      check_opencl(clWaitForEvents(static_cast<cl_uint>(scatter_waits.size()), scatter_waits.data()),
                   "extract unique scatter completion");
  } catch (...) {
    clFinish(impl_->queue);
    throw;
  }
  std::vector<Impl::DetectionScratch*> octave_scratch(static_cast<size_t>(octave_count));
  std::vector<cl_uint> octave_unique_counts(static_cast<size_t>(octave_count));
  for (int octave = 0; octave < octave_count; ++octave) {
    octave_scratch[octave] = impl_->detection_scratch[octave].get();
    octave_unique_counts[octave] = octave_scratch[octave]->unique_count;
  }
  if (impl_->feature_scratch.empty())
    impl_->feature_scratch.push_back(std::make_unique<Impl::FeatureScratch>());
  auto *feature_scratch = impl_->feature_scratch.front().get();
  // Device-side concat, then one host materialization. Response cap + stable
  // group reorder stay on-device only when max_features > 0 (identity gather).
  // Uncapped ladder path skips the single-WI reorder — it was a net loss vs
  // host bucket + source-index upload.
  impl_->concatenate_unique_records(*feature_scratch, octave_scratch);
  (void)octave_unique_counts;
  const bool device_ordered = max_features > 0;
  if (device_ordered) {
    const int level_count = static_cast<int>(gaussian.size());
    impl_->device_cap_and_group_order(*feature_scratch, level_count, max_features);
  }
  std::vector<float> concatenated_records;
  std::vector<int> concatenated_groups;
  impl_->materialize_concatenated_unique_host(*feature_scratch, concatenated_records,
                                              concatenated_groups);
  auto keypoints = impl_->keypoints_from_concatenated_unique(
      concatenated_records, concatenated_groups, intervals, base_sigma,
      feature_scratch->identity_sources);
  auto dispatch = impl_->build_feature_dispatch(
      std::move(keypoints), gaussian, intervals,
      device_ordered ? 0 : max_features, feature_scratch->identity_sources);
  const auto detector_end = std::chrono::steady_clock::now();
  std::vector<SiftFeature> result;
  double orientation_ms = 0.0;
  double descriptor_ms = 0.0;
  std::vector<float> descriptors;
  std::vector<Impl::OrientationSource> orientation_sources;
  std::vector<int> gradient_layout;
  std::vector<OrientedKeypoint> oriented;
  auto &ordered_points = dispatch.ordered_points;
  auto &packed = dispatch.packed;
  auto &layout = dispatch.layout;
  auto &image_offsets = dispatch.image_offsets;
  const size_t gradient_count = dispatch.gradient_count;
  const size_t feature_groups = dispatch.feature_groups;
  const auto orientation_start = std::chrono::steady_clock::now();
  if (feature_groups > 0) try {
    auto *scratch = feature_scratch;
    impl_->gather_resident_orientation_points(*scratch, dispatch);
    impl_->ensure_buffer(scratch->magnitude, CL_MEM_READ_WRITE, gradient_count * sizeof(float));
    impl_->ensure_buffer(scratch->orientation, CL_MEM_READ_WRITE, gradient_count * sizeof(float));
    cl_mem shared_image = nullptr;
    bool packed_gradients = true;
    for (size_t group = 0; group < gaussian.size(); ++group) {
      if (!dispatch.occupied[group]) continue;
      cl_mem parent = nullptr;
      size_t offset = 0;
      check_opencl(clGetMemObjectInfo(levels.device_gaussian[group], CL_MEM_ASSOCIATED_MEMOBJECT,
        sizeof(parent), &parent, nullptr), "Gaussian parent buffer");
      check_opencl(clGetMemObjectInfo(levels.device_gaussian[group], CL_MEM_OFFSET,
        sizeof(offset), &offset, nullptr), "Gaussian level offset");
      if (gradient_layout.empty()) shared_image = parent;
      if (!parent || parent != shared_image || offset % sizeof(float) != 0 ||
          offset / sizeof(float) > static_cast<size_t>(std::numeric_limits<int>::max())) {
        packed_gradients = false;
        break;
      }
      gradient_layout.insert(gradient_layout.end(), {gaussian[group].width, gaussian[group].height,
        static_cast<int>(offset / sizeof(float)), image_offsets[group]});
    }
    if (packed_gradients) {
      if (!impl_->packed_gradient_kernel) {
        cl_int status = CL_SUCCESS;
        impl_->packed_gradient_kernel = clCreateKernel(impl_->program, "sift_packed_gradients", &status);
        check_opencl(status, "clCreateKernel(packed gradients)");
      }
      const size_t layout_bytes = gradient_layout.size() * sizeof(int);
      cl_mem metadata = impl_->ensure_buffer(scratch->gradient_layout, CL_MEM_READ_ONLY, layout_bytes);
      check_opencl(clEnqueueWriteBuffer(impl_->queue, metadata, CL_FALSE, 0, layout_bytes,
        gradient_layout.data(), 0, nullptr, nullptr), "packed gradient layout upload");
      cl_kernel kernel = impl_->packed_gradient_kernel;
      const int level_count = static_cast<int>(gradient_layout.size() / 4);
      const int pixel_count = static_cast<int>(gradient_count);
      check_opencl(clSetKernelArg(kernel, 0, sizeof(shared_image), &shared_image), "packed gradient image");
      check_opencl(clSetKernelArg(kernel, 1, sizeof(cl_mem), &scratch->magnitude.memory), "packed gradient magnitude");
      check_opencl(clSetKernelArg(kernel, 2, sizeof(cl_mem), &scratch->orientation.memory), "packed gradient orientation");
      check_opencl(clSetKernelArg(kernel, 3, sizeof(metadata), &metadata), "packed gradient metadata");
      check_opencl(clSetKernelArg(kernel, 4, sizeof(level_count), &level_count), "packed gradient levels");
      check_opencl(clSetKernelArg(kernel, 5, sizeof(pixel_count), &pixel_count), "packed gradient pixels");
      const size_t local_size = 256;
      const size_t global_size = (gradient_count + local_size - 1) / local_size * local_size;
      if (scratch->gradient_event) {
        clReleaseEvent(scratch->gradient_event);
        scratch->gradient_event = nullptr;
      }
      check_opencl(clEnqueueNDRangeKernel(impl_->queue, kernel, 1, nullptr, &global_size,
        &local_size, 0, nullptr, impl_->profile_features ? &scratch->gradient_event : nullptr),
        "packed gradient launch");
      impl_->gradients_ready = true;
    }
    if (!packed_gradients) {
      for (size_t group = 0; group < gaussian.size(); ++group) {
        if (!dispatch.occupied[group]) continue;
        impl_->prepare_gradients(gaussian[group], levels.device_gaussian[group], scratch,
          image_offsets[group]);
      }
    }
    impl_->run_feature_kernel("sift_orientations", gaussian.front(), packed,
      36, levels.device_gaussian.front(), scratch, &layout, false);
    const auto descriptor_start = std::chrono::steady_clock::now();
    orientation_ms = std::chrono::duration<double, std::milli>(descriptor_start - orientation_start).count();
    descriptors = impl_->resident_descriptors(*scratch, ordered_points.size(), orientation_sources);
    scratch->resident_orientation_points = false;
    impl_->report_feature_profile("sift_packed_gradients");
    impl_->report_feature_profile("sift_orientations");
    impl_->report_feature_profile("sift_descriptors");
    oriented.reserve(descriptors.size() / 128);
    result.reserve(descriptors.size() / 128);
    for (const auto &source : orientation_sources) {
      if (source.point >= ordered_points.size() || !(source.angle >= 0.0f))
        throw std::logic_error("Invalid resident orientation source");
      oriented.push_back({ordered_points[source.point], source.angle});
    }
    if (descriptors.size() != oriented.size() * 128)
      throw std::logic_error("Resident descriptor count does not match orientations");
    for (size_t index = 0; index < oriented.size(); ++index) {
      SiftFeature feature;
      feature.point = oriented[index];
      std::copy_n(descriptors.begin() + index * 128, 128, feature.descriptor.begin());
      result.push_back(feature);
    }
    descriptor_ms = std::chrono::duration<double, std::milli>(
      std::chrono::steady_clock::now() - descriptor_start).count();
  } catch (...) {
    clFinish(impl_->queue);
    throw;
  }
  impl_->gradients_ready = false;
  const size_t uncapped_feature_count = result.size();
  if (max_features > 0 && result.size() > static_cast<size_t>(max_features)) {
    std::stable_sort(result.begin(), result.end(), [](const auto &first,
                                                      const auto &second) {
      return std::abs(first.point.keypoint.local.response) >
             std::abs(second.point.keypoint.local.response);
    });
    result.resize(static_cast<size_t>(max_features));
  }
  // Retain descriptors on the extract queue for match_last_self(). Uncapped
  // extracts reuse the device descriptor buffer; capped paths re-pack once.
  {
    Impl::FeatureScratch *scratch =
        impl_->feature_scratch.empty() ? nullptr : impl_->feature_scratch.front().get();
    const bool device_aligned =
        max_features == 0 && result.size() == uncapped_feature_count && scratch &&
        scratch->descriptors.memory;
    impl_->publish_resident_match(scratch, result, device_aligned);
  }
  if (std::getenv("SIFT_OPENCL_PROFILE")) {
    const auto milliseconds = [](auto start, auto end) {
      return std::chrono::duration<double, std::milli>(end - start).count();
    };
    const auto profile_end = std::chrono::steady_clock::now();
    std::fprintf(stderr,
                 "OPENCL_PROFILE gaussian_dog_ms=%.3f "
                 "extrema_refine_ms=%.3f orientation_ms=%.3f "
                 "descriptor_ms=%.3f "
                 "resident_feature_handoff=1 resident_orientation_points=1 "
                 "resident_layout_gather=1 "
                 "total_ms=%.3f gaussian_levels=%zu dog_levels=%zu "
                 "keypoints=%zu features=%zu feature_groups=%zu\n",
                 milliseconds(profile_start, difference_end),
                 milliseconds(difference_end, detector_end),
                 orientation_ms, descriptor_ms,
                 milliseconds(profile_start, profile_end), gaussian.size(),
                 differences.size(), ordered_points.size(), result.size(),
                 feature_groups);
  }
  return result;
}

bool OpenCLDoGExtrema::has_resident_match() const {
  return impl_->resident_match_count > 0;
}

std::vector<SiftMatchResult> OpenCLDoGExtrema::match_last_self() {
  return impl_->run_resident_self_match();
}

} // namespace sift_extractor::detail
