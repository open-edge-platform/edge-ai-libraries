// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <sycl/sycl.hpp>
#include <cstdint>
#include <string>
#include <vector>

struct sycl_quantization_args {
    int qbit;
    int blocks_num;
    int block_size;
    int head_num;
    int head_dim;
    bool rh;
    bool asym;
    std::string scaling_method;

    const int32_t* perm = nullptr;   // device pointer, length = hadamard_size
    const float*   signs = nullptr;  // device pointer, length = hadamard_size
};

// Quantize KV cache data on XPU.
// src: device pointer to fp16/bf16/fp32 input, element_count elements
// dst: device pointer to int8 output (packed int4 for qbit=4)
// scales_out: device pointer to float[num_chunks] (written by kernel)
// zps_out: device pointer to float[num_chunks] (written by kernel, zero if symmetric)
// Returns event for synchronization.
template<typename KVType, typename QType>
sycl::event quantize_kvcache_sycl(
    sycl::queue& q,
    const KVType* src,
    QType* dst,
    float* scales_out,
    float* zps_out,
    int64_t element_count,
    const sycl_quantization_args& args,
    const std::vector<sycl::event>& deps = {});

template<typename KVType, typename QType>
sycl::event dequantize_kvcache_sycl(
    sycl::queue& q,
    const QType* src,
    KVType* dst,
    const float* scales_in,
    const float* zps_in,
    int64_t element_count,
    const sycl_quantization_args& args,
    const std::vector<sycl::event>& deps = {});

// 4-bit packing: pack int8 logical values into packed nibbles on device.
sycl::event pack_int4_sycl(
    sycl::queue& q,
    const int8_t* logical,
    int8_t* packed,
    int64_t logical_count,
    const std::vector<sycl::event>& deps = {});

// 4-bit unpacking: unpack packed nibbles into int8 logical values on device.
sycl::event unpack_int4_sycl(
    sycl::queue& q,
    const int8_t* packed,
    int8_t* logical,
    int64_t logical_count,
    const std::vector<sycl::event>& deps = {});
