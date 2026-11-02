// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <limits>
#include <unordered_map>
#include <type_traits>
#include <immintrin.h>
#include <stdexcept>
#include <cstdint>
#include <cstring>

#ifdef USE_MULTITHREADING
#include <omp.h>
#endif


void fast_walsh_hadamard_transform(float* x, int64_t n);

void fast_walsh_hadamard_transform_fused(const float* in, float* out, int64_t n,
                                         const int32_t* perm, const float* signs);

void fast_walsh_hadamard_inverse_fused(const float* in, float* out, int64_t n,
                                       const int32_t* perm, const float* signs);

// Reorder [layers, tokens, head_num*head_dim] to [layers*head_num, tokens, head_dim] (OpenMP strided copy).
template<typename T>
void split_fused_attention_heads_native(const T* src, T* dst, int64_t layers,
                                         int64_t tokens, int64_t head_num,
                                         int64_t head_dim, int num_threads) {
    int64_t hidden = head_num * head_dim;
    int64_t total_units = layers * head_num;
#ifdef USE_MULTITHREADING
    int nthreads = (num_threads > 0) ? num_threads : omp_get_max_threads();
    #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && total_units > 1)
#endif
    for (int64_t nl = 0; nl < total_units; ++nl) {
        int64_t l = nl / head_num;
        int64_t h = nl % head_num;
        const T* src_unit = src + l * tokens * hidden + h * head_dim;
        T* dst_unit = dst + nl * tokens * head_dim;
        for (int64_t t = 0; t < tokens; ++t) {
            std::memcpy(dst_unit + t * head_dim, src_unit + t * hidden, static_cast<size_t>(head_dim) * sizeof(T));
        }
    }
}

// Inverse of split_fused_attention_heads_native: merges
// [layers*head_num, tokens, head_dim] back into [layers, tokens, head_num*head_dim].
template<typename T>
void merge_fused_attention_heads_native(const T* src, T* dst, int64_t layers,
                                         int64_t tokens, int64_t head_num,
                                         int64_t head_dim, int num_threads) {
    int64_t hidden = head_num * head_dim;
    int64_t total_units = layers * head_num;
#ifdef USE_MULTITHREADING
    int nthreads = (num_threads > 0) ? num_threads : omp_get_max_threads();
    #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && total_units > 1)
#endif
    for (int64_t nl = 0; nl < total_units; ++nl) {
        int64_t l = nl / head_num;
        int64_t h = nl % head_num;
        const T* src_unit = src + nl * tokens * head_dim;
        T* dst_unit = dst + l * tokens * hidden + h * head_dim;
        for (int64_t t = 0; t < tokens; ++t) {
            std::memcpy(dst_unit + t * hidden, src_unit + t * head_dim, static_cast<size_t>(head_dim) * sizeof(T));
        }
    }
}

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
        #pragma omp parallel num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        {
            // Per-thread scratch, reused across chunks.
            std::vector<float> local_buf(static_cast<size_t>(chunk_size));
            std::vector<float> fused_out(static_cast<size_t>(chunk_size));
            #pragma omp for schedule(static)
            for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
                int64_t offset = is_per_channel ? chunk : chunk * chunk_size;
                for (int64_t i = 0; i < chunk_size; ++i)
                    local_buf[static_cast<size_t>(i)] = static_cast<float>(src[i * stride + offset]);
                fast_walsh_hadamard_transform_fused(local_buf.data(), fused_out.data(), chunk_size, args.perm, args.signs);
                std::copy(fused_out.begin(), fused_out.end(), local_buf.begin());
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
        }
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
            args.quantize_block_scales[scale_key] = p_scales[static_cast<size_t>(chunk)];
            args.quantize_block_zps[scale_key] = p_zps[static_cast<size_t>(chunk)];
        }
    }
#else
    std::vector<float> transformed_src(static_cast<size_t>(chunk_size));
    std::vector<float> fused_out(static_cast<size_t>(chunk_size));
    for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
        int64_t offset = is_per_channel ? chunk : chunk * chunk_size;

        for (int64_t i = 0; i < chunk_size; ++i) {
            transformed_src[static_cast<size_t>(i)] = static_cast<float>(src[i * stride + offset]);
        }

        fast_walsh_hadamard_transform_fused(transformed_src.data(), fused_out.data(), chunk_size, args.perm, args.signs);
        std::copy(fused_out.begin(), fused_out.end(), transformed_src.begin());

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
        #pragma omp parallel num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        {
            // Per-thread scratch, reused across chunks.
            std::vector<float> local_buf(static_cast<size_t>(chunk_size));
            std::vector<float> inv_out(static_cast<size_t>(chunk_size));
            #pragma omp for schedule(static)
            for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
                int64_t offset = is_per_channel ? chunk : chunk * chunk_size;
                float scale = p_scales[static_cast<size_t>(chunk)];
                float zeropoint = p_zps[static_cast<size_t>(chunk)];
                for (int64_t i = 0; i < chunk_size; ++i)
                    local_buf[static_cast<size_t>(i)] = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
                fast_walsh_hadamard_inverse_fused(local_buf.data(), inv_out.data(), chunk_size, args.perm, args.signs);
                std::copy(inv_out.begin(), inv_out.end(), local_buf.begin());
                for (int64_t i = 0; i < chunk_size; ++i)
                    dst[i * stride + offset] = static_cast<kvtype>(local_buf[static_cast<size_t>(i)]);
            }
        }
    }
#else
    std::vector<float> transformed_src(static_cast<size_t>(chunk_size));
    std::vector<float> inv_out(static_cast<size_t>(chunk_size));

    for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {

        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
        int64_t offset = is_per_channel ? chunk : chunk * chunk_size;
        float scale = args.quantize_block_scales[scale_key];
        float zeropoint = 0.0f;
        if (args.asym) zeropoint = args.quantize_block_zps[scale_key];

        for (int64_t i = 0; i < chunk_size; ++i) {
            transformed_src[static_cast<size_t>(i)] = static_cast<float>(src[i * stride + offset]) * scale + zeropoint;
        }

        fast_walsh_hadamard_inverse_fused(transformed_src.data(), inv_out.data(), chunk_size, args.perm, args.signs);
        std::copy(inv_out.begin(), inv_out.end(), transformed_src.begin());
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

// ---- Mamba opaque-page strided per_channel quantize/dequantize ----
//
// Mamba opaque-page per_channel quantize. Reads src via page addressing
// (page_index = i/rows_per_page, row_in_page = i%rows_per_page,
// addr = page_base + page_index*page_bytes + byte_offset
//      + (row_in_page*row_width + col_offset + c)*elem_size);
// dst is a flat q_data buffer. row_width is the full row width, head_dim is the
// quantized segment width, col_offset is its start column.
template<typename kvtype, typename qtype>
void quantize_block_mamba_page_per_channel(
    uint8_t* page_base, int64_t page_bytes, int64_t byte_offset,
    qtype* dst, int64_t rows_per_page, int64_t total_rows,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    const int64_t num_chunks = head_dim;
    const int64_t num_pages = total_rows / rows_per_page;

    const int64_t qmax_int = (1 << (args.qbit - 1)) - 1;
    const int64_t qmin_int = -(1 << (args.qbit - 1));
    const float qmax_float = static_cast<float>(qmax_int);
    const float qmin_float = static_cast<float>(qmin_int);

    // Nested page/row loops: the running offset resets only at page boundaries, so there is no per-element div/mod.
#ifdef USE_MULTITHREADING
    {
        std::vector<float> p_scales(static_cast<size_t>(num_chunks));
        std::vector<float> p_zps(static_cast<size_t>(num_chunks));
        int nthreads = (args.num_threads > 0) ? args.num_threads : omp_get_max_threads();
        int cl_chunks = std::max(1, 64 / static_cast<int>(sizeof(qtype)));
        nthreads = std::min(nthreads, std::max(1, static_cast<int>(num_chunks) / cl_chunks));
        #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        for (int64_t c = 0; c < num_chunks; ++c) {
            const int64_t col = col_offset + c;
            const kvtype* page_row0 = reinterpret_cast<const kvtype*>(page_base + byte_offset) + col;
            float min_val = static_cast<float>(page_row0[0]);
            float max_val = min_val;
            for (int64_t p = 0; p < num_pages; ++p) {
                const kvtype* page_ptr = reinterpret_cast<const kvtype*>(
                    page_base + p * page_bytes + byte_offset) + col;
                for (int64_t r = 0; r < rows_per_page; ++r) {
                    float v = static_cast<float>(page_ptr[r * row_width]);
                    min_val = std::min(min_val, v);
                    max_val = std::max(max_val, v);
                }
            }
            float scale = 0.0f, zeropoint = 0.0f;
            if (args.asym) {
                scale = (max_val - min_val) / (qmax_float - qmin_float);
                zeropoint = min_val - qmin_float * scale;
            } else {
                scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
            }
            p_scales[static_cast<size_t>(c)] = scale;
            p_zps[static_cast<size_t>(c)] = zeropoint;
            float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;
            qtype* dst_c = dst + c;
            for (int64_t p = 0; p < num_pages; ++p) {
                const kvtype* page_ptr = reinterpret_cast<const kvtype*>(
                    page_base + p * page_bytes + byte_offset) + col;
                qtype* dst_page = dst_c + p * rows_per_page * head_dim;
                for (int64_t r = 0; r < rows_per_page; ++r) {
                    float q_val = std::clamp(std::round((static_cast<float>(page_ptr[r * row_width]) - zeropoint) * inv_scale), qmin_float, qmax_float);
                    dst_page[r * head_dim] = static_cast<qtype>(q_val);
                }
            }
        }
        for (int64_t c = 0; c < num_chunks; ++c) {
            uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(c);
            args.quantize_block_scales[scale_key] = p_scales[static_cast<size_t>(c)];
            args.quantize_block_zps[scale_key] = p_zps[static_cast<size_t>(c)];
        }
    }
#else
    for (int64_t c = 0; c < num_chunks; ++c) {
        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(c);
        const int64_t col = col_offset + c;
        const kvtype* page_row0 = reinterpret_cast<const kvtype*>(page_base + byte_offset) + col;
        float min_val = static_cast<float>(page_row0[0]);
        float max_val = min_val;
        for (int64_t p = 0; p < num_pages; ++p) {
            const kvtype* page_ptr = reinterpret_cast<const kvtype*>(
                page_base + p * page_bytes + byte_offset) + col;
            for (int64_t r = 0; r < rows_per_page; ++r) {
                float v = static_cast<float>(page_ptr[r * row_width]);
                min_val = std::min(min_val, v);
                max_val = std::max(max_val, v);
            }
        }
        float scale = 0.0f, zeropoint = 0.0f;
        if (args.asym) {
            scale = (max_val - min_val) / (qmax_float - qmin_float);
            zeropoint = min_val - qmin_float * scale;
        } else {
            scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
        }
        args.quantize_block_scales[scale_key] = scale;
        args.quantize_block_zps[scale_key] = zeropoint;
        float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;
        qtype* dst_c = dst + c;
        for (int64_t p = 0; p < num_pages; ++p) {
            const kvtype* page_ptr = reinterpret_cast<const kvtype*>(
                page_base + p * page_bytes + byte_offset) + col;
            qtype* dst_page = dst_c + p * rows_per_page * head_dim;
            for (int64_t r = 0; r < rows_per_page; ++r) {
                float q_val = std::clamp(std::round((static_cast<float>(page_ptr[r * row_width]) - zeropoint) * inv_scale), qmin_float, qmax_float);
                dst_page[r * head_dim] = static_cast<qtype>(q_val);
            }
        }
    }
#endif
}

