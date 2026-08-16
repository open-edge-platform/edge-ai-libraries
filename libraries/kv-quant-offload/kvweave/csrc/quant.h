// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <unordered_map>
#include <type_traits>
#include <immintrin.h>
#include <stdexcept>
#include <cstdint>

#ifdef USE_MULTITHREADING
#include <omp.h>
#endif


void fast_walsh_hadamard_transform(float* x, int64_t n);

void fast_walsh_hadamard_transform_fused(const float* in, float* out, int64_t n,
                                         const int32_t* perm, const float* signs);

void fast_walsh_hadamard_inverse_fused(const float* in, float* out, int64_t n,
                                       const int32_t* perm, const float* signs);

struct quantization_args {
    struct tls_map_wrapper {
        inline static thread_local std::unordered_map<uint64_t, float> data;
        float& operator[](uint64_t key) { return data[key]; }
    } quantize_block_scales;

    struct tls_map_wrapper_zps {
        inline static thread_local std::unordered_map<uint64_t, float> data;
        float& operator[](uint64_t key) { return data[key]; }
    } quantize_block_zps;

    int qbit;
    int blocks_num;
    int block_size;
    int head_num;
    int head_dim;
    bool rh;
    bool asym;
    std::string scaling_method;
    int num_threads = 0;   // 0 = use OMP_NUM_THREADS / all available cores

    // Preconditioning: perm (P), signs (D) for H·D·P·x transform
    const int32_t* perm = nullptr;       // permutation indices, length = chunk_size
    const float*   signs = nullptr;      // sign-flip diagonal (±1), length = chunk_size
};

