// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <sycl/sycl.hpp>
#include <cstdint>
#include <string>
#include <vector>

// ---------------------------------------------------------------------------
// Component-level performance profiling (opt-in, off by default).
//
// Opt-in per-stage profiling (KVWEAVE_QUANT_PROFILE=1 or
// quant_profile_set_enabled(true)). When enabled, always uses the multi-kernel
// global-memory path so each stage is timed separately; results are numerically
// unchanged. When disabled: fused single-kernel for chunk_size <= MAX_SLM_CHUNK,
// otherwise the multi-kernel global-memory path, with no added overhead.
// ---------------------------------------------------------------------------
enum class QuantStage {
    LoadGather = 0,
    Hadamard,
    ReduceQuantize,
    Pack4bit,
    Unpack4bit,
    DequantLoad,
    HadamardInverse,
    PrecondWriteback,
    Count
};

struct QuantStageStat {
    const char* name;
    uint64_t total_ns;
    uint64_t calls;
};

void quant_profile_set_enabled(bool enabled);
bool quant_profile_is_enabled();
void quant_profile_reset();
std::vector<QuantStageStat> quant_profile_snapshot();

struct sycl_quantization_args {
    int qbit;
    int blocks_num;
    int block_size;
    int head_num;
    int head_dim;
    bool rh;
    bool asym;
    std::string scaling_method;

    // Number of layers stacked contiguously in src/dst (element_count spans
    // all of them). Each layer is quantized independently with its own
    // scale/zero-point. Default 1.
    int64_t num_layers = 1;

    // > 0: src is fused [num_layers / fused_src_head_num, tokens,
    // fused_src_head_num * head_dim] and is read per (layer, head) unit in
    // place; dst/scales keep the split [num_layers, tokens, head_dim] layout.
    // Quantize only; per_channel/per_token only.
    int64_t fused_src_head_num = 0;

    // Dequantize counterpart: > 0 writes dst as fused [num_layers /
    // fused_dst_head_num, tokens, fused_dst_head_num * head_dim] while src and
    // scales keep the split layout. per_channel/per_token only.
    int64_t fused_dst_head_num = 0;

    // Preconditioning: forward permutation P and sign-flip diagonal D for
    // H·D·P·x, used as-is (gather) by the global-memory path.
    const int32_t* perm = nullptr;   // device pointer, length = chunk_size
    const float*   signs = nullptr;  // device pointer, length = chunk_size

    // inv_perm = argsort(perm), signs_reordered = signs[inv_perm]; used by the
    // SLM path to read/write src/dst in coalesced order and permute only into SLM.
    const int32_t* inv_perm = nullptr;        // device pointer, length = chunk_size
    const float*   signs_reordered = nullptr; // device pointer, length = chunk_size
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