// dequantize_block's per_channel branch, mirrored: reads a flat q_data
// buffer and writes dequantized values directly into the opaque page. See
// quantize_block_mamba_page_per_channel's docstring for row_width/col_offset.
template<typename kvtype, typename qtype>
void dequantize_block_mamba_page_per_channel(
    const qtype* src, uint8_t* page_base, int64_t page_bytes, int64_t byte_offset,
    int64_t rows_per_page, int64_t total_rows,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    const int64_t num_chunks = head_dim;
    const int64_t num_pages = total_rows / rows_per_page;

#ifdef USE_MULTITHREADING
    {
        std::vector<float> p_scales(static_cast<size_t>(num_chunks));
        std::vector<float> p_zps(static_cast<size_t>(num_chunks));
        for (int64_t c = 0; c < num_chunks; ++c) {
            uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(c);
            p_scales[static_cast<size_t>(c)] = args.quantize_block_scales[scale_key];
            p_zps[static_cast<size_t>(c)] = args.asym ? args.quantize_block_zps[scale_key] : 0.0f;
        }
        int nthreads = (args.num_threads > 0) ? args.num_threads : omp_get_max_threads();
        int cl_chunks = std::max(1, 64 / static_cast<int>(sizeof(kvtype)));
        nthreads = std::min(nthreads, std::max(1, static_cast<int>(num_chunks) / cl_chunks));
        #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        for (int64_t c = 0; c < num_chunks; ++c) {
            float scale = p_scales[static_cast<size_t>(c)];
            float zeropoint = p_zps[static_cast<size_t>(c)];
            const int64_t col = col_offset + c;
            const qtype* src_c = src + c;
            for (int64_t p = 0; p < num_pages; ++p) {
                kvtype* page_ptr = reinterpret_cast<kvtype*>(
                    page_base + p * page_bytes + byte_offset) + col;
                const qtype* src_page = src_c + p * rows_per_page * head_dim;
                for (int64_t r = 0; r < rows_per_page; ++r) {
                    float value = static_cast<float>(src_page[r * head_dim]) * scale + zeropoint;
                    page_ptr[r * row_width] = static_cast<kvtype>(value);
                }
            }
        }
    }
#else
    for (int64_t c = 0; c < num_chunks; ++c) {
        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(c);
        float scale = args.quantize_block_scales[scale_key];
        float zeropoint = args.asym ? args.quantize_block_zps[scale_key] : 0.0f;
        const int64_t col = col_offset + c;
        const qtype* src_c = src + c;
        for (int64_t p = 0; p < num_pages; ++p) {
            kvtype* page_ptr = reinterpret_cast<kvtype*>(
                page_base + p * page_bytes + byte_offset) + col;
            const qtype* src_page = src_c + p * rows_per_page * head_dim;
            for (int64_t r = 0; r < rows_per_page; ++r) {
                float value = static_cast<float>(src_page[r * head_dim]) * scale + zeropoint;
                page_ptr[r * row_width] = static_cast<kvtype>(value);
            }
        }
    }
#endif
}

// ---- Mamba opaque-page two-plane per_channel quantize/dequantize ----
//
// Two-plane variant of the page per_channel kernels: the page spans two storage
// regions of plane_bytes each (raw[0], raw[1]). ssm usually straddles the
// boundary; conv always fits in plane 0, so it does not need this variant.
// A channel crosses the boundary at most once per page, so resolve the split
// once and walk two linear runs.
template<typename kvtype, typename Byte, typename Fn>
inline void for_each_two_plane_channel_run(
    Byte* page_base0, Byte* page_base1, int64_t plane_bytes,
    int64_t byte_offset, int64_t row_width, int64_t col,
    int64_t rows_per_page, int64_t num_pages, Fn&& fn
) {
    const int64_t row_bytes = row_width * static_cast<int64_t>(sizeof(kvtype));
    const int64_t channel_offset = byte_offset + col * static_cast<int64_t>(sizeof(kvtype));
    const int64_t rows0 = channel_offset < plane_bytes
        ? std::min(rows_per_page, 1 + (plane_bytes - channel_offset - 1) / row_bytes)
        : 0;
    for (int64_t p = 0; p < num_pages; ++p) {
        if (rows0 > 0) {
            auto* ptr = reinterpret_cast<kvtype*>(
                page_base0 + p * plane_bytes + channel_offset);
            fn(ptr, p, int64_t{0}, rows0);
        }
        if (rows0 < rows_per_page) {
            auto* ptr = reinterpret_cast<kvtype*>(
                page_base1 + p * plane_bytes + channel_offset
                + rows0 * row_bytes - plane_bytes);
            fn(ptr, p, rows0, rows_per_page - rows0);
        }
    }
}

template<typename kvtype, typename qtype>
void quantize_block_mamba_page_per_channel_2plane(
    const uint8_t* page_base0, const uint8_t* page_base1,
    int64_t plane_bytes, int64_t byte_offset,
    qtype* dst, int64_t rows_per_page, int64_t total_rows,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    const int64_t num_chunks = head_dim;
    const int64_t num_pages = total_rows / rows_per_page;
    const int64_t elem_size = static_cast<int64_t>(sizeof(kvtype));

    const int64_t qmax_int = (1 << (args.qbit - 1)) - 1;
    const int64_t qmin_int = -(1 << (args.qbit - 1));
    const float qmax_float = static_cast<float>(qmax_int);
    const float qmin_float = static_cast<float>(qmin_int);

    auto first_value = [&](int64_t col) -> kvtype {
        const int64_t elem_logical = byte_offset + col * elem_size;
        const int64_t plane_index = elem_logical / plane_bytes;
        const int64_t plane_relative_offset = elem_logical % plane_bytes;
        const uint8_t* base = (plane_index == 0) ? page_base0 : page_base1;
        return reinterpret_cast<const kvtype*>(base + plane_relative_offset)[0];
    };

#ifdef USE_MULTITHREADING
    {
        std::vector<float> p_scales(static_cast<size_t>(num_chunks));
        std::vector<float> p_zps(static_cast<size_t>(num_chunks));
        int nthreads = (args.num_threads > 0) ? args.num_threads : omp_get_max_threads();
        int cl_chunks = std::max(1, 64 / static_cast<int>(sizeof(qtype)));
        nthreads = std::min(nthreads, std::max(1, static_cast<int>(num_chunks) / cl_chunks));
        #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        for (int64_t c = 0; c < num_chunks; ++c) {
            const int64_t col = col_offset + c;
            float min_val = static_cast<float>(first_value(col));
            float max_val = min_val;
            for_each_two_plane_channel_run<const kvtype>(
                page_base0, page_base1, plane_bytes, byte_offset,
                row_width, col, rows_per_page, num_pages,
                [&](const kvtype* ptr, int64_t, int64_t, int64_t count) {
                    for (int64_t r = 0; r < count; ++r) {
                        float v = static_cast<float>(ptr[r * row_width]);
                        min_val = std::min(min_val, v);
                        max_val = std::max(max_val, v);
                    }
                });
            float scale = 0.0f, zeropoint = 0.0f;
            if (args.asym) {
                scale = (max_val - min_val) / (qmax_float - qmin_float);
                zeropoint = min_val - qmin_float * scale;
            } else {
                scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
            }
            p_scales[static_cast<size_t>(c)] = scale;
            p_zps[static_cast<size_t>(c)] = zeropoint;
            float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;
            qtype* dst_c = dst + c;
            for_each_two_plane_channel_run<const kvtype>(
                page_base0, page_base1, plane_bytes, byte_offset,
                row_width, col, rows_per_page, num_pages,
                [&](const kvtype* ptr, int64_t p, int64_t start, int64_t count) {
                    qtype* dst_run = dst_c + (p * rows_per_page + start) * head_dim;
                    for (int64_t r = 0; r < count; ++r) {
                        float raw_v = static_cast<float>(ptr[r * row_width]);
                        float q_val = std::clamp(std::round((raw_v - zeropoint) * inv_scale), qmin_float, qmax_float);
                        dst_run[r * head_dim] = static_cast<qtype>(q_val);
                    }
                });
        }
        for (int64_t c = 0; c < num_chunks; ++c) {
            uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(c);
            args.quantize_block_scales[scale_key] = p_scales[static_cast<size_t>(c)];
            args.quantize_block_zps[scale_key] = p_zps[static_cast<size_t>(c)];
        }
    }