namespace q4_detail {

inline int64_t packed_size(int64_t logical_count) {
    return (logical_count + 1) / 2;
}

inline void pack_value(int8_t* dst, int64_t logical_idx, int8_t value) {
    int64_t byte_idx = logical_idx / 2;
    uint8_t nibble = static_cast<uint8_t>(value) & 0x0F;
    uint8_t byte = static_cast<uint8_t>(dst[byte_idx]);
    if ((logical_idx & 1) == 0) {
        byte = static_cast<uint8_t>((byte & 0xF0) | nibble);
    } else {
        byte = static_cast<uint8_t>((byte & 0x0F) | (nibble << 4));
    }
    dst[byte_idx] = static_cast<int8_t>(byte);
}

inline int8_t unpack_value(const int8_t* src, int64_t logical_idx) {
    uint8_t byte = static_cast<uint8_t>(src[logical_idx / 2]);
    uint8_t nibble = ((logical_idx & 1) == 0) ? (byte & 0x0F) : ((byte >> 4) & 0x0F);
    return static_cast<int8_t>((nibble >= 8) ? (static_cast<int>(nibble) - 16) : static_cast<int>(nibble));
}

#if defined(__SSSE3__)
inline __m128i pack_16_logical_sse(__m128i values) {
    const __m128i mask = _mm_set1_epi8(0x0F);
    const __m128i even_idx = _mm_setr_epi8(0, 2, 4, 6, 8, 10, 12, 14,
                                           -1, -1, -1, -1, -1, -1, -1, -1);
    const __m128i odd_idx = _mm_setr_epi8(1, 3, 5, 7, 9, 11, 13, 15,
                                          -1, -1, -1, -1, -1, -1, -1, -1);
    __m128i nibbles = _mm_and_si128(values, mask);
    __m128i even = _mm_shuffle_epi8(nibbles, even_idx);
    __m128i odd = _mm_slli_epi16(_mm_shuffle_epi8(nibbles, odd_idx), 4);
    return _mm_or_si128(even, odd);
}
#endif

inline __m128i unpack_8_packed_sse(__m128i packed) {
    const __m128i mask = _mm_set1_epi8(0x0F);
    const __m128i sign_bit = _mm_set1_epi8(0x08);
    __m128i low = _mm_and_si128(packed, mask);
    __m128i high = _mm_and_si128(_mm_srli_epi16(packed, 4), mask);
    __m128i interleaved = _mm_unpacklo_epi8(low, high);
    return _mm_sub_epi8(_mm_xor_si128(interleaved, sign_bit), sign_bit);
}

inline __m128i unpack_16_low_packed_sse(__m128i packed) {
    const __m128i mask = _mm_set1_epi8(0x0F);
    const __m128i sign_bit = _mm_set1_epi8(0x08);
    __m128i low = _mm_and_si128(packed, mask);
    __m128i high = _mm_and_si128(_mm_srli_epi16(packed, 4), mask);
    __m128i interleaved = _mm_unpacklo_epi8(low, high);
    return _mm_sub_epi8(_mm_xor_si128(interleaved, sign_bit), sign_bit);
}

inline __m128i unpack_16_high_packed_sse(__m128i packed) {
    const __m128i mask = _mm_set1_epi8(0x0F);
    const __m128i sign_bit = _mm_set1_epi8(0x08);
    __m128i low = _mm_and_si128(packed, mask);
    __m128i high = _mm_and_si128(_mm_srli_epi16(packed, 4), mask);
    __m128i interleaved = _mm_unpackhi_epi8(low, high);
    return _mm_sub_epi8(_mm_xor_si128(interleaved, sign_bit), sign_bit);
}

inline void pack_buffer(const int8_t* logical, int8_t* packed, int64_t logical_count) {
    int64_t i = 0;
#if defined(__AVX512BW__) && defined(__AVX512DQ__)
    const __m512i mask512 = _mm512_set1_epi8(0x0F);
    const __m512i even_idx512 = _mm512_set_epi8(
        -1, -1, -1, -1, -1, -1, -1, -1, 14, 12, 10, 8, 6, 4, 2, 0,
        -1, -1, -1, -1, -1, -1, -1, -1, 14, 12, 10, 8, 6, 4, 2, 0,
        -1, -1, -1, -1, -1, -1, -1, -1, 14, 12, 10, 8, 6, 4, 2, 0,
        -1, -1, -1, -1, -1, -1, -1, -1, 14, 12, 10, 8, 6, 4, 2, 0);
    const __m512i odd_idx512 = _mm512_set_epi8(
        -1, -1, -1, -1, -1, -1, -1, -1, 15, 13, 11, 9, 7, 5, 3, 1,
        -1, -1, -1, -1, -1, -1, -1, -1, 15, 13, 11, 9, 7, 5, 3, 1,
        -1, -1, -1, -1, -1, -1, -1, -1, 15, 13, 11, 9, 7, 5, 3, 1,
        -1, -1, -1, -1, -1, -1, -1, -1, 15, 13, 11, 9, 7, 5, 3, 1);
    for (; i + 64 <= logical_count; i += 64) {
        __m512i values = _mm512_loadu_si512(reinterpret_cast<const __m512i*>(logical + i));
        __m512i nibbles = _mm512_and_si512(values, mask512);
        __m512i even = _mm512_shuffle_epi8(nibbles, even_idx512);
        __m512i odd = _mm512_slli_epi16(_mm512_shuffle_epi8(nibbles, odd_idx512), 4);
        __m512i packed_lanes = _mm512_or_si512(even, odd);
        __m128i lane0 = _mm512_extracti32x4_epi32(packed_lanes, 0);
        __m128i lane1 = _mm512_extracti32x4_epi32(packed_lanes, 1);
        __m128i lane2 = _mm512_extracti32x4_epi32(packed_lanes, 2);
        __m128i lane3 = _mm512_extracti32x4_epi32(packed_lanes, 3);
        _mm_storel_epi64(reinterpret_cast<__m128i*>(packed + i / 2), lane0);
        _mm_storel_epi64(reinterpret_cast<__m128i*>(packed + i / 2 + 8), lane1);
        _mm_storel_epi64(reinterpret_cast<__m128i*>(packed + i / 2 + 16), lane2);
        _mm_storel_epi64(reinterpret_cast<__m128i*>(packed + i / 2 + 24), lane3);
    }
#endif
#if defined(__SSSE3__)
    for (; i + 16 <= logical_count; i += 16) {
        __m128i values = _mm_loadu_si128(reinterpret_cast<const __m128i*>(logical + i));
        __m128i packed_values = pack_16_logical_sse(values);
        _mm_storel_epi64(reinterpret_cast<__m128i*>(packed + i / 2), packed_values);
    }
#endif
    for (; i + 1 < logical_count; i += 2) {
        uint8_t low = static_cast<uint8_t>(logical[i]) & 0x0F;
        uint8_t high = static_cast<uint8_t>(logical[i + 1]) & 0x0F;
        packed[i / 2] = static_cast<int8_t>(low | (high << 4));
    }
    if (i < logical_count) {
        packed[i / 2] = static_cast<int8_t>(static_cast<uint8_t>(logical[i]) & 0x0F);
    }
}

inline void unpack_buffer(const int8_t* packed, int8_t* logical, int64_t logical_count) {
    int64_t i = 0;
#if defined(__AVX512BW__) && defined(__AVX512DQ__)
    for (; i + 64 <= logical_count; i += 64) {
        __m128i p0 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(packed + i / 2));
        __m128i p1 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(packed + i / 2 + 16));
        _mm_storeu_si128(reinterpret_cast<__m128i*>(logical + i), unpack_16_low_packed_sse(p0));
        _mm_storeu_si128(reinterpret_cast<__m128i*>(logical + i + 16), unpack_16_high_packed_sse(p0));
        _mm_storeu_si128(reinterpret_cast<__m128i*>(logical + i + 32), unpack_16_low_packed_sse(p1));
        _mm_storeu_si128(reinterpret_cast<__m128i*>(logical + i + 48), unpack_16_high_packed_sse(p1));
    }
#endif
    for (; i + 32 <= logical_count; i += 32) {
        __m128i packed_values = _mm_loadu_si128(reinterpret_cast<const __m128i*>(packed + i / 2));
        _mm_storeu_si128(reinterpret_cast<__m128i*>(logical + i), unpack_16_low_packed_sse(packed_values));
        _mm_storeu_si128(reinterpret_cast<__m128i*>(logical + i + 16), unpack_16_high_packed_sse(packed_values));
    }
    for (; i + 16 <= logical_count; i += 16) {
        __m128i packed_values = _mm_loadl_epi64(reinterpret_cast<const __m128i*>(packed + i / 2));
        _mm_storeu_si128(reinterpret_cast<__m128i*>(logical + i), unpack_8_packed_sse(packed_values));
    }
    for (; i < logical_count; ++i) {
        logical[i] = unpack_value(packed, i);
    }
}

} // namespace q4_detail