#else
    for (int64_t c = 0; c < num_chunks; ++c) {
        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(c);
        const int64_t col = col_offset + c;
        float min_val = static_cast<float>(first_value(col));
        float max_val = min_val;
        for_each_two_plane_channel_run<const kvtype>(
            page_base0, page_base1, plane_bytes, byte_offset,
            row_width, col, rows_per_page, num_pages,
            [&](const kvtype* ptr, int64_t, int64_t, int64_t count) {
                for (int64_t r = 0; r < count; ++r) {
                    float v = static_cast<float>(ptr[r * row_width]);
                    min_val = std::min(min_val, v);
                    max_val = std::max(max_val, v);
                }
            });
        float scale = 0.0f, zeropoint = 0.0f;
        if (args.asym) {
            scale = (max_val - min_val) / (qmax_float - qmin_float);
            zeropoint = min_val - qmin_float * scale;
        } else {
            scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
        }
        args.quantize_block_scales[scale_key] = scale;
        args.quantize_block_zps[scale_key] = zeropoint;
        float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;
        qtype* dst_c = dst + c;
        for_each_two_plane_channel_run<const kvtype>(
            page_base0, page_base1, plane_bytes, byte_offset,
            row_width, col, rows_per_page, num_pages,
            [&](const kvtype* ptr, int64_t p, int64_t start, int64_t count) {
                qtype* dst_run = dst_c + (p * rows_per_page + start) * head_dim;
                for (int64_t r = 0; r < count; ++r) {
                    float raw_v = static_cast<float>(ptr[r * row_width]);
                    float q_val = std::clamp(std::round((raw_v - zeropoint) * inv_scale), qmin_float, qmax_float);
                    dst_run[r * head_dim] = static_cast<qtype>(q_val);
                }
            });
    }
#endif
}

template<typename kvtype, typename qtype>
void dequantize_block_mamba_page_per_channel_2plane(
    const qtype* src, uint8_t* page_base0, uint8_t* page_base1,
    int64_t plane_bytes, int64_t byte_offset,
    int64_t rows_per_page, int64_t total_rows,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    const int64_t num_chunks = head_dim;
    const int64_t num_pages = total_rows / rows_per_page;

#ifdef USE_MULTITHREADING
    {
        std::vector<float> p_scales(static_cast<size_t>(num_chunks));
        std::vector<float> p_zps(static_cast<size_t>(num_chunks));
        for (int64_t c = 0; c < num_chunks; ++c) {
            uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(c);
            p_scales[static_cast<size_t>(c)] = args.quantize_block_scales[scale_key];
            p_zps[static_cast<size_t>(c)] = args.asym ? args.quantize_block_zps[scale_key] : 0.0f;
        }
        int nthreads = (args.num_threads > 0) ? args.num_threads : omp_get_max_threads();
        int cl_chunks = std::max(1, 64 / static_cast<int>(sizeof(kvtype)));
        nthreads = std::min(nthreads, std::max(1, static_cast<int>(num_chunks) / cl_chunks));
        #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        for (int64_t c = 0; c < num_chunks; ++c) {
            float scale = p_scales[static_cast<size_t>(c)];
            float zeropoint = p_zps[static_cast<size_t>(c)];
            const int64_t col = col_offset + c;
            const qtype* src_c = src + c;
            for_each_two_plane_channel_run<kvtype>(
                page_base0, page_base1, plane_bytes, byte_offset,
                row_width, col, rows_per_page, num_pages,
                [&](kvtype* ptr, int64_t p, int64_t start, int64_t count) {
                    const qtype* src_run = src_c + (p * rows_per_page + start) * head_dim;
                    for (int64_t r = 0; r < count; ++r) {
                        float value = static_cast<float>(src_run[r * head_dim]) * scale + zeropoint;
                        ptr[r * row_width] = static_cast<kvtype>(value);
                    }
                });
        }
    }
#else
    for (int64_t c = 0; c < num_chunks; ++c) {
        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(c);
        float scale = args.quantize_block_scales[scale_key];
        float zeropoint = args.asym ? args.quantize_block_zps[scale_key] : 0.0f;
        const int64_t col = col_offset + c;
        const qtype* src_c = src + c;
        for_each_two_plane_channel_run<kvtype>(
            page_base0, page_base1, plane_bytes, byte_offset,
            row_width, col, rows_per_page, num_pages,
            [&](kvtype* ptr, int64_t p, int64_t start, int64_t count) {
                const qtype* src_run = src_c + (p * rows_per_page + start) * head_dim;
                for (int64_t r = 0; r < count; ++r) {
                    float value = static_cast<float>(src_run[r * head_dim]) * scale + zeropoint;
                    ptr[r * row_width] = static_cast<kvtype>(value);
                }
            });
    }
#endif
}

// ---- Mamba opaque-page strided per_token/per_tensor quantize/dequantize ----
//
// per_token/per_tensor chunks are contiguous runs of chunk_size elements that
// need not align to pages, so reads and writes walk logical rows and jump
// page_bytes at each rows_per_page boundary. for_each_row_run(start_row,
// num_rows, fn) calls fn(page_ptr, row_in_page, run_len) once per maximal
// in-page run.
template<typename ElemT, typename Fn>
inline void for_each_row_run(
    ElemT* page_base, int64_t page_bytes, int64_t byte_offset,
    int64_t rows_per_page,
    int64_t start_row, int64_t num_rows, Fn&& fn
) {
    using BytePtr = std::conditional_t<std::is_const_v<ElemT>, const uint8_t*, uint8_t*>;
    int64_t row = start_row;
    int64_t remaining = num_rows;
    while (remaining > 0) {
        const int64_t page_index = row / rows_per_page;
        const int64_t row_in_page = row % rows_per_page;
        const int64_t run_len = std::min(remaining, rows_per_page - row_in_page);
        ElemT* page_ptr = reinterpret_cast<ElemT*>(
            reinterpret_cast<BytePtr>(page_base) + page_index * page_bytes + byte_offset);
        fn(page_ptr, row_in_page, run_len);
        row += run_len;
        remaining -= run_len;
    }
}

// quantize_block's per_token/per_tensor branch (stride=1), reading src via
// mamba page addressing. dst is a flat contiguous buffer, same as
// quantize_block_mamba_page_per_channel.
template<typename kvtype, typename qtype>
void quantize_block_mamba_page_per_token(
    uint8_t* page_base, int64_t page_bytes, int64_t byte_offset,
    qtype* dst, int64_t rows_per_page, int64_t head_dim,
    int64_t num_chunks, int64_t rows_per_chunk,
    int64_t scale_id, quantization_args& args
) {
    const int64_t qmax_int = (1 << (args.qbit - 1)) - 1;
    const int64_t qmin_int = -(1 << (args.qbit - 1));
    const float qmax_float = static_cast<float>(qmax_int);
    const float qmin_float = static_cast<float>(qmin_int);
    const int64_t chunk_elems = rows_per_chunk * head_dim;

#ifdef USE_MULTITHREADING
    {
        std::vector<float> p_scales(static_cast<size_t>(num_chunks));
        std::vector<float> p_zps(static_cast<size_t>(num_chunks));
        int nthreads = (args.num_threads > 0) ? args.num_threads : omp_get_max_threads();
        #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            const int64_t start_row = chunk * rows_per_chunk;
            float min_val = std::numeric_limits<float>::infinity();
            float max_val = -std::numeric_limits<float>::infinity();
            for_each_row_run<const kvtype>(
                reinterpret_cast<const kvtype*>(page_base), page_bytes, byte_offset,
                rows_per_page, start_row, rows_per_chunk,
                [&](const kvtype* page_ptr, int64_t row_in_page, int64_t run_len) {
                    const kvtype* p = page_ptr + row_in_page * head_dim;
                    const int64_t n = run_len * head_dim;
                    for (int64_t i = 0; i < n; ++i) {
                        float v = static_cast<float>(p[i]);
                        min_val = std::min(min_val, v);
                        max_val = std::max(max_val, v);
                    }
                });
            float scale = 0.0f, zeropoint = 0.0f;
            if (args.asym) {
                scale = (max_val - min_val) / (qmax_float - qmin_float);
                zeropoint = min_val - qmin_float * scale;
            } else {
                scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
            }
            p_scales[static_cast<size_t>(chunk)] = scale;
            p_zps[static_cast<size_t>(chunk)] = zeropoint;
            const float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;
            qtype* dst_chunk = dst + chunk * chunk_elems;
            int64_t dst_offset = 0;
            for_each_row_run<const kvtype>(
                reinterpret_cast<const kvtype*>(page_base), page_bytes, byte_offset,
                rows_per_page, start_row, rows_per_chunk,
                [&](const kvtype* page_ptr, int64_t row_in_page, int64_t run_len) {
                    const kvtype* p = page_ptr + row_in_page * head_dim;
                    const int64_t n = run_len * head_dim;
                    for (int64_t i = 0; i < n; ++i) {
                        float q_val = std::clamp(std::round((static_cast<float>(p[i]) - zeropoint) * inv_scale), qmin_float, qmax_float);
                        dst_chunk[dst_offset + i] = static_cast<qtype>(q_val);
                    }
                    dst_offset += n;
                });
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
        const int64_t start_row = chunk * rows_per_chunk;
        float min_val = std::numeric_limits<float>::infinity();
        float max_val = -std::numeric_limits<float>::infinity();
        for_each_row_run<const kvtype>(
            reinterpret_cast<const kvtype*>(page_base), page_bytes, byte_offset,
            rows_per_page, start_row, rows_per_chunk,
            [&](const kvtype* page_ptr, int64_t row_in_page, int64_t run_len) {
                const kvtype* p = page_ptr + row_in_page * head_dim;
                const int64_t n = run_len * head_dim;
                for (int64_t i = 0; i < n; ++i) {
                    float v = static_cast<float>(p[i]);
                    min_val = std::min(min_val, v);
                    max_val = std::max(max_val, v);
                }
            });
        float scale = 0.0f, zeropoint = 0.0f;
        if (args.asym) {
            scale = (max_val - min_val) / (qmax_float - qmin_float);
            zeropoint = min_val - qmin_float * scale;
        } else {
            scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
        }
        args.quantize_block_scales[scale_key] = scale;
        args.quantize_block_zps[scale_key] = zeropoint;
        const float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;
        qtype* dst_chunk = dst + chunk * chunk_elems;
        int64_t dst_offset = 0;
        for_each_row_run<const kvtype>(
            reinterpret_cast<const kvtype*>(page_base), page_bytes, byte_offset,
            rows_per_page, start_row, rows_per_chunk,
            [&](const kvtype* page_ptr, int64_t row_in_page, int64_t run_len) {
                const kvtype* p = page_ptr + row_in_page * head_dim;
                const int64_t n = run_len * head_dim;
                for (int64_t i = 0; i < n; ++i) {
                    float q_val = std::clamp(std::round((static_cast<float>(p[i]) - zeropoint) * inv_scale), qmin_float, qmax_float);
                    dst_chunk[dst_offset + i] = static_cast<qtype>(q_val);
                }
                dst_offset += n;
            });
    }
#endif
}

// dequantize_block's per_token/per_tensor branch, mirrored.
template<typename kvtype, typename qtype>
void dequantize_block_mamba_page_per_token(
    const qtype* src, uint8_t* page_base, int64_t page_bytes, int64_t byte_offset,
    int64_t rows_per_page, int64_t head_dim,
    int64_t num_chunks, int64_t rows_per_chunk,
    int64_t scale_id, quantization_args& args
) {
    const int64_t chunk_elems = rows_per_chunk * head_dim;

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
        #pragma omp parallel for schedule(static) num_threads(nthreads) if(nthreads > 1 && num_chunks > 1)
        for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
            float scale = p_scales[static_cast<size_t>(chunk)];
            float zeropoint = p_zps[static_cast<size_t>(chunk)];
            const int64_t start_row = chunk * rows_per_chunk;
            const qtype* src_chunk = src + chunk * chunk_elems;
            int64_t src_offset = 0;
            for_each_row_run<kvtype>(
                reinterpret_cast<kvtype*>(page_base), page_bytes, byte_offset,
                rows_per_page, start_row, rows_per_chunk,
                [&](kvtype* page_ptr, int64_t row_in_page, int64_t run_len) {
                    kvtype* p = page_ptr + row_in_page * head_dim;
                    const int64_t n = run_len * head_dim;
                    for (int64_t i = 0; i < n; ++i) {
                        float value = static_cast<float>(src_chunk[src_offset + i]) * scale + zeropoint;
                        p[i] = static_cast<kvtype>(value);
                    }
                    src_offset += n;
                });
        }
    }
#else
    for (int64_t chunk = 0; chunk < num_chunks; ++chunk) {
        uint64_t scale_key = (static_cast<uint64_t>(scale_id) << 32) | static_cast<uint64_t>(chunk);
        float scale = args.quantize_block_scales[scale_key];
        float zeropoint = args.asym ? args.quantize_block_zps[scale_key] : 0.0f;
        const int64_t start_row = chunk * rows_per_chunk;
        const qtype* src_chunk = src + chunk * chunk_elems;
        int64_t src_offset = 0;
        for_each_row_run<kvtype>(
            reinterpret_cast<kvtype*>(page_base), page_bytes, byte_offset,
            rows_per_page, start_row, rows_per_chunk,
            [&](kvtype* page_ptr, int64_t row_in_page, int64_t run_len) {
                kvtype* p = page_ptr + row_in_page * head_dim;
                const int64_t n = run_len * head_dim;
                for (int64_t i = 0; i < n; ++i) {
                    float value = static_cast<float>(src_chunk[src_offset + i]) * scale + zeropoint;
                    p[i] = static_cast<kvtype>(value);
                }
                src_offset += n;
            });
    }
#endif
}

// Validate runtime args before dispatch; the kernels do no internal checks (OOB / divide-by-zero otherwise).
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

// Mamba opaque-page analog of quantize_kvcache. Supports per_channel/per_token/
// per_tensor, not rh (callers fall back to the non-direct path). element_count
// is the total over all pages; rows_per_page and head_dim are passed explicitly.
template<typename kvtype, typename qtype>
void quantize_kvcache_mamba_page(
    uint8_t* page_base, int64_t page_bytes, int64_t byte_offset,
    qtype* dst, int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    if (args.rh) {
        throw std::invalid_argument(
            "quantize_kvcache_mamba_page does not support rh=true");
    }
    if (args.scaling_method != "per_channel"
        && args.scaling_method != "per_token"
        && args.scaling_method != "per_tensor") {
        throw std::invalid_argument(
            "quantize_kvcache_mamba_page only supports scaling_method in "
            "{'per_channel', 'per_token', 'per_tensor'}");
    }
    const bool is_per_channel = (args.scaling_method == "per_channel");
    if (!is_per_channel && (row_width != head_dim || col_offset != 0)) {
        throw std::invalid_argument(
            "quantize_kvcache_mamba_page: a row sub-range (row_width != "
            "head_dim or col_offset != 0) is only supported with "
            "scaling_method='per_channel'");
    }
    validate_quant_args(element_count, args);
    const int64_t total_rows = element_count / head_dim;
    const int64_t num_chunks = is_per_channel
        ? head_dim
        : (args.scaling_method == "per_token" ? args.blocks_num * args.block_size : 1);
    const int64_t rows_per_chunk = is_per_channel ? 0 : total_rows / num_chunks;

    if constexpr (std::is_same_v<qtype, int8_t>) {
        if (args.qbit == 4) {
            std::vector<int8_t> logical(static_cast<size_t>(element_count));
            if (is_per_channel) {
                quantize_block_mamba_page_per_channel<kvtype, int8_t>(
                    page_base, page_bytes, byte_offset, logical.data(),
                    rows_per_page, total_rows, row_width, col_offset, head_dim, scale_id, args);
            } else {
                quantize_block_mamba_page_per_token<kvtype, int8_t>(
                    page_base, page_bytes, byte_offset, logical.data(),
                    rows_per_page, head_dim, num_chunks, rows_per_chunk, scale_id, args);
            }
            q4_detail::pack_buffer(logical.data(), dst, element_count);
            return;
        }
    }

    if (is_per_channel) {
        quantize_block_mamba_page_per_channel<kvtype, qtype>(
            page_base, page_bytes, byte_offset, dst,
            rows_per_page, total_rows, row_width, col_offset, head_dim, scale_id, args);
    } else {
        quantize_block_mamba_page_per_token<kvtype, qtype>(
            page_base, page_bytes, byte_offset, dst,
            rows_per_page, head_dim, num_chunks, rows_per_chunk, scale_id, args);
    }
}