// ipex: 2(k&v) x [block_num, block_size, head_num, head_dim](src)
template<typename kvtype, typename qtype>
void quantize_block_rh(kvtype* src, qtype* dst, int64_t element_count, int64_t scale_id, quantization_args& args)
{
    int64_t num_chunks = 1;
    if (args.scaling_method == "per_token") {
        num_chunks = args.blocks_num * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        num_chunks = args.head_dim;
    } 
    
    int64_t chunk_size = element_count / num_chunks;

    int64_t qmax_int = (1 << (args.qbit - 1)) - 1;
    int64_t qmin_int = -(1 << (args.qbit - 1));
    float qmax_float = static_cast<float>(qmax_int);
    float qmin_float = static_cast<float>(qmin_int);
    
    bool is_per_channel = (args.scaling_method == "per_channel");
    int64_t stride = is_per_channel ? args.head_dim : 1;

#ifdef USE_MULTITHREADING
    {
        std::vector<float> p_scales(static_cast<size_t>(num_chunks));
        std::vector<float> p_zps(static_cast<size_t>(num_chunks));
        int nthreads = (args.num_threads > 0) ? args.num_threads : omp_get_max_threads();
        // Per-channel: dst writes are strided (stride=head_dim). Cap threads so each thread
        // owns at least one cache line worth of chunks, preventing false sharing.
        if (is_per_channel) {
            int cl_chunks = std::max(1, 64 / static_cast<int>(sizeof(qtype)));
            nthreads = std::min(nthreads, std::max(1, static_cast<int>(num_chunks) / cl_chunks));
        }
        #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            int64_t offset = is_per_channel ? chunk : chunk * chunk_size;
            std::vector<float> local_buf(static_cast<size_t>(chunk_size));
            for (int64_t i = 0; i < chunk_size; ++i)
                local_buf[static_cast<size_t>(i)] = static_cast<float>(src[i * stride + offset]);
            {
                std::vector<float> fused_out(static_cast<size_t>(chunk_size));
                fast_walsh_hadamard_transform_fused(local_buf.data(), fused_out.data(), chunk_size, args.perm, args.signs);
                std::copy(fused_out.begin(), fused_out.end(), local_buf.begin());
            }
            float min_val = local_buf[0], max_val = local_buf[0];
            for (const auto& v : local_buf) {
                min_val = std::min(min_val, v);
                max_val = std::max(max_val, v);
            }
            float scale = 0.0f, zeropoint = 0.0f;
            if (args.asym) {
                scale = (max_val - min_val) / (qmax_float - qmin_float);
                zeropoint = min_val - qmin_float * scale;
            } else {
                scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
            }
            p_scales[static_cast<size_t>(chunk)] = scale;
            p_zps[static_cast<size_t>(chunk)] = zeropoint;
            float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;
            for (int64_t i = 0; i < chunk_size; ++i) {
                float q_val = std::clamp(std::round((local_buf[static_cast<size_t>(i)] - zeropoint) * inv_scale), qmin_float, qmax_float);
                dst[i * stride + offset] = static_cast<qtype>(q_val);
            }
        }
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
            args.quantize_block_scales[scale_key] = p_scales[static_cast<size_t>(chunk)];
            args.quantize_block_zps[scale_key] = p_zps[static_cast<size_t>(chunk)];
        }
    }
#else
    std::vector<float> transformed_src(static_cast<size_t>(chunk_size));
    for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
        int64_t offset = is_per_channel ? chunk : chunk * chunk_size;

        for (int64_t i = 0; i < chunk_size; ++i) {
            transformed_src[static_cast<size_t>(i)] = static_cast<float>(src[i * stride + offset]);
        }

        {
            std::vector<float> fused_out(static_cast<size_t>(chunk_size));
            fast_walsh_hadamard_transform_fused(transformed_src.data(), fused_out.data(), chunk_size, args.perm, args.signs);
            std::copy(fused_out.begin(), fused_out.end(), transformed_src.begin());
        }

        float min_val = transformed_src[0];
        float max_val = transformed_src[0];
        for (const auto& v : transformed_src) {
            min_val = std::min(min_val, v);
            max_val = std::max(max_val, v);
        }

        float scale = 0.0f;
        float zeropoint = 0.0f;
        if (args.asym) {
            scale = (max_val - min_val) / (qmax_float - qmin_float);
            zeropoint = min_val - qmin_float * scale;
        } else {
            scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
        }

        args.quantize_block_scales[scale_key] = scale;
        args.quantize_block_zps[scale_key] = zeropoint;

        float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;

        for (int64_t i = 0; i < chunk_size; ++i) {
            float q_val = std::clamp(std::round((transformed_src[static_cast<size_t>(i)] - zeropoint) * inv_scale), qmin_float, qmax_float);
            dst[i * stride + offset] = static_cast<qtype>(q_val);
        }
    }
#endif
}