// Mamba opaque-page analog of dequantize_kvcache: mirrors
// quantize_kvcache_mamba_page (per_channel/per_token/per_tensor, no RH).
template<typename kvtype, typename qtype>
void dequantize_kvcache_mamba_page(
    qtype* src, uint8_t* page_base, int64_t page_bytes, int64_t byte_offset,
    int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    if (args.rh) {
        throw std::invalid_argument(
            "dequantize_kvcache_mamba_page does not support rh=true");
    }
    if (args.scaling_method != "per_channel"
        && args.scaling_method != "per_token"
        && args.scaling_method != "per_tensor") {
        throw std::invalid_argument(
            "dequantize_kvcache_mamba_page only supports scaling_method in "
            "{'per_channel', 'per_token', 'per_tensor'}");
    }
    const bool is_per_channel = (args.scaling_method == "per_channel");
    if (!is_per_channel && (row_width != head_dim || col_offset != 0)) {
        throw std::invalid_argument(
            "dequantize_kvcache_mamba_page: a row sub-range (row_width != "
            "head_dim or col_offset != 0) is only supported with "
            "scaling_method='per_channel'");
    }
    validate_quant_args(element_count, args);
    const int64_t total_rows = element_count / head_dim;
    const int64_t num_chunks = is_per_channel
        ? head_dim
        : (args.scaling_method == "per_token" ? args.blocks_num * args.block_size : 1);
    const int64_t rows_per_chunk = is_per_channel ? 0 : total_rows / num_chunks;

    if constexpr (std::is_same_v<qtype, int8_t>) {
        if (args.qbit == 4) {
            std::vector<int8_t> logical(static_cast<size_t>(element_count));
            q4_detail::unpack_buffer(src, logical.data(), element_count);
            if (is_per_channel) {
                dequantize_block_mamba_page_per_channel<kvtype, int8_t>(
                    logical.data(), page_base, page_bytes, byte_offset,
                    rows_per_page, total_rows, row_width, col_offset, head_dim, scale_id, args);
            } else {
                dequantize_block_mamba_page_per_token<kvtype, int8_t>(
                    logical.data(), page_base, page_bytes, byte_offset,
                    rows_per_page, head_dim, num_chunks, rows_per_chunk, scale_id, args);
            }
            return;
        }
    }

    if (is_per_channel) {
        dequantize_block_mamba_page_per_channel<kvtype, qtype>(
            src, page_base, page_bytes, byte_offset,
            rows_per_page, total_rows, row_width, col_offset, head_dim, scale_id, args);
    } else {
        dequantize_block_mamba_page_per_token<kvtype, qtype>(
            src, page_base, page_bytes, byte_offset,
            rows_per_page, head_dim, num_chunks, rows_per_chunk, scale_id, args);
    }
}

// Two-plane analog of quantize_kvcache_mamba_page: per_channel only (only ssm needs two-plane addressing).
template<typename kvtype, typename qtype>
void quantize_kvcache_mamba_page_2plane(
    const uint8_t* page_base0, const uint8_t* page_base1,
    int64_t plane_bytes, int64_t page_bytes, int64_t byte_offset,
    qtype* dst, int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    if (args.rh) {
        throw std::invalid_argument(
            "quantize_kvcache_mamba_page_2plane does not support rh=true");
    }
    if (args.scaling_method != "per_channel") {
        throw std::invalid_argument(
            "quantize_kvcache_mamba_page_2plane only supports "
            "scaling_method='per_channel'");
    }
    if (page_bytes != 2 * plane_bytes) {
        throw std::invalid_argument(
            "quantize_kvcache_mamba_page_2plane: page_bytes must equal "
            "2 * plane_bytes");
    }
    validate_quant_args(element_count, args);
    const int64_t total_rows = element_count / head_dim;

    if constexpr (std::is_same_v<qtype, int8_t>) {
        if (args.qbit == 4) {
            std::vector<int8_t> logical(static_cast<size_t>(element_count));
            quantize_block_mamba_page_per_channel_2plane<kvtype, int8_t>(
                page_base0, page_base1, plane_bytes, byte_offset,
                logical.data(), rows_per_page, total_rows, row_width, col_offset,
                head_dim, scale_id, args);
            q4_detail::pack_buffer(logical.data(), dst, element_count);
            return;
        }
    }

    quantize_block_mamba_page_per_channel_2plane<kvtype, qtype>(
        page_base0, page_base1, plane_bytes, byte_offset, dst,
        rows_per_page, total_rows, row_width, col_offset, head_dim, scale_id, args);
}

template<typename kvtype, typename qtype>
void dequantize_kvcache_mamba_page_2plane(
    qtype* src, uint8_t* page_base0, uint8_t* page_base1,
    int64_t plane_bytes, int64_t page_bytes, int64_t byte_offset,
    int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    if (args.rh) {
        throw std::invalid_argument(
            "dequantize_kvcache_mamba_page_2plane does not support rh=true");
    }
    if (args.scaling_method != "per_channel") {
        throw std::invalid_argument(
            "dequantize_kvcache_mamba_page_2plane only supports "
            "scaling_method='per_channel'");
    }
    if (page_bytes != 2 * plane_bytes) {
        throw std::invalid_argument(
            "dequantize_kvcache_mamba_page_2plane: page_bytes must equal "
            "2 * plane_bytes");
    }
    validate_quant_args(element_count, args);
    const int64_t total_rows = element_count / head_dim;

    if constexpr (std::is_same_v<qtype, int8_t>) {
        if (args.qbit == 4) {
            std::vector<int8_t> logical(static_cast<size_t>(element_count));
            q4_detail::unpack_buffer(src, logical.data(), element_count);
            dequantize_block_mamba_page_per_channel_2plane<kvtype, int8_t>(
                logical.data(), page_base0, page_base1, plane_bytes,
                byte_offset, rows_per_page, total_rows, row_width, col_offset,
                head_dim, scale_id, args);
            return;
        }
    }

    dequantize_block_mamba_page_per_channel_2plane<kvtype, qtype>(
        src, page_base0, page_base1, plane_bytes, byte_offset,
        rows_per_page, total_rows, row_width, col_offset, head_dim, scale_id, args);
}

// Quantizes fused-K/V attention [layers, tokens, head_num*head_dim] in place of
// split_fused_attention_heads_native + per-(layer*head) quantize_kvcache.
// Output q bytes and scales are identical to that path; only the access order differs.
struct fused_direct_params {
    int64_t layers = 0;
    int64_t tokens = 0;
    int64_t head_num = 0;
    int64_t head_dim = 0;
    int qbit = 4;
    bool rh = false;
    bool asym = false;
    bool per_channel = true;
    const int32_t* perm = nullptr;
    const float* signs = nullptr;
    int num_threads = 0;
};

namespace fused_direct_detail {

constexpr int64_t kMaxColumnBlock = 32;

inline int64_t column_block(int64_t head_dim) {
    for (int64_t cb = kMaxColumnBlock; cb >= 2; cb >>= 1) {
        if (head_dim % cb == 0) {
            return cb;
        }
    }
    return 1;
}

inline void store_logical(const int8_t* logical, int8_t* unit_dst, int64_t logical_off,
                          int64_t n, int qbit) {
    if (qbit == 4) {
        q4_detail::pack_buffer(logical, unit_dst + logical_off / 2, n);
    } else {
        std::memcpy(unit_dst + logical_off, logical, static_cast<size_t>(n));
    }
}

// Same expressions as quantize_block / quantize_block_rh.
inline void scale_and_zeropoint(float min_val, float max_val, bool asym, float qmin_float,
                                float qmax_float, float& scale, float& zeropoint,
                                bool exact_division = false, [[maybe_unused]] bool rh = false) {
    scale = 0.0f;
    zeropoint = 0.0f;
    if (exact_division) {
        // Match the reference scale arithmetic exactly (avoid reciprocal substitution).
        volatile float denominator = asym ? qmax_float - qmin_float : qmax_float;
        scale = (asym ? max_val - min_val : std::max(std::abs(min_val), std::abs(max_val)))
            / denominator;
#ifdef __INTEL_LLVM_COMPILER
        if (!asym && !rh) {
            volatile float reciprocal = 1.0f / qmax_float;
            scale = std::max(std::abs(min_val), std::abs(max_val)) * reciprocal;
        }
#endif
        if (asym) {
            zeropoint = min_val - qmin_float * scale;
        }
        return;
    }
    if (asym) {
        scale = (max_val - min_val) / (qmax_float - qmin_float);
        zeropoint = min_val - qmin_float * scale;
    } else {
        scale = std::max(std::abs(min_val), std::abs(max_val)) / qmax_float;
    }
}

// One (layer, head) unit, columns [c0, c0+cb): every column is its own scale group over tokens.
template<typename kvtype>
void per_channel_block(const kvtype* unit_src, int64_t row_stride, int64_t c0, int64_t cb,
                       const fused_direct_params& p, float qmin_float, float qmax_float,
                       float* buf, int8_t* qrow, float* scales, float* zps, int8_t* unit_dst,
                       bool exact_division = false) {
    const int64_t tokens = p.tokens;
    const int32_t* perm = p.rh ? p.perm : nullptr;
    const float* signs = p.rh ? p.signs : nullptr;

    for (int64_t t = 0; t < tokens; ++t) {
        const int64_t src_t = perm ? static_cast<int64_t>(perm[t]) : t;
        const kvtype* row = unit_src + src_t * row_stride + c0;
        float* out = buf + t * cb;
        for (int64_t c = 0; c < cb; ++c) {
            out[c] = static_cast<float>(row[c]);
        }
        if (signs) {
            const float s = signs[t];
            for (int64_t c = 0; c < cb; ++c) {
                out[c] *= s;
            }
        }
    }

    if (p.rh) {
        for (int64_t h = 1; h < tokens; h <<= 1) {
            for (int64_t i = 0; i < tokens; i += h << 1) {
                for (int64_t j = i; j < i + h; ++j) {
                    float* __restrict a = buf + j * cb;
                    float* __restrict b = buf + (j + h) * cb;
                    for (int64_t c = 0; c < cb; ++c) {
                        const float x = a[c];
                        const float y = b[c];
                        a[c] = x + y;
                        b[c] = x - y;
                    }
                }
            }
        }
        const float inv_sqrt_n = 1.0f / std::sqrt(static_cast<float>(tokens));
        for (int64_t i = 0; i < tokens * cb; ++i) {
            buf[i] *= inv_sqrt_n;
        }
    }

    float min_vals[kMaxColumnBlock];
    float max_vals[kMaxColumnBlock];
    float zero_points[kMaxColumnBlock];
    float inv_scales[kMaxColumnBlock];
    for (int64_t c = 0; c < cb; ++c) {
        min_vals[c] = buf[c];
        max_vals[c] = buf[c];
    }
    for (int64_t t = 0; t < tokens; ++t) {
        const float* row = buf + t * cb;
        for (int64_t c = 0; c < cb; ++c) {
            min_vals[c] = std::min(min_vals[c], row[c]);
            max_vals[c] = std::max(max_vals[c], row[c]);
        }
    }
    for (int64_t c = 0; c < cb; ++c) {
        float scale = 0.0f;
        float zeropoint = 0.0f;
        scale_and_zeropoint(min_vals[c], max_vals[c], p.asym, qmin_float, qmax_float,
                            scale, zeropoint, exact_division, p.rh);
        scales[c0 + c] = scale;
        zps[c0 + c] = zeropoint;
        zero_points[c] = zeropoint;
        inv_scales[c] = (scale != 0.0f) ? (1.0f / scale) : 0.0f;
    }

    for (int64_t t = 0; t < tokens; ++t) {
        const float* row = buf + t * cb;
        for (int64_t c = 0; c < cb; ++c) {
            const float q_val = std::clamp(
                std::round((row[c] - zero_points[c]) * inv_scales[c]), qmin_float, qmax_float);
            qrow[c] = static_cast<int8_t>(q_val);
        }
        store_logical(qrow, unit_dst, t * p.head_dim + c0, cb, p.qbit);
    }
}

// One (layer, token) row across all heads: each head's head_dim slice is its own scale group.
template<typename kvtype>
void per_token_row(const kvtype* row_src, int64_t layer, int64_t token,
                   const fused_direct_params& p, float qmin_float, float qmax_float,
                   float* local_buf, float* fused_out, int8_t* qrow, float* scales,
                   float* zps, int8_t* q_dst, int64_t unit_q_bytes) {
    const int64_t head_dim = p.head_dim;
    for (int64_t h = 0; h < p.head_num; ++h) {
        const kvtype* src = row_src + h * head_dim;
        for (int64_t i = 0; i < head_dim; ++i) {
            local_buf[i] = static_cast<float>(src[i]);
        }
        const float* vals = local_buf;
        if (p.rh) {
            fast_walsh_hadamard_transform_fused(local_buf, fused_out, head_dim, p.perm, p.signs);
            vals = fused_out;
        }
        float min_val = vals[0];
        float max_val = vals[0];
        for (int64_t i = 0; i < head_dim; ++i) {
            min_val = std::min(min_val, vals[i]);
            max_val = std::max(max_val, vals[i]);
        }
        float scale = 0.0f;
        float zeropoint = 0.0f;
        scale_and_zeropoint(min_val, max_val, p.asym, qmin_float, qmax_float, scale, zeropoint);
        const int64_t unit = layer * p.head_num + h;
        scales[unit * p.tokens + token] = scale;
        zps[unit * p.tokens + token] = zeropoint;
        const float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;
        for (int64_t i = 0; i < head_dim; ++i) {
            const float q_val = std::clamp(
                std::round((vals[i] - zeropoint) * inv_scale), qmin_float, qmax_float);
            qrow[i] = static_cast<int8_t>(q_val);
        }
        store_logical(qrow, q_dst + unit * unit_q_bytes, token * head_dim, head_dim, p.qbit);
    }
}

} // namespace fused_direct_detail

// Page boundaries may split a row; the two physical planes are not adjacent.
struct mamba_page_params {
    int64_t page_bytes;
    int64_t byte_offset;
    int64_t rows_per_page;
    int64_t total_rows;
    int64_t head_dim;
    int64_t row_width;
    int64_t col_offset;
    int64_t rows_per_layer;
};

template<bool read>
inline void copy_mamba_page_run(
    uint8_t* page0, uint8_t* page1, uint8_t* buffer,
    int64_t page, int64_t offset, int64_t bytes, int64_t page_bytes
) {
    const int64_t plane_bytes = page1 ? page_bytes / 2 : page_bytes;
    uint8_t* first;
    int64_t first_bytes = bytes;
    if (page1 && offset >= plane_bytes) {
        first = page1 + page * plane_bytes + offset - plane_bytes;
    } else {
        first = page0 + page * plane_bytes + offset;
        if (page1) {
            first_bytes = std::min(bytes, plane_bytes - offset);
        }
    }
    if constexpr (read) {
        std::memcpy(buffer, first, static_cast<size_t>(first_bytes));
        if (first_bytes < bytes) {
            std::memcpy(buffer + first_bytes, page1 + page * plane_bytes,
                        static_cast<size_t>(bytes - first_bytes));
        }
    } else {
        std::memcpy(first, buffer, static_cast<size_t>(first_bytes));
        if (first_bytes < bytes) {
            std::memcpy(page1 + page * plane_bytes, buffer + first_bytes,
                        static_cast<size_t>(bytes - first_bytes));
        }
    }
}

template<typename kvtype, bool quantize>
void mamba_page_per_token(
    uint8_t* page0, uint8_t* page1, int8_t* q_data,
    float* scales, float* zps, const mamba_page_params& p,
    const quantization_args& args
) {
    const int64_t row_bytes = p.head_dim * static_cast<int64_t>(sizeof(kvtype));
    const int64_t q_row_bytes = args.qbit == 4 ? p.head_dim / 2 : p.head_dim;
    const float qmin = -static_cast<float>(1 << (args.qbit - 1));
    const float qmax = static_cast<float>((1 << (args.qbit - 1)) - 1);
#ifdef USE_MULTITHREADING
    const int nthreads = args.num_threads > 0 ? args.num_threads : omp_get_max_threads();
    #pragma omp parallel num_threads(nthreads) if(nthreads > 1 && p.total_rows > 1)
#endif
    {
        std::vector<kvtype> row(static_cast<size_t>(p.head_dim));
        std::vector<float> values(static_cast<size_t>(p.head_dim));
        std::vector<float> transformed(quantize ? static_cast<size_t>(p.head_dim) : 0);
        std::vector<int8_t> logical(static_cast<size_t>(p.head_dim));
#ifdef USE_MULTITHREADING
        #pragma omp for schedule(static)
#endif
        for (int64_t r = 0; r < p.total_rows; ++r) {
            const int64_t page = r / p.rows_per_page;
            const int64_t offset = p.byte_offset
                + ((r % p.rows_per_page) * p.row_width + p.col_offset)
                    * static_cast<int64_t>(sizeof(kvtype));
            auto* row_data = reinterpret_cast<uint8_t*>(row.data());
            int8_t* q_row = q_data + r * q_row_bytes;
            if constexpr (quantize) {
                copy_mamba_page_run<true>(
                    page0, page1, row_data, page, offset, row_bytes, p.page_bytes);
                for (int64_t i = 0; i < p.head_dim; ++i) {
                    values[static_cast<size_t>(i)] = static_cast<float>(row[static_cast<size_t>(i)]);
                }
                const float* vals = values.data();
                if (args.rh) {
                    fast_walsh_hadamard_transform_fused(
                        values.data(), transformed.data(), p.head_dim, args.perm, args.signs);
                    vals = transformed.data();
                }
                float min_val = vals[0], max_val = vals[0];
                for (int64_t i = 0; i < p.head_dim; ++i) {
                    const float value = vals[i];
                    min_val = std::min(min_val, value);
                    max_val = std::max(max_val, value);
                }
                float scale, zp;
                fused_direct_detail::scale_and_zeropoint(
                    min_val, max_val, args.asym, qmin, qmax, scale, zp, !args.rh, args.rh);
                scales[r] = scale;
                zps[r] = zp;
                const float inv_scale = scale != 0.0f ? 1.0f / scale : 0.0f;
                for (int64_t i = 0; i < p.head_dim; ++i) {
                    logical[static_cast<size_t>(i)] = static_cast<int8_t>(std::clamp(
                        std::round((vals[i] - zp) * inv_scale),
                        qmin, qmax));
                }
                fused_direct_detail::store_logical(
                    logical.data(), q_row, 0, p.head_dim, args.qbit);
            } else {
                const float scale = scales[r];
                const float zp = args.asym ? zps[r] : 0.0f;
                if (!args.rh) {
                    if (args.qbit == 4) {
                        q4_detail::unpack_buffer(q_row, logical.data(), p.head_dim);
                    } else {
                        std::memcpy(logical.data(), q_row, static_cast<size_t>(p.head_dim));
                    }
                    int64_t i = 0;
                    // Match dequantize_block's SIMD prefix and scalar tail.
#if defined(__AVX512F__)
                    if constexpr (!std::is_same_v<kvtype, __bf16>
#ifdef __AVX512BF16__
                                  || std::is_same_v<kvtype, __bf16>
#endif
                    ) {
                        for (; i + 16 <= p.head_dim; i += 16) {
                            const __m128i q = _mm_loadu_si128(
                                reinterpret_cast<const __m128i*>(logical.data() + i));
                            const __m512 v = _mm512_add_ps(
                                _mm512_mul_ps(_mm512_cvtepi32_ps(_mm512_cvtepi8_epi32(q)),
                                              _mm512_set1_ps(scale)), _mm512_set1_ps(zp));
                            if constexpr (std::is_same_v<kvtype, float>) {
                                _mm512_storeu_ps(row.data() + i, v);
                            } else if constexpr (std::is_same_v<kvtype, _Float16>) {
                                _mm256_storeu_si256(reinterpret_cast<__m256i*>(row.data() + i),
                                    _mm512_cvtps_ph(v, _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC));
#ifdef __AVX512BF16__
                            } else {
                                _mm256_storeu_si256(reinterpret_cast<__m256i*>(row.data() + i),
                                                    (__m256i)_mm512_cvtneps_pbh(v));
#endif
                            }
                        }
                    }
#elif defined(__AVX2__)
                    if constexpr (!std::is_same_v<kvtype, __bf16>) {
                        for (; i + 8 <= p.head_dim; i += 8) {
                            const __m128i q = _mm_loadl_epi64(
                                reinterpret_cast<const __m128i*>(logical.data() + i));
                            const __m256 v = _mm256_add_ps(
                                _mm256_mul_ps(_mm256_cvtepi32_ps(_mm256_cvtepi8_epi32(q)),
                                              _mm256_set1_ps(scale)), _mm256_set1_ps(zp));
                            if constexpr (std::is_same_v<kvtype, float>) {
                                _mm256_storeu_ps(row.data() + i, v);
                            } else {
                                _mm_storeu_si128(reinterpret_cast<__m128i*>(row.data() + i),
                                    _mm256_cvtps_ph(v, _MM_FROUND_TO_NEAREST_INT | _MM_FROUND_NO_EXC));
                            }
                        }
                    }
#endif
                    for (; i < p.head_dim; ++i) {
                        row[static_cast<size_t>(i)] = static_cast<kvtype>(
                            static_cast<float>(logical[static_cast<size_t>(i)]) * scale + zp);
                    }
                } else {
                    for (int64_t i = 0; i < p.head_dim; ++i) {
                        const int8_t q = args.qbit == 4
                            ? q4_detail::unpack_value(q_row, i) : q_row[i];
#ifdef __FMA__
                        // Match dequantize_block_rh's contracted multiply/add.
                        values[static_cast<size_t>(i)] = std::fma(static_cast<float>(q), scale, zp);
#else
                        values[static_cast<size_t>(i)] =
                            static_cast<float>(q) * scale + zp;
#endif
                    }
                    // Same H, D, P^T as the reference inverse, with no per-row temporary.
                    fast_walsh_hadamard_transform(values.data(), p.head_dim);
                    for (int64_t i = 0; i < p.head_dim; ++i) {
                        row[static_cast<size_t>(args.perm[i])] = static_cast<kvtype>(
                            values[static_cast<size_t>(i)] * args.signs[i]);
                    }
                }
                copy_mamba_page_run<false>(
                    page0, page1, row_data, page, offset, row_bytes, p.page_bytes);
            }
        }
    }
}