template<typename kvtype, typename qtype>
void quantize_block(kvtype* src, qtype* dst, int64_t element_count, int64_t scale_id, quantization_args& args)
{
    int64_t num_chunks = 1;
    if (args.scaling_method == "per_token") {
        num_chunks = args.blocks_num * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        num_chunks = args.head_dim;
    } 
    
    int64_t chunk_size = element_count / num_chunks;

    int64_t qmax_int = (1 << (args.qbit - 1)) - 1;
    int64_t qmin_int = -(1 << (args.qbit - 1));
    float qmax_float = static_cast<float>(qmax_int);
    float qmin_float = static_cast<float>(qmin_int);
    
    bool is_per_channel = (args.scaling_method == "per_channel");
    int64_t stride = is_per_channel ? args.head_dim : 1;

#ifdef USE_MULTITHREADING
    {
        std::vector<float> p_scales(static_cast<size_t>(num_chunks));
        std::vector<float> p_zps(static_cast<size_t>(num_chunks));
        int nthreads = (args.num_threads > 0) ? args.num_threads : omp_get_max_threads();
        if (is_per_channel) {
            int cl_chunks = std::max(1, 64 / static_cast<int>(sizeof(qtype)));
            nthreads = std::min(nthreads, std::max(1, static_cast<int>(num_chunks) / cl_chunks));
        }
        #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            int64_t offset = is_per_channel ? chunk : chunk * chunk_size;
            float min_val = static_cast<float>(src[offset]);
            float max_val = static_cast<float>(src[offset]);
            for (int64_t i = 0; i < chunk_size; ++i) {
                float v = static_cast<float>(src[i * stride + offset]);
                min_val = std::min(min_val, v);
                max_val = std::max(max_val, v);
            }
            float scale = 0.0f, zeropoint = 0.0f;
            if (args.asym) {
                scale = (max_val - min_val) / (qmax_float - qmin_float);
                zeropoint = min_val - qmin_float * scale;
            } else {
                scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
            }
            p_scales[static_cast<size_t>(chunk)] = scale;
            p_zps[static_cast<size_t>(chunk)] = zeropoint;
            float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;
            for (int64_t i = 0; i < chunk_size; ++i) {
                float q_val = std::clamp(std::round((static_cast<float>(src[i * stride + offset]) - zeropoint) * inv_scale), qmin_float, qmax_float);
                dst[i * stride + offset] = static_cast<qtype>(q_val);
            }
        }
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
            args.quantize_block_scales[scale_key] = p_scales[static_cast<size_t>(chunk)];
            args.quantize_block_zps[scale_key] = p_zps[static_cast<size_t>(chunk)];
        }
    }
#else
    for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
        int64_t offset = is_per_channel ? chunk : chunk * chunk_size;
        
        float min_val = static_cast<float>(src[offset]);
        float max_val = static_cast<float>(src[offset]);
        for (int64_t i = 0; i < chunk_size; ++i) {
            float v = static_cast<float>(src[i * stride + offset]);
            min_val = std::min(min_val, v);
            max_val = std::max(max_val, v);
        }

        float scale = 0.0f;
        float zeropoint = 0.0f;
        if (args.asym) {
            scale = (max_val - min_val) / (qmax_float - qmin_float);
            zeropoint = min_val - qmin_float * scale;
        } else {
            scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
        }

        args.quantize_block_scales[scale_key] = scale;
        args.quantize_block_zps[scale_key] = zeropoint;
        float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;

        for (int64_t i = 0; i < chunk_size; ++i) {
            float q_val = std::clamp(std::round((static_cast<float>(src[i * stride + offset]) - zeropoint) * inv_scale), qmin_float, qmax_float);
            dst[i * stride + offset] = static_cast<qtype>(q_val);
        }
    }
#endif
}

template<typename kvtype, typename qtype>
void dequantize_block_rh(qtype* src, kvtype* dst, int64_t element_count, int64_t scale_id, quantization_args& args)
{
    int64_t num_chunks = 1;
    if (args.scaling_method == "per_token") {
        num_chunks = args.blocks_num * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        num_chunks = args.head_dim;
    } 
    
    int64_t chunk_size = element_count / num_chunks;

    bool is_per_channel = (args.scaling_method == "per_channel");
    int64_t stride = is_per_channel ? args.head_dim : 1;

#ifdef USE_MULTITHREADING
    {
        std::vector<float> p_scales(static_cast<size_t>(num_chunks));
        std::vector<float> p_zps(static_cast<size_t>(num_chunks));
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
            p_scales[static_cast<size_t>(chunk)] = args.quantize_block_scales[scale_key];
            p_zps[static_cast<size_t>(chunk)] = args.asym ? args.quantize_block_zps[scale_key] : 0.0f;
        }
        int nthreads = (args.num_threads > 0) ? args.num_threads : omp_get_max_threads();
        // dst writes are strided for per_channel; cap to avoid false sharing
        if (is_per_channel) {
            int cl_chunks = std::max(1, 64 / static_cast<int>(sizeof(kvtype)));
            nthreads = std::min(nthreads, std::max(1, static_cast<int>(num_chunks) / cl_chunks));
        }
        #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            int64_t offset = is_per_channel ? chunk : chunk * chunk_size;
            float scale = p_scales[static_cast<size_t>(chunk)];
            float zeropoint = p_zps[static_cast<size_t>(chunk)];
            std::vector<float> local_buf(static_cast<size_t>(chunk_size));
            for (int64_t i = 0; i < chunk_size; ++i)
                local_buf[static_cast<size_t>(i)] = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
            {
                std::vector<float> inv_out(static_cast<size_t>(chunk_size));
                fast_walsh_hadamard_inverse_fused(local_buf.data(), inv_out.data(), chunk_size, args.perm, args.signs);
                std::copy(inv_out.begin(), inv_out.end(), local_buf.begin());
            }
            for (int64_t i = 0; i < chunk_size; ++i)
                dst[i * stride + offset] = static_cast<kvtype>(local_buf[static_cast<size_t>(i)]);
        }
    }