// q_dst: units*unit_q_bytes; scales/zps: [layers*head_num, nchunks] with
// nchunks = head_dim (per_channel) or tokens (per_token).
template<typename kvtype>
void quantize_fused_direct(const kvtype* src, int8_t* q_dst, float* scales, float* zps,
                           const fused_direct_params& p) {
    using namespace fused_direct_detail;
    const int64_t tokens = p.tokens;
    const int64_t head_num = p.head_num;
    const int64_t head_dim = p.head_dim;
    const int64_t hidden = head_num * head_dim;
    const int64_t unit_elems = tokens * head_dim;
    const int64_t unit_q_bytes = (p.qbit == 4) ? unit_elems / 2 : unit_elems;
    const int64_t qmax_int = (1 << (p.qbit - 1)) - 1;
    const int64_t qmin_int = -(1 << (p.qbit - 1));
    const float qmax_float = static_cast<float>(qmax_int);
    const float qmin_float = static_cast<float>(qmin_int);
#ifdef USE_MULTITHREADING
    const int nthreads = (p.num_threads > 0) ? p.num_threads : omp_get_max_threads();
#endif

    if (p.per_channel) {
        const int64_t cb = column_block(head_dim);
        const int64_t blocks_per_unit = head_dim / cb;
        const int64_t tasks = p.layers * head_num * blocks_per_unit;
#ifdef USE_MULTITHREADING
        #pragma omp parallel num_threads(nthreads) if(nthreads > 1 && tasks > 1)
#endif
        {
            std::vector<float> buf(static_cast<size_t>(tokens * cb));
            std::vector<int8_t> qrow(static_cast<size_t>(cb));
#ifdef USE_MULTITHREADING
            #pragma omp for schedule(static)
#endif
            for (int64_t task = 0; task < tasks; ++task) {
                const int64_t unit = task / blocks_per_unit;
                const int64_t c0 = (task % blocks_per_unit) * cb;
                const int64_t layer = unit / head_num;
                const int64_t h = unit % head_num;
                per_channel_block<kvtype>(
                    src + layer * tokens * hidden + h * head_dim, hidden, c0, cb, p,
                    qmin_float, qmax_float, buf.data(), qrow.data(),
                    scales + unit * head_dim, zps + unit * head_dim,
                    q_dst + unit * unit_q_bytes);
            }
        }
        return;
    }

    const int64_t rows = p.layers * tokens;
#ifdef USE_MULTITHREADING
    #pragma omp parallel num_threads(nthreads) if(nthreads > 1 && rows > 1)
#endif
    {
        std::vector<float> local_buf(static_cast<size_t>(head_dim));
        std::vector<float> fused_out(static_cast<size_t>(head_dim));
        std::vector<int8_t> qrow(static_cast<size_t>(head_dim));
#ifdef USE_MULTITHREADING
        #pragma omp for schedule(static)
#endif
        for (int64_t r = 0; r < rows; ++r) {
            const int64_t layer = r / tokens;
            const int64_t token = r % tokens;
            per_token_row<kvtype>(
                src + r * hidden, layer, token, p, qmin_float, qmax_float,
                local_buf.data(), fused_out.data(), qrow.data(), scales, zps,
                q_dst, unit_q_bytes);
        }
    }
}

namespace fused_direct_detail {

inline void load_logical(const int8_t* unit_q, int64_t logical_off, int64_t n, int qbit,
                         int8_t* logical) {
    if (qbit == 4) {
        q4_detail::unpack_buffer(unit_q + logical_off / 2, logical, n);
    } else {
        std::memcpy(logical, unit_q + logical_off, static_cast<size_t>(n));
    }
}

// Inverse of per_channel_block: dequantize columns [c0, c0+cb) of one unit and
// write them straight into the fused [tokens, row_stride] destination.
template<typename kvtype>
void dequant_per_channel_block(const int8_t* unit_q, kvtype* unit_dst, int64_t row_stride,
                               int64_t c0, int64_t cb, const fused_direct_params& p,
                               const float* scales, const float* zps, float* buf,
                               int8_t* qrow) {
    const int64_t tokens = p.tokens;
    const int32_t* perm = p.rh ? p.perm : nullptr;
    const float* signs = p.rh ? p.signs : nullptr;
    float col_scale[kMaxColumnBlock];
    float col_zp[kMaxColumnBlock];
    for (int64_t c = 0; c < cb; ++c) {
        col_scale[c] = scales[c0 + c];
        col_zp[c] = p.asym ? zps[c0 + c] : 0.0f;
    }
    for (int64_t t = 0; t < tokens; ++t) {
        load_logical(unit_q, t * p.head_dim + c0, cb, p.qbit, qrow);
        float* row = buf + t * cb;
        for (int64_t c = 0; c < cb; ++c) {
            row[c] = static_cast<float>(qrow[c]) * col_scale[c] + col_zp[c];
        }
    }

    if (p.rh) {
        for (int64_t h = 1; h < tokens; h <<= 1) {
            for (int64_t i = 0; i < tokens; i += h << 1) {
                for (int64_t j = i; j < i + h; ++j) {
                    float* __restrict a = buf + j * cb;
                    float* __restrict b = buf + (j + h) * cb;
                    for (int64_t c = 0; c < cb; ++c) {
                        const float x = a[c];
                        const float y = b[c];
                        a[c] = x + y;
                        b[c] = x - y;
                    }
                }
            }
        }
        const float inv_sqrt_n = 1.0f / std::sqrt(static_cast<float>(tokens));
        for (int64_t i = 0; i < tokens * cb; ++i) {
            buf[i] *= inv_sqrt_n;
        }
    }

    // Forward gathered row perm[t] into slot t; the inverse scatters slot t back.
    for (int64_t t = 0; t < tokens; ++t) {
        const int64_t dst_t = perm ? static_cast<int64_t>(perm[t]) : t;
        const float s = signs ? signs[t] : 1.0f;
        const float* row = buf + t * cb;
        kvtype* out = unit_dst + dst_t * row_stride + c0;
        for (int64_t c = 0; c < cb; ++c) {
            out[c] = static_cast<kvtype>(row[c] * s);
        }
    }
}

// Inverse of per_token_row for one (layer, token) row across all heads.
template<typename kvtype>
void dequant_per_token_row(const int8_t* q_src, kvtype* row_dst, int64_t layer, int64_t token,
                           const fused_direct_params& p, const float* scales,
                           const float* zps, int64_t unit_q_bytes, float* buf,
                           float* restored, int8_t* qrow) {
    const int64_t head_dim = p.head_dim;
    const int32_t* perm = p.rh ? p.perm : nullptr;
    const float* signs = p.rh ? p.signs : nullptr;
    for (int64_t h = 0; h < p.head_num; ++h) {
        const int64_t unit = layer * p.head_num + h;
        load_logical(q_src + unit * unit_q_bytes, token * head_dim, head_dim, p.qbit, qrow);
        const float scale = scales[unit * p.tokens + token];
        const float zp = p.asym ? zps[unit * p.tokens + token] : 0.0f;
        for (int64_t i = 0; i < head_dim; ++i) {
            buf[i] = static_cast<float>(qrow[i]) * scale + zp;
        }
        kvtype* __restrict out = row_dst + h * head_dim;
        const float* vals = buf;
        if (p.rh) {
            fast_walsh_hadamard_transform(buf, head_dim);
            if (signs) {
                for (int64_t i = 0; i < head_dim; ++i) {
                    buf[i] *= signs[i];
                }
            }
            // Undo the permutation in fp32 so the narrowing store stays contiguous.
            if (perm) {
                for (int64_t i = 0; i < head_dim; ++i) {
                    restored[perm[i]] = buf[i];
                }
                vals = restored;
            }
        }
        for (int64_t i = 0; i < head_dim; ++i) {
            out[i] = static_cast<kvtype>(vals[i]);
        }
    }
}

} // namespace fused_direct_detail