#else
    std::vector<float> transformed_src(static_cast<size_t>(chunk_size));

    for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {

        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
        int64_t offset = is_per_channel ? chunk : chunk * chunk_size;
        float scale = args.quantize_block_scales[scale_key];
        float zeropoint = 0.0f;
        if (args.asym) zeropoint = args.quantize_block_zps[scale_key];

        for (int64_t i = 0; i < chunk_size; ++i) {
            transformed_src[static_cast<size_t>(i)] = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
        }

        {
            std::vector<float> inv_out(static_cast<size_t>(chunk_size));
            fast_walsh_hadamard_inverse_fused(transformed_src.data(), inv_out.data(), chunk_size, args.perm, args.signs);
            std::copy(inv_out.begin(), inv_out.end(), transformed_src.begin());
        }
        for (int64_t i = 0; i < chunk_size; ++i) {
            dst[i * stride + offset] =  static_cast<kvtype>(transformed_src[static_cast<size_t>(i)]);
        }
    }
#endif
}

template<typename kvtype, typename qtype>
void dequantize_block(qtype* src, kvtype* dst, int64_t element_count, int64_t scale_id, quantization_args& args)
{
    int64_t num_chunks = 1;
    if (args.scaling_method == "per_token") {
        num_chunks = args.blocks_num * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        num_chunks = args.head_dim;
    } 
    
    int64_t chunk_size = element_count / num_chunks;

    bool is_per_channel = (args.scaling_method == "per_channel");
    int64_t stride = is_per_channel ? args.head_dim : 1;

#ifdef USE_MULTITHREADING
    {
        std::vector<float> p_scales(static_cast<size_t>(num_chunks));
        std::vector<float> p_zps(static_cast<size_t>(num_chunks));
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
            p_scales[static_cast<size_t>(chunk)] = args.quantize_block_scales[scale_key];
            p_zps[static_cast<size_t>(chunk)] = args.asym ? args.quantize_block_zps[scale_key] : 0.0f;
        }
        int nthreads = (args.num_threads > 0) ? args.num_threads : omp_get_max_threads();
        if (is_per_channel) {
            int cl_chunks = std::max(1, 64 / static_cast<int>(sizeof(kvtype)));
            nthreads = std::min(nthreads, std::max(1, static_cast<int>(num_chunks) / cl_chunks));
        }
        #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            int64_t offset = is_per_channel ? chunk : chunk * chunk_size;
            float scale = p_scales[static_cast<size_t>(chunk)];
            float zeropoint = p_zps[static_cast<size_t>(chunk)];

            if (is_per_channel) {

                for (int64_t i = 0; i < chunk_size; ++i) {
                    dst[i * stride + offset] = static_cast<kvtype>(static_cast<float>(src[i * stride + offset]) * scale + zeropoint);
                }

            } else {

                if constexpr (std::is_same_v<qtype, int8_t>) {

#ifdef __AVX512F__
                    __m512 scale_vec = _mm512_set1_ps(scale);
                    __m512 zero_vec = _mm512_set1_ps(zeropoint);
                    int64_t simd_size = chunk_size - (chunk_size % 16);

                    for (int64_t i = 0; i < simd_size; i += 16) {
                        __m128i data_int8 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(&src[i * stride + offset]));
                        __m512i data_int32 = _mm512_cvtepi8_epi32(data_int8);
                        __m512 data_fp32 = _mm512_cvtepi32_ps(data_int32);
                        __m512 data_scaled = _mm512_mul_ps(data_fp32, scale_vec);
                        data_scaled = _mm512_add_ps(data_scaled, zero_vec);

                        if constexpr (std::is_same_v<kvtype, float>) {
                            _mm512_storeu_ps(&dst[i * stride + offset], data_scaled);
#ifdef __AVX512BF16__
                        } else if constexpr (std::is_same_v<kvtype, __bf16>) {
                            __m256bh packed = _mm512_cvtneps_pbh(data_scaled);
                            _mm256_storeu_si256(reinterpret_cast<__m256i*>(&dst[i * stride + offset]), (__m256i)packed);
#endif
                        } else if constexpr (std::is_same_v<kvtype, _Float16>) {
                            __m256i packed = _mm512_cvtps_ph(data_scaled, _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC);
                            _mm256_storeu_si256(reinterpret_cast<__m256i*>(&dst[i * stride + offset]), packed);
                        } else {
                            static_assert(sizeof(kvtype) == 0, "Unsupported kvtype for dequantization.");
                        }
                    }

                    for (int64_t i = simd_size; i < chunk_size; ++i) {
                        float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                        dst[i * stride + offset] = static_cast<kvtype>(value);
                    }
#elif defined(__AVX2__)
                    __m256 scale_vec = _mm256_set1_ps(scale);
                    __m256 zero_vec = _mm256_set1_ps(zeropoint);
                    int64_t simd_size = chunk_size - (chunk_size % 8);

                    for (int64_t i = 0; i < simd_size; i += 8) {
                        __m128i data_int8 = _mm_loadl_epi64(reinterpret_cast<const __m128i*>(&src[i * stride + offset]));
                        __m256i data_int32 = _mm256_cvtepi8_epi32(data_int8);
                        __m256 data_fp32 = _mm256_cvtepi32_ps(data_int32);
                        __m256 data_scaled = _mm256_mul_ps(data_fp32, scale_vec);
                        data_scaled = _mm256_add_ps(data_scaled, zero_vec);

                        if constexpr (std::is_same_v<kvtype, float>) {
                            _mm256_storeu_ps(&dst[i * stride + offset], data_scaled);
                        } else if constexpr (std::is_same_v<kvtype, _Float16>) {
                            __m128i packed = _mm256_cvtps_ph(data_scaled, _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC);
                            _mm_storeu_si128(reinterpret_cast<__m128i*>(&dst[i * stride + offset]), packed);
                        } else {
                            for (int k = 0; k < 8; ++k) {
                                float value = static_cast<float>(src[(i + k) * stride + offset]) * scale + zeropoint;
                                dst[(i + k) * stride + offset] = static_cast<kvtype>(value);
                            }
                        }
                    }

                    for (int64_t i = simd_size; i < chunk_size; ++i) {
                        float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                        dst[i * stride + offset] = static_cast<kvtype>(value);
                    }
#else
                    for (int64_t i = 0; i < chunk_size; ++i) {
                        float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                        dst[i * stride + offset] = static_cast<kvtype>(value);
                    }
#endif

                } else {
#ifdef __AVX512F__
                    __m512 scale_vec = _mm512_set1_ps(scale);
                    __m512 zero_vec = _mm512_set1_ps(zeropoint);

                    int64_t simd_size = chunk_size - (chunk_size % 16);

                    for (int64_t i = 0; i < simd_size; i += 16) {
                        __m256i data_int16 = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(&src[i * stride + offset]));
                        __m512i data_int32 = _mm512_cvtepi16_epi32(data_int16);
                        __m512 data_fp32 = _mm512_cvtepi32_ps(data_int32);
                        __m512 data_scaled = _mm512_mul_ps(data_fp32, scale_vec);
                        data_scaled = _mm512_add_ps(data_scaled, zero_vec);

                        if constexpr (std::is_same_v<kvtype, float>) {
                            _mm512_storeu_ps(&dst[i * stride + offset], data_scaled);
#ifdef __AVX512BF16__
                        } else if constexpr (std::is_same_v<kvtype, __bf16>) {
                            __m256bh packed = _mm512_cvtneps_pbh(data_scaled);
                            _mm256_storeu_si256(reinterpret_cast<__m256i*>(&dst[i * stride + offset]), (__m256i)packed);
#endif
                        } else if constexpr (std::is_same_v<kvtype, _Float16>) {
                            __m256i packed = _mm512_cvtps_ph(data_scaled, _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC);
                            _mm256_storeu_si256(reinterpret_cast<__m256i*>(&dst[i * stride + offset]), packed);
                        } else {
                            static_assert(sizeof(kvtype) == 0, "Unsupported kvtype for dequantization.");
                        }
                    }

                    for (int64_t i = simd_size; i < chunk_size; ++i) {
                        float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                        dst[i * stride + offset] = static_cast<kvtype>(value);
                    }
#elif defined(__AVX2__)
                    __m256 scale_vec = _mm256_set1_ps(scale);
                    __m256 zero_vec = _mm256_set1_ps(zeropoint);

                    int64_t simd_size = chunk_size - (chunk_size % 8);

                    for (int64_t i = 0; i < simd_size; i += 8) {
                        __m128i data_int16 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(&src[i * stride + offset]));
                        __m256i data_int32 = _mm256_cvtepi16_epi32(data_int16);
                        __m256 data_fp32 = _mm256_cvtepi32_ps(data_int32);
                        __m256 data_scaled = _mm256_mul_ps(data_fp32, scale_vec);
                        data_scaled = _mm256_add_ps(data_scaled, zero_vec);

                        if constexpr (std::is_same_v<kvtype, float>) {
                            _mm256_storeu_ps(&dst[i * stride + offset], data_scaled);
                        } else if constexpr (std::is_same_v<kvtype, _Float16>) {
                            __m128i packed = _mm256_cvtps_ph(data_scaled, _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC);
                            _mm_storeu_si128(reinterpret_cast<__m128i*>(&dst[i * stride + offset]), packed);
                        } else {
                            for (int k = 0; k < 8; ++k) {
                                float value = static_cast<float>(src[(i + k) * stride + offset]) * scale + zeropoint;
                                dst[(i + k) * stride + offset] = static_cast<kvtype>(value);
                            }
                        }
                    }

                    for (int64_t i = simd_size; i < chunk_size; ++i) {
                        float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                        dst[i * stride + offset] = static_cast<kvtype>(value);
                    }
#else
                    for (int64_t i = 0; i < chunk_size; ++i) {
                        float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                        dst[i * stride + offset] = static_cast<kvtype>(value);
                    }
#endif
                }
            }
        }
    }
#else
    for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
        int64_t offset = is_per_channel ? chunk : chunk * chunk_size;
        
        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
        
        float scale = args.quantize_block_scales[scale_key];
        float zeropoint = 0.0f;
        if (args.asym) zeropoint = args.quantize_block_zps[scale_key];

        if (is_per_channel) {

            for (int64_t i = 0; i < chunk_size; ++i) {
                dst[i * stride + offset] = static_cast<kvtype>(static_cast<float>(src[i * stride + offset]) * scale + zeropoint);
            }

        } else {

            if constexpr (std::is_same_v<qtype, int8_t>) {

#ifdef __AVX512F__
                __m512 scale_vec = _mm512_set1_ps(scale);
                __m512 zero_vec = _mm512_set1_ps(zeropoint);
                int64_t simd_size = chunk_size - (chunk_size % 16);

                for (int64_t i = 0; i < simd_size; i += 16) {
                    __m128i data_int8 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(&src[i * stride + offset]));
                    __m512i data_int32 = _mm512_cvtepi8_epi32(data_int8);
                    __m512 data_fp32 = _mm512_cvtepi32_ps(data_int32);
                    __m512 data_scaled = _mm512_mul_ps(data_fp32, scale_vec);
                    data_scaled = _mm512_add_ps(data_scaled, zero_vec);

                    if constexpr (std::is_same_v<kvtype, float>) {
                        _mm512_storeu_ps(&dst[i * stride + offset], data_scaled);
#ifdef __AVX512BF16__
                    } else if constexpr (std::is_same_v<kvtype, __bf16>) {
                        __m256bh packed = _mm512_cvtneps_pbh(data_scaled);
                        _mm256_storeu_si256(reinterpret_cast<__m256i*>(&dst[i * stride + offset]), (__m256i)packed);
#endif
                    } else if constexpr (std::is_same_v<kvtype, _Float16>) {
                        __m256i packed = _mm512_cvtps_ph(data_scaled, _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC);
                        _mm256_storeu_si256(reinterpret_cast<__m256i*>(&dst[i * stride + offset]), packed);
                    } else {
                        static_assert(sizeof(kvtype) == 0, "Unsupported kvtype for dequantization.");
                    }
                }

                for (int64_t i = simd_size; i < chunk_size; ++i) {
                    float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                    dst[i * stride + offset] = static_cast<kvtype>(value);
                }
#elif defined(__AVX2__)
                __m256 scale_vec = _mm256_set1_ps(scale);
                __m256 zero_vec = _mm256_set1_ps(zeropoint);
                int64_t simd_size = chunk_size - (chunk_size % 8);

                for (int64_t i = 0; i < simd_size; i += 8) {
                    __m128i data_int8 = _mm_loadl_epi64(reinterpret_cast<const __m128i*>(&src[i * stride + offset]));
                    __m256i data_int32 = _mm256_cvtepi8_epi32(data_int8);
                    __m256 data_fp32 = _mm256_cvtepi32_ps(data_int32);
                    __m256 data_scaled = _mm256_mul_ps(data_fp32, scale_vec);
                    data_scaled = _mm256_add_ps(data_scaled, zero_vec);

                    if constexpr (std::is_same_v<kvtype, float>) {
                        _mm256_storeu_ps(&dst[i * stride + offset], data_scaled);
                    } else if constexpr (std::is_same_v<kvtype, _Float16>) {
                        __m128i packed = _mm256_cvtps_ph(data_scaled, _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC);
                        _mm_storeu_si128(reinterpret_cast<__m128i*>(&dst[i * stride + offset]), packed);
                    } else {
                        for (int k = 0; k < 8; ++k) {
                            float value = static_cast<float>(src[(i + k) * stride + offset]) * scale + zeropoint;
                            dst[(i + k) * stride + offset] = static_cast<kvtype>(value);
                        }
                    }
                }

                for (int64_t i = simd_size; i < chunk_size; ++i) {
                    float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                    dst[i * stride + offset] = static_cast<kvtype>(value);
                }
#else
                for (int64_t i = 0; i < chunk_size; ++i) {
                    float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                    dst[i * stride + offset] = static_cast<kvtype>(value);
                }
#endif

            } else {
#ifdef __AVX512F__
                __m512 scale_vec = _mm512_set1_ps(scale);
                __m512 zero_vec = _mm512_set1_ps(zeropoint);

                int64_t simd_size = chunk_size - (chunk_size % 16);

                for (int64_t i = 0; i < simd_size; i += 16) {
                    __m256i data_int16 = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(&src[i * stride + offset]));
                    __m512i data_int32 = _mm512_cvtepi16_epi32(data_int16);
                    __m512 data_fp32 = _mm512_cvtepi32_ps(data_int32);
                    __m512 data_scaled = _mm512_mul_ps(data_fp32, scale_vec);
                    data_scaled = _mm512_add_ps(data_scaled, zero_vec);

                    if constexpr (std::is_same_v<kvtype, float>) {
                        _mm512_storeu_ps(&dst[i * stride + offset], data_scaled);
#ifdef __AVX512BF16__
                    } else if constexpr (std::is_same_v<kvtype, __bf16>) {
                        __m256bh packed = _mm512_cvtneps_pbh(data_scaled);
                        _mm256_storeu_si256(reinterpret_cast<__m256i*>(&dst[i * stride + offset]), (__m256i)packed);
#endif
                    } else if constexpr (std::is_same_v<kvtype, _Float16>) {
                        __m256i packed = _mm512_cvtps_ph(data_scaled, _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC);
                        _mm256_storeu_si256(reinterpret_cast<__m256i*>(&dst[i * stride + offset]), packed);
                    } else {
                        static_assert(sizeof(kvtype) == 0, "Unsupported kvtype for dequantization.");
                    }
                }

                for (int64_t i = simd_size; i < chunk_size; ++i) {
                    float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                    dst[i * stride + offset] = static_cast<kvtype>(value);
                }