template<typename kvtype, bool quantize>
void mamba_page_per_channel(
    uint8_t* page0, uint8_t* page1, int8_t* q_data,
    float* scales, float* zps, const mamba_page_params& p,
    const quantization_args& args
) {
    using namespace fused_direct_detail;
    const int64_t cb = column_block(p.head_dim);
    const int64_t tiles_per_layer = p.head_dim / cb;
    const int64_t layers = p.total_rows / p.rows_per_layer;
    const int64_t units = layers * tiles_per_layer;
    const int64_t tile_elems = p.rows_per_layer * cb;
    const int64_t tile_q_bytes = args.qbit == 4 ? tile_elems / 2 : tile_elems;
    const int64_t layer_q_bytes = args.qbit == 4
        ? p.rows_per_layer * p.head_dim / 2 : p.rows_per_layer * p.head_dim;
    const float qmin = -static_cast<float>(1 << (args.qbit - 1));
    const float qmax = static_cast<float>((1 << (args.qbit - 1)) - 1);
    fused_direct_params tile_params;
    tile_params.tokens = p.rows_per_layer;
    tile_params.head_dim = cb;
    tile_params.qbit = args.qbit;
    tile_params.rh = args.rh;
    tile_params.asym = args.asym;
    tile_params.perm = args.perm;
    tile_params.signs = args.signs;
#ifdef USE_MULTITHREADING
    const int nthreads = args.num_threads > 0 ? args.num_threads : omp_get_max_threads();
    #pragma omp parallel num_threads(nthreads) if(nthreads > 1 && units > 1)
#endif
    {
        std::vector<kvtype> tile(static_cast<size_t>(tile_elems));
        std::vector<float> buffer(static_cast<size_t>(tile_elems));
        std::vector<int8_t> tile_q(static_cast<size_t>(tile_q_bytes));
        std::vector<int8_t> logical(static_cast<size_t>(cb));
        float tile_scales[kMaxColumnBlock];
        float tile_zps[kMaxColumnBlock];
#ifdef USE_MULTITHREADING
        #pragma omp for schedule(static)
#endif
        for (int64_t unit = 0; unit < units; ++unit) {
            const int64_t layer = unit / tiles_per_layer;
            const int64_t c0 = (unit % tiles_per_layer) * cb;
            int8_t* layer_q = q_data + layer * layer_q_bytes;
            for (int64_t t = 0; t < p.rows_per_layer; ++t) {
                const int64_t r = layer * p.rows_per_layer + t;
                const int64_t page = r / p.rows_per_page;
                const int64_t offset = p.byte_offset
                    + ((r % p.rows_per_page) * p.row_width + p.col_offset + c0)
                        * static_cast<int64_t>(sizeof(kvtype));
                if constexpr (quantize) {
                    copy_mamba_page_run<true>(
                        page0, page1, reinterpret_cast<uint8_t*>(tile.data() + t * cb),
                        page, offset, cb * static_cast<int64_t>(sizeof(kvtype)), p.page_bytes);
                } else {
                    load_logical(layer_q, t * p.head_dim + c0, cb, args.qbit, logical.data());
                    store_logical(logical.data(), tile_q.data(), t * cb, cb, args.qbit);
                }
            }
            if constexpr (quantize) {
                per_channel_block(
                    tile.data(), cb, 0, cb, tile_params, qmin, qmax, buffer.data(),
                    logical.data(), tile_scales, tile_zps, tile_q.data(), true);
                for (int64_t c = 0; c < cb; ++c) {
                    scales[layer * p.head_dim + c0 + c] = tile_scales[c];
                    zps[layer * p.head_dim + c0 + c] = tile_zps[c];
                }
            } else {
                dequant_per_channel_block(
                    tile_q.data(), tile.data(), cb, 0, cb, tile_params,
                    scales + layer * p.head_dim + c0, zps + layer * p.head_dim + c0,
                    buffer.data(), logical.data());
            }
            for (int64_t t = 0; t < p.rows_per_layer; ++t) {
                if constexpr (quantize) {
                    load_logical(tile_q.data(), t * cb, cb, args.qbit, logical.data());
                    store_logical(logical.data(), layer_q, t * p.head_dim + c0, cb, args.qbit);
                } else {
                    const int64_t r = layer * p.rows_per_layer + t;
                    const int64_t offset = p.byte_offset
                        + ((r % p.rows_per_page) * p.row_width + p.col_offset + c0)
                            * static_cast<int64_t>(sizeof(kvtype));
                    copy_mamba_page_run<false>(
                        page0, page1, reinterpret_cast<uint8_t*>(tile.data() + t * cb),
                        r / p.rows_per_page, offset,
                        cb * static_cast<int64_t>(sizeof(kvtype)), p.page_bytes);
                }
            }
        }
    }
}

// Inverse of quantize_fused_direct: q_src/scales/zps use the same per-unit
// layout, dst is the fused [layers, tokens, head_num*head_dim] tensor.
template<typename kvtype>
void dequantize_fused_direct(const int8_t* q_src, kvtype* dst, const float* scales,
                             const float* zps, const fused_direct_params& p) {
    using namespace fused_direct_detail;
    const int64_t tokens = p.tokens;
    const int64_t head_num = p.head_num;
    const int64_t head_dim = p.head_dim;
    const int64_t hidden = head_num * head_dim;
    const int64_t unit_elems = tokens * head_dim;
    const int64_t unit_q_bytes = (p.qbit == 4) ? unit_elems / 2 : unit_elems;
#ifdef USE_MULTITHREADING
    const int nthreads = (p.num_threads > 0) ? p.num_threads : omp_get_max_threads();
#endif

    if (p.per_channel) {
        const int64_t cb = column_block(head_dim);
        const int64_t blocks_per_unit = head_dim / cb;
        const int64_t tasks = p.layers * head_num * blocks_per_unit;
#ifdef USE_MULTITHREADING
        #pragma omp parallel num_threads(nthreads) if(nthreads > 1 && tasks > 1)
#endif
        {
            std::vector<float> buf(static_cast<size_t>(tokens * cb));
            std::vector<int8_t> qrow(static_cast<size_t>(cb));
#ifdef USE_MULTITHREADING
            #pragma omp for schedule(static)
#endif
            for (int64_t task = 0; task < tasks; ++task) {
                const int64_t unit = task / blocks_per_unit;
                const int64_t c0 = (task % blocks_per_unit) * cb;
                const int64_t layer = unit / head_num;
                const int64_t h = unit % head_num;
                dequant_per_channel_block<kvtype>(
                    q_src + unit * unit_q_bytes, dst + layer * tokens * hidden + h * head_dim,
                    hidden, c0, cb, p, scales + unit * head_dim, zps + unit * head_dim,
                    buf.data(), qrow.data());
            }
        }
        return;
    }

    const int64_t rows = p.layers * tokens;
#ifdef USE_MULTITHREADING
    #pragma omp parallel num_threads(nthreads) if(nthreads > 1 && rows > 1)
#endif
    {
        std::vector<float> buf(static_cast<size_t>(head_dim));
        std::vector<float> restored(static_cast<size_t>(head_dim));
        std::vector<int8_t> qrow(static_cast<size_t>(head_dim));
#ifdef USE_MULTITHREADING
        #pragma omp for schedule(static)
#endif
        for (int64_t r = 0; r < rows; ++r) {
            dequant_per_token_row<kvtype>(
                q_src, dst + r * hidden, r / tokens, r % tokens, p, scales, zps,
                unit_q_bytes, buf.data(), restored.data(), qrow.data());
        }
    }
}