#elif defined(__AVX2__)
                __m256 scale_vec = _mm256_set1_ps(scale);
                __m256 zero_vec = _mm256_set1_ps(zeropoint);

                int64_t simd_size = chunk_size - (chunk_size % 8);

                for (int64_t i = 0; i < simd_size; i += 8) {
                    __m128i data_int16 = _mm_loadu_si128(reinterpret_cast<const __m128i*>(&src[i * stride + offset]));
                    __m256i data_int32 = _mm256_cvtepi16_epi32(data_int16);
                    __m256 data_fp32 = _mm256_cvtepi32_ps(data_int32);
                    __m256 data_scaled = _mm256_mul_ps(data_fp32, scale_vec);
                    data_scaled = _mm256_add_ps(data_scaled, zero_vec);

                    if constexpr (std::is_same_v<kvtype, float>) {
                        _mm256_storeu_ps(&dst[i * stride + offset], data_scaled);
                    } else if constexpr (std::is_same_v<kvtype, _Float16>) {
                        __m128i packed = _mm256_cvtps_ph(data_scaled, _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC);
                        _mm_storeu_si128(reinterpret_cast<__m128i*>(&dst[i * stride + offset]), packed);
                    } else {
                        for (int k = 0; k < 8; ++k) {
                            float value = static_cast<float>(src[(i + k) * stride + offset]) * scale + zeropoint;
                            dst[(i + k) * stride + offset] = static_cast<kvtype>(value);
                        }
                    }
                }

                for (int64_t i = simd_size; i < chunk_size; ++i) {
                    float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                    dst[i * stride + offset] = static_cast<kvtype>(value);
                }
#else
                for (int64_t i = 0; i < chunk_size; ++i) {
                    float value = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                    dst[i * stride + offset] = static_cast<kvtype>(value);
                }
#endif
            }
        }
    }
#endif
}


// Validate the runtime quantization arguments before dispatching to the
// templated kernels.  The kernels index gather/scatter buffers, shift by
// (qbit-1), and divide element_count by a derived num_chunks with no internal
// checks, so an out-of-contract argument is otherwise UB (OOB / divide-by-zero)
// or a late, opaque throw from the FWHT.
inline void validate_quant_args(int64_t element_count,
                                const quantization_args& args) {
    if (args.qbit < 1 || args.qbit > 16) {
        throw std::invalid_argument(
            "quantization qbit must be in [1, 16]");
    }
    int64_t num_chunks = 1;
    if (args.scaling_method == "per_token") {
        num_chunks = static_cast<int64_t>(args.blocks_num) * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        num_chunks = args.head_dim;
    }
    if (num_chunks <= 0) {
        throw std::invalid_argument(
            "quantization num_chunks must be positive "
            "(check blocks_num/block_size/head_dim)");
    }
    if (element_count % num_chunks != 0) {
        throw std::invalid_argument(
            "element_count must be divisible by num_chunks");
    }
    if (args.rh) {
        int64_t chunk_size = element_count / num_chunks;
        if (chunk_size < 1 || (chunk_size & (chunk_size - 1)) != 0) {
            throw std::invalid_argument(
                "rh (Hadamard) requires chunk_size to be a power of 2");
        }
    }
}


template<typename kvtype, typename qtype>
void quantize_kvcache(kvtype *src, qtype *dst, int64_t element_count, int64_t scale_id, quantization_args& args) {
    validate_quant_args(element_count, args);

    if constexpr (std::is_same_v<qtype, int8_t>) {
        if (args.qbit == 4) {
            std::vector<int8_t> logical(static_cast<size_t>(element_count));
            if (args.rh) {
                quantize_block_rh<kvtype, int8_t>(src, logical.data(), element_count, scale_id, args);
            } else {
                quantize_block<kvtype, int8_t>(src, logical.data(), element_count, scale_id, args);
            }
            q4_detail::pack_buffer(logical.data(), dst, element_count);
            return;
        }
    }

    if (args.rh) {
        quantize_block_rh<kvtype, qtype>(
            src, dst, element_count, scale_id, args);
    } else {
        quantize_block<kvtype, qtype>(
            src,
            dst,
            element_count,
            scale_id,
            args
        );
    }
}

template<typename kvtype, typename qtype>
void dequantize_kvcache(qtype *src, kvtype *dst, int64_t element_count, int64_t scale_id, quantization_args& args) {
    validate_quant_args(element_count, args);

    if constexpr (std::is_same_v<qtype, int8_t>) {
        if (args.qbit == 4) {
            std::vector<int8_t> logical(static_cast<size_t>(element_count));
            q4_detail::unpack_buffer(src, logical.data(), element_count);
            if (args.rh) {
                dequantize_block_rh<kvtype, int8_t>(logical.data(), dst, element_count, scale_id, args);
            } else {
                dequantize_block<kvtype, int8_t>(logical.data(), dst, element_count, scale_id, args);
            }
            return;
        }
    }

    if (args.rh) {
        dequantize_block_rh<kvtype, qtype>(
            src, dst, element_count, scale_id, args);
    } else {
        dequantize_block<kvtype, qtype>(
            src,
            dst,
            element_count,
            scale_id,
            args
        );
    }
}