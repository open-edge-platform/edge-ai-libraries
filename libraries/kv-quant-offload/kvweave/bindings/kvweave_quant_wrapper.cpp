// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <torch/extension.h>
#include <algorithm>
#include <exception>
#include <mutex>
#include <stdexcept>
#include <cstring>

#ifdef USE_MULTITHREADING
#include <omp.h>
#endif

#include "quant.h"

#ifndef KVWEAVE_BUILD_COMPILER
#define KVWEAVE_BUILD_COMPILER "unknown"
#endif

#ifndef KVWEAVE_BUILD_ISA
#define KVWEAVE_BUILD_ISA "unknown"
#endif

#ifndef KVWEAVE_BUILD_MULTITHREAD
#define KVWEAVE_BUILD_MULTITHREAD 0
#endif

namespace {

#ifdef USE_MULTITHREADING
void ensure_nested_openmp_for_fused_halves(int requested_threads) {
    if (requested_threads < 2) {
        return;
    }

    static std::once_flag omp_nested_once;
    std::call_once(omp_nested_once, []() {
        omp_set_nested(1);
        omp_set_max_active_levels(2);
    });
}
#endif

void ensure_cpu_tensor(const torch::Tensor& tensor, const char* name) {
    if (!tensor.device().is_cpu()) {
        throw std::invalid_argument(std::string(name) + " tensor must reside on CPU.");
    }
}

void copy_mamba_page_substate(
    uint8_t* page0,
    uint8_t* page1,
    uint8_t* contiguous,
    int64_t page_bytes,
    int64_t byte_offset,
    int64_t row_width,
    int64_t rows_per_page,
    int64_t head_dim,
    int64_t col_offset,
    int64_t layers,
    int64_t blocks,
    int64_t elem_size,
    bool is_two_plane,
    bool gather
) {
    const int64_t plane_bytes = is_two_plane ? page_bytes / 2 : page_bytes;
    const int64_t total_pages = layers * blocks;
    for (int64_t page = 0; page < total_pages; ++page) {
        for (int64_t row = 0; row < rows_per_page; ++row) {
            int64_t page_offset = byte_offset
                + (row * row_width + col_offset) * elem_size;
            int64_t copied_bytes = 0;
            const int64_t row_bytes = head_dim * elem_size;
            while (copied_bytes < row_bytes) {
                const int64_t current_offset = page_offset + copied_bytes;
                const bool second_plane =
                    is_two_plane && current_offset >= plane_bytes;
                const int64_t plane_offset =
                    second_plane ? current_offset - plane_bytes : current_offset;
                const int64_t boundary = is_two_plane && !second_plane
                    ? plane_bytes
                    : page_bytes;
                const int64_t copy_bytes = std::min(
                    row_bytes - copied_bytes, boundary - current_offset);
                uint8_t* page_base = is_two_plane
                    ? (second_plane ? page1 : page0) + page * plane_bytes
                    : page0 + page * page_bytes;
                uint8_t* page_address = page_base + plane_offset;
                uint8_t* linear_address = contiguous
                    + (page * rows_per_page + row) * row_bytes + copied_bytes;
                if (gather) {
                    std::memcpy(
                        linear_address, page_address,
                        static_cast<size_t>(copy_bytes));
                } else {
                    std::memcpy(
                        page_address, linear_address,
                        static_cast<size_t>(copy_bytes));
                }
                copied_bytes += copy_bytes;
            }
        }
    }
}

void set_mamba_rh_vectors(
    quantization_args& args,
    torch::Tensor& signs,
    torch::Tensor& perm,
    int64_t elements_per_layer
) {
    if (signs.scalar_type() != torch::kFloat32
        || perm.scalar_type() != torch::kInt32) {
        throw std::invalid_argument(
            "RH signs must be float32 and perm must be int32.");
    }
    validate_quant_args(elements_per_layer, args);
    int64_t chunks = 1;
    if (args.scaling_method == "per_token") {
        chunks = static_cast<int64_t>(args.blocks_num) * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        chunks = args.head_dim;
    }
    const int64_t transform_size = elements_per_layer / chunks;
    if (signs.numel() != transform_size || perm.numel() != transform_size) {
        throw std::invalid_argument(
            "RH signs and perm lengths must match the transform size.");
    }
    args.signs = signs.data_ptr<float>();
    args.perm = perm.data_ptr<int32_t>();
}

quantization_args build_quant_args(
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    bool rh,
    bool asym,
    const std::string& scaling_method
) {
    quantization_args args;
    args.qbit = qbit;
    args.blocks_num = blocks_num;
    args.block_size = block_size;
    args.head_num = head_num;
    args.head_dim = head_dim;
    args.rh = rh;
    args.asym = asym;
    args.scaling_method = scaling_method;
    return args;
}

int64_t logical_numel_from_layout(
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim
) {
    return static_cast<int64_t>(blocks_num) * block_size * head_num * head_dim;
}

int64_t quantized_numel_for_qbit(int64_t logical_numel, int qbit) {
    if (qbit == 4) {
        return q4_detail::packed_size(logical_numel);
    }
    return logical_numel;
}

template <typename KVType, typename QType>
void run_quantize_kernel(torch::Tensor& src, torch::Tensor& dst, int64_t scale_id, quantization_args& args) {
    auto* src_ptr = reinterpret_cast<KVType*>(src.data_ptr());
    auto* dst_ptr = reinterpret_cast<QType*>(dst.data_ptr());
    int64_t numel = src.numel();
    quantize_kvcache<KVType, QType>(src_ptr, dst_ptr, numel, scale_id, args);
}

template <typename KVType, typename QType>
void run_quantize(torch::Tensor& src, torch::Tensor& dst, int64_t scale_id, quantization_args& args) {
    // Ensure contiguous storage before raw-pointer casts
    src = src.contiguous();
    dst = dst.contiguous();
    // Release the GIL via PyEval_SaveThread/RestoreThread (avoids pybind11's decref_pyobject).
    Py_BEGIN_ALLOW_THREADS
    run_quantize_kernel<KVType, QType>(src, dst, scale_id, args);
    Py_END_ALLOW_THREADS
}

template <typename KVType, typename QType>
void run_dequantize_kernel(torch::Tensor& src, torch::Tensor& dst, int64_t scale_id, quantization_args& args) {
    auto* src_ptr = reinterpret_cast<QType*>(src.data_ptr());
    auto* dst_ptr = reinterpret_cast<KVType*>(dst.data_ptr());
    int64_t numel = dst.numel();
    dequantize_kvcache<KVType, QType>(src_ptr, dst_ptr, numel, scale_id, args);
}

template <typename KVType, typename QType>
void run_dequantize(torch::Tensor& src, torch::Tensor& dst, int64_t scale_id, quantization_args& args) {
    src = src.contiguous();
    dst = dst.contiguous();
    // Release GIL for kernel
    Py_BEGIN_ALLOW_THREADS
    run_dequantize_kernel<KVType, QType>(src, dst, scale_id, args);
    Py_END_ALLOW_THREADS
}

void dispatch_quantization(
    torch::Tensor& src,
    torch::Tensor& dst,
    int64_t scale_id,
    quantization_args& args
) {
    const auto src_type = src.scalar_type();
    const auto dst_type = dst.scalar_type();

    if (dst_type == torch::kInt8) {
        if (src_type == torch::kFloat32) {
            run_quantize<float, int8_t>(src, dst, scale_id, args);
        } else if (src_type == torch::kFloat16) {
            run_quantize<_Float16, int8_t>(src, dst, scale_id, args);
        } else if (src_type == torch::kBFloat16) {
            run_quantize<__bf16, int8_t>(src, dst, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported src dtype for quantization (int8 destination).");
        }
    } else if (dst_type == torch::kInt16) {
        if (src_type == torch::kFloat32) {
            run_quantize<float, int16_t>(src, dst, scale_id, args);
        } else if (src_type == torch::kFloat16) {
            run_quantize<_Float16, int16_t>(src, dst, scale_id, args);
        } else if (src_type == torch::kBFloat16) {
            run_quantize<__bf16, int16_t>(src, dst, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported src dtype for quantization (int16 destination).");
        }
    } else {
        throw std::invalid_argument("Destination dtype must be int8 or int16 for quantization.");
    }
}

void dispatch_quantization_kernel(
    torch::Tensor& src,
    torch::Tensor& dst,
    int64_t scale_id,
    quantization_args& args
) {
    const auto src_type = src.scalar_type();
    const auto dst_type = dst.scalar_type();

    if (dst_type == torch::kInt8) {
        if (src_type == torch::kFloat32) {
            run_quantize_kernel<float, int8_t>(src, dst, scale_id, args);
        } else if (src_type == torch::kFloat16) {
            run_quantize_kernel<_Float16, int8_t>(src, dst, scale_id, args);
        } else if (src_type == torch::kBFloat16) {
            run_quantize_kernel<__bf16, int8_t>(src, dst, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported src dtype for quantization (int8 destination).");
        }
    } else if (dst_type == torch::kInt16) {
        if (src_type == torch::kFloat32) {
            run_quantize_kernel<float, int16_t>(src, dst, scale_id, args);
        } else if (src_type == torch::kFloat16) {
            run_quantize_kernel<_Float16, int16_t>(src, dst, scale_id, args);
        } else if (src_type == torch::kBFloat16) {
            run_quantize_kernel<__bf16, int16_t>(src, dst, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported src dtype for quantization (int16 destination).");
        }
    } else {
        throw std::invalid_argument("Destination dtype must be int8 or int16 for quantization.");
    }
}

void dispatch_dequantization(
    torch::Tensor& src,
    torch::Tensor& dst,
    int64_t scale_id,
    quantization_args& args
) {
    const auto src_type = src.scalar_type();
    const auto dst_type = dst.scalar_type();

    if (src_type == torch::kInt8) {
        if (dst_type == torch::kFloat32) {
            run_dequantize<float, int8_t>(src, dst, scale_id, args);
        } else if (dst_type == torch::kFloat16) {
            run_dequantize<_Float16, int8_t>(src, dst, scale_id, args);
        } else if (dst_type == torch::kBFloat16) {
            run_dequantize<__bf16, int8_t>(src, dst, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported destination dtype for int8 source.");
        }
    } else if (src_type == torch::kInt16) {
        if (dst_type == torch::kFloat32) {
            run_dequantize<float, int16_t>(src, dst, scale_id, args);
        } else if (dst_type == torch::kFloat16) {
            run_dequantize<_Float16, int16_t>(src, dst, scale_id, args);
        } else if (dst_type == torch::kBFloat16) {
            run_dequantize<__bf16, int16_t>(src, dst, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported destination dtype for int16 source.");
        }
    } else {
        throw std::invalid_argument("Source dtype must be int8 or int16 for dequantization.");
    }
}

void dispatch_dequantization_kernel(
    torch::Tensor& src,
    torch::Tensor& dst,
    int64_t scale_id,
    quantization_args& args
) {
    const auto src_type = src.scalar_type();
    const auto dst_type = dst.scalar_type();

    if (src_type == torch::kInt8) {
        if (dst_type == torch::kFloat32) {
            run_dequantize_kernel<float, int8_t>(src, dst, scale_id, args);
        } else if (dst_type == torch::kFloat16) {
            run_dequantize_kernel<_Float16, int8_t>(src, dst, scale_id, args);
        } else if (dst_type == torch::kBFloat16) {
            run_dequantize_kernel<__bf16, int8_t>(src, dst, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported destination dtype for int8 source.");
        }
    } else if (src_type == torch::kInt16) {
        if (dst_type == torch::kFloat32) {
            run_dequantize_kernel<float, int16_t>(src, dst, scale_id, args);
        } else if (dst_type == torch::kFloat16) {
            run_dequantize_kernel<_Float16, int16_t>(src, dst, scale_id, args);
        } else if (dst_type == torch::kBFloat16) {
            run_dequantize_kernel<__bf16, int16_t>(src, dst, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported destination dtype for int16 source.");
        }
    } else {
        throw std::invalid_argument("Source dtype must be int8 or int16 for dequantization.");
    }
}

}  // namespace

// ---- Helpers to access thread-local scale maps from C++ ----

static std::string pack_mamba_dense_scales(
    const std::vector<float>& scales, const std::vector<float>& zps,
    int64_t layers, int64_t rows_per_layer
) {
    constexpr size_t entry_bytes = sizeof(uint32_t) + 2 * sizeof(float);
    const size_t layer_bytes = sizeof(uint32_t)
        + static_cast<size_t>(rows_per_layer) * entry_bytes;
    std::string blob(static_cast<size_t>(layers) * layer_bytes, '\0');
    char* cursor = blob.data();
    const auto count = static_cast<uint32_t>(rows_per_layer);
    for (int64_t layer = 0; layer < layers; ++layer) {
        std::memcpy(cursor, &count, sizeof(count));
        cursor += sizeof(count);
        for (uint32_t row = 0; row < count; ++row) {
            const size_t pos = static_cast<size_t>(layer * rows_per_layer + row);
            std::memcpy(cursor, &row, sizeof(row)); cursor += sizeof(row);
            std::memcpy(cursor, &scales[pos], sizeof(float)); cursor += sizeof(float);
            std::memcpy(cursor, &zps[pos], sizeof(float)); cursor += sizeof(float);
        }
    }
    return blob;
}

static void unpack_mamba_dense_scales(
    const std::string& blob, int64_t layers, int64_t rows_per_layer,
    std::vector<float>& scales, std::vector<float>& zps
) {
    constexpr size_t entry_bytes = sizeof(uint32_t) + 2 * sizeof(float);
    const size_t layer_bytes = sizeof(uint32_t)
        + static_cast<size_t>(rows_per_layer) * entry_bytes;
    if (blob.size() != static_cast<size_t>(layers) * layer_bytes) {
        throw std::invalid_argument("Mamba scale blob has an invalid size.");
    }
    std::vector<bool> seen(static_cast<size_t>(rows_per_layer));
    const char* cursor = blob.data();
    for (int64_t layer = 0; layer < layers; ++layer) {
        uint32_t count;
        std::memcpy(&count, cursor, sizeof(count)); cursor += sizeof(count);
        if (count != rows_per_layer) {
            throw std::invalid_argument("Mamba scale count does not match scale groups.");
        }
        std::fill(seen.begin(), seen.end(), false);
        for (uint32_t entry = 0; entry < count; ++entry) {
            uint32_t row;
            std::memcpy(&row, cursor, sizeof(row)); cursor += sizeof(row);
            if (row >= count || seen[row]) {
                throw std::invalid_argument("Mamba scale index is invalid or repeated.");
            }
            seen[row] = true;
            const size_t pos = static_cast<size_t>(layer * rows_per_layer + row);
            std::memcpy(&scales[pos], cursor, sizeof(float)); cursor += sizeof(float);
            std::memcpy(&zps[pos], cursor, sizeof(float)); cursor += sizeof(float);
        }
    }
}

static bool uses_mamba_fused_scaling(
    const quantization_args& args, int64_t numel_per_layer,
    int64_t row_width, int64_t col_offset, torch::ScalarType dtype
) {
    if ((args.qbit != 4 && args.qbit != 8) || args.head_dim < 1
        || (args.qbit == 4 && args.head_dim % 2 != 0)
        || col_offset < 0 || col_offset + args.head_dim > row_width
        || (dtype != torch::kFloat32 && dtype != torch::kFloat16 && dtype != torch::kBFloat16)) {
        return false;
    }
    if (args.scaling_method == "per_channel") {
        return numel_per_layer % args.head_dim == 0;
    }
    return args.scaling_method == "per_token"
        && numel_per_layer
            == static_cast<int64_t>(args.blocks_num) * args.block_size * args.head_dim;
}

template<typename T, bool quantize>
static void run_mamba_fused_scaling(
    uint8_t* page0, uint8_t* page1, int8_t* q_data, float* scales, float* zps,
    const mamba_page_params& p, const quantization_args& args
) {
    if (args.scaling_method == "per_channel") {
        mamba_page_per_channel<T, quantize>(page0, page1, q_data, scales, zps, p, args);
    } else {
        mamba_page_per_token<T, quantize>(page0, page1, q_data, scales, zps, p, args);
    }
}

template<bool quantize>
static void dispatch_mamba_fused_scaling(
    torch::ScalarType dtype, uint8_t* page0, uint8_t* page1,
    torch::Tensor& q_data, std::vector<float>& scales, std::vector<float>& zps,
    const mamba_page_params& p, const quantization_args& args
) {
    pybind11::gil_scoped_release release;
    if (dtype == torch::kFloat32) {
        run_mamba_fused_scaling<float, quantize>(
            page0, page1, q_data.data_ptr<int8_t>(), scales.data(), zps.data(), p, args);
    } else if (dtype == torch::kFloat16) {
        run_mamba_fused_scaling<_Float16, quantize>(
            page0, page1, q_data.data_ptr<int8_t>(), scales.data(), zps.data(), p, args);
    } else {
        run_mamba_fused_scaling<__bf16, quantize>(
            page0, page1, q_data.data_ptr<int8_t>(), scales.data(), zps.data(), p, args);
    }
}

// Serialize scale/zeropoint entries for scale_id from the calling thread's TLS maps.
// Must be called from the SAME thread that called quantize_kvcache with scale_id.
static std::string get_scales_bytes_for_id(int64_t scale_id) {
    const auto& scales_map = quantization_args::tls_map_wrapper::data;
    const auto& zps_map    = quantization_args::tls_map_wrapper_zps::data;

    std::vector<std::tuple<uint32_t, float, float>> entries;
    entries.reserve(128);
    for (const auto& [key, scale] : scales_map) {
        if (static_cast<int64_t>(key >> 32) == scale_id) {
            uint32_t chunk_idx = static_cast<uint32_t>(key & 0xFFFFFFFFu);
            float zp = 0.0f;
            auto it = zps_map.find(key);
            if (it != zps_map.end()) zp = it->second;
            entries.emplace_back(chunk_idx, scale, zp);
        }
    }

    uint32_t count = static_cast<uint32_t>(entries.size());
    constexpr size_t entry_size = sizeof(uint32_t) + 2 * sizeof(float);
    std::string buf;
    buf.resize(sizeof(uint32_t) + count * entry_size);
    char* ptr = buf.data();
    std::memcpy(ptr, &count, sizeof(uint32_t)); ptr += sizeof(uint32_t);
    for (auto& [idx, s, z] : entries) {
        std::memcpy(ptr, &idx, sizeof(uint32_t)); ptr += sizeof(uint32_t);
        std::memcpy(ptr, &s,   sizeof(float));    ptr += sizeof(float);
        std::memcpy(ptr, &z,   sizeof(float));    ptr += sizeof(float);
    }
    return buf;
}

static void clear_scales_for_id_impl(int64_t scale_id) {
    auto& scales_map = quantization_args::tls_map_wrapper::data;
    auto& zps_map    = quantization_args::tls_map_wrapper_zps::data;
    for (auto it = scales_map.begin(); it != scales_map.end(); ) {
        if (static_cast<int64_t>(it->first >> 32) == scale_id)
            it = scales_map.erase(it);
        else ++it;
    }
    for (auto it = zps_map.begin(); it != zps_map.end(); ) {
        if (static_cast<int64_t>(it->first >> 32) == scale_id)
            it = zps_map.erase(it);
        else ++it;
    }
}

static void set_scales_for_id_impl(int64_t scale_id, const std::string& buf) {
    auto& scales_map = quantization_args::tls_map_wrapper::data;
    auto& zps_map    = quantization_args::tls_map_wrapper_zps::data;

    const char* ptr = buf.data();
    const char* end = ptr + buf.size();

    if (static_cast<size_t>(end - ptr) < sizeof(uint32_t)) {
        throw std::invalid_argument("Scale blob is too small.");
    }

    uint32_t count = 0;
    std::memcpy(&count, ptr, sizeof(uint32_t)); ptr += sizeof(uint32_t);

    constexpr size_t entry_size = sizeof(uint32_t) + 2 * sizeof(float);
    if (static_cast<size_t>(end - ptr) < static_cast<size_t>(count) * entry_size) {
        throw std::invalid_argument("Scale blob is truncated.");
    }

    for (uint32_t i = 0; i < count; ++i) {
        uint32_t chunk_idx = 0;
        float scale = 0.0f, zp = 0.0f;
        std::memcpy(&chunk_idx, ptr, sizeof(uint32_t)); ptr += sizeof(uint32_t);
        std::memcpy(&scale,     ptr, sizeof(float));    ptr += sizeof(float);
        std::memcpy(&zp,        ptr, sizeof(float));    ptr += sizeof(float);

        uint64_t new_key = (static_cast<uint64_t>(scale_id) << 32) | chunk_idx;
        scales_map[new_key] = scale;
        zps_map[new_key]    = zp;
    }
}

class ScaleIdGuard {
public:
    ScaleIdGuard(int64_t scale_id, const std::string& data) : scale_id_(scale_id) {
        set_scales_for_id_impl(scale_id_, data);
    }

    ~ScaleIdGuard() {
        clear_scales_for_id_impl(scale_id_);
    }

    ScaleIdGuard(const ScaleIdGuard&) = delete;
    ScaleIdGuard& operator=(const ScaleIdGuard&) = delete;

private:
    int64_t scale_id_;
};

class ClearScaleIdGuard {
public:
    explicit ClearScaleIdGuard(int64_t scale_id) : scale_id_(scale_id) {}

    ~ClearScaleIdGuard() {
        clear_scales_for_id_impl(scale_id_);
    }

    ClearScaleIdGuard(const ClearScaleIdGuard&) = delete;
    ClearScaleIdGuard& operator=(const ClearScaleIdGuard&) = delete;

private:
    int64_t scale_id_;
};

static std::vector<std::string> split_scale_blob(const std::string& blob, int64_t num_layers) {
    std::vector<std::string> parts;
    parts.reserve(static_cast<size_t>(num_layers));
    size_t offset = 0;
    for (int64_t i = 0; i < num_layers; ++i) {
        if (offset + sizeof(uint32_t) > blob.size()) {
            throw std::invalid_argument("scale blob too short for split");
        }
        uint32_t count;
        std::memcpy(&count, blob.data() + offset, sizeof(uint32_t));
        constexpr size_t entry_size = sizeof(uint32_t) + 2 * sizeof(float);
        size_t blob_size = sizeof(uint32_t) + count * entry_size;
        parts.emplace_back(blob.data() + offset, blob_size);
        offset += blob_size;
    }
    return parts;
}

static std::string quantize_one_half_per_layer(
    torch::Tensor& src,
    torch::Tensor& dst,
    int64_t base_scale_id,
    int64_t num_layers,
    quantization_args args
) {
    int64_t layer_numel = src.numel() / num_layers;
    int64_t layer_q_numel = dst.numel() / num_layers;
    std::string all_scales;
    for (int64_t l = 0; l < num_layers; ++l) {
        auto layer_src = torch::from_blob(
            static_cast<char*>(src.data_ptr()) + l * layer_numel * src.element_size(),
            {layer_numel}, src.options()
        );
        auto layer_dst = torch::from_blob(
            static_cast<char*>(dst.data_ptr()) + l * layer_q_numel * dst.element_size(),
            {layer_q_numel}, dst.options()
        );
        int64_t scale_id = base_scale_id + l;
        ClearScaleIdGuard scales(scale_id);
        dispatch_quantization_kernel(layer_src, layer_dst, scale_id, args);
        all_scales += get_scales_bytes_for_id(scale_id);
    }
    return all_scales;
}

static void dequantize_one_half_per_layer(
    torch::Tensor& src,
    torch::Tensor& dst,
    int64_t scale_id,
    const std::vector<std::string>& layer_scales,
    int64_t num_layers,
    quantization_args args,
    int layer_num_threads = 1
) {
    int64_t layer_q_numel = src.numel() / num_layers;
    int64_t layer_numel = dst.numel() / num_layers;
#ifdef USE_MULTITHREADING
    const int outer_threads = std::max(1, std::min(layer_num_threads, static_cast<int>(num_layers)));
    #pragma omp parallel for schedule(static) num_threads(outer_threads) if(outer_threads > 1 && num_layers > 1)
#endif
    for (int64_t l = 0; l < num_layers; ++l) {
        auto layer_src = torch::from_blob(
            static_cast<char*>(src.data_ptr()) + l * layer_q_numel * src.element_size(),
            {layer_q_numel}, src.options()
        );
        auto layer_dst = torch::from_blob(
            static_cast<char*>(dst.data_ptr()) + l * layer_numel * dst.element_size(),
            {layer_numel}, dst.options()
        );
        quantization_args layer_args = args;
        ScaleIdGuard guard(scale_id, layer_scales[static_cast<size_t>(l)]);
        dispatch_dequantization_kernel(layer_src, layer_dst, scale_id, layer_args);
    }
}

static void dequantize_one_half(
    torch::Tensor& src,
    torch::Tensor& dst,
    int64_t scale_id,
    const std::string& scale_bytes,
    quantization_args args
) {
    ScaleIdGuard scales(scale_id, scale_bytes);
    dispatch_dequantization_kernel(src, dst, scale_id, args);
}

static std::string quantize_one_half(
    torch::Tensor& src,
    torch::Tensor& dst,
    int64_t scale_id,
    quantization_args args
) {
    ClearScaleIdGuard scales(scale_id);
    dispatch_quantization_kernel(src, dst, scale_id, args);
    return get_scales_bytes_for_id(scale_id);
}

static bool use_per_layer_quantization(
    int64_t num_layers,
    const std::string& scaling_method
) {
    if (num_layers <= 1) {
        return false;
    }
    return (
        scaling_method == "per_token"
        || scaling_method == "per_channel"
        || scaling_method == "per_tensor"
    );
}

// -----------------------------------------------------------------------

torch::Tensor quantize_kvcache_py(
    torch::Tensor src,
    int64_t scale_id,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads = 0
) {
    ensure_cpu_tensor(src, "src");
    auto src_contig = src.contiguous();
    auto dst_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    torch::Tensor dst;
    if (qbit == 4) {
        dst = torch::empty({q4_detail::packed_size(src_contig.numel())}, src_contig.options().dtype(dst_dtype));
    } else {
        dst = torch::empty_like(src_contig, src_contig.options().dtype(dst_dtype));
    }

    auto args = build_quant_args(qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;  // 0 = use omp_get_max_threads() (standalone); set >0 from lmcache

    // Handle optional preconditioning tensors
    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    dispatch_quantization(src_contig, dst, scale_id, args);
    return dst;
}

torch::Tensor dequantize_kvcache_py(
    torch::Tensor src,
    int64_t scale_id,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    torch::ScalarType output_dtype,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads = 0
) {
    ensure_cpu_tensor(src, "src");
    auto src_contig = src.contiguous();
    torch::Tensor dst;
    if (qbit == 4) {
        int64_t logical_numel = logical_numel_from_layout(blocks_num, block_size, head_num, head_dim);
        dst = torch::empty({logical_numel}, src_contig.options().dtype(output_dtype));
    } else {
        dst = torch::empty(src_contig.sizes(), src_contig.options().dtype(output_dtype));
    }

    auto args = build_quant_args(qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;  // 0 = use omp_get_max_threads() (standalone); set >0 from lmcache

    // Handle optional preconditioning tensors
    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    dispatch_dequantization(src_contig, dst, scale_id, args);
    return dst;
}

// Fused dequantization of a layerwise K/V chunk.
torch::Tensor kvweave_dequantize_chunk_py(
    torch::Tensor q_data,
    pybind11::bytes k_scale_bytes,
    pybind11::bytes v_scale_bytes,
    int64_t num_layers,
    int64_t chunk_tokens,
    int64_t h_merged,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    torch::ScalarType output_dtype,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads = 0
) {
    ensure_cpu_tensor(q_data, "q_data");
    auto q_contig = q_data.contiguous();

    auto q_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    if (q_contig.scalar_type() != q_dtype) {
        throw std::invalid_argument("q_data dtype does not match qbit.");
    }

    int64_t half_numel = num_layers * chunk_tokens * h_merged;
    int64_t half_q_numel = quantized_numel_for_qbit(half_numel, qbit);
    int64_t expected_numel = 2 * half_q_numel;
    if (q_contig.numel() < expected_numel) {
        throw std::invalid_argument("q_data is smaller than expected for K/V payload.");
    }

    auto result = torch::empty(
        {2, num_layers, chunk_tokens, h_merged},
        q_contig.options().dtype(output_dtype)
    );

    auto q_k = torch::from_blob(
        q_contig.data_ptr(), {half_q_numel}, q_contig.options()
    );
    auto q_v = torch::from_blob(
        static_cast<char*>(q_contig.data_ptr()) + half_q_numel * q_contig.element_size(),
        {half_q_numel}, q_contig.options()
    );
    auto out_k = torch::from_blob(
        result.data_ptr(), {half_numel}, result.options()
    );
    auto out_v = torch::from_blob(
        static_cast<char*>(result.data_ptr()) + half_numel * result.element_size(),
        {half_numel}, result.options()
    );

    const bool per_layer_quant = use_per_layer_quantization(
        num_layers, scaling_method
    );
    const int effective_blocks_num = blocks_num;

    auto args = build_quant_args(qbit, effective_blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;

    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    constexpr int64_t scale_id_k = 0xD001;
    constexpr int64_t scale_id_v = 0xD002;

    const std::string k_scales = std::string(k_scale_bytes);
    const std::string v_scales = std::string(v_scale_bytes);

    if (per_layer_quant) {
        auto k_layer_scales = split_scale_blob(k_scales, num_layers);
        auto v_layer_scales = split_scale_blob(v_scales, num_layers);

#ifdef USE_MULTITHREADING
        if (args.num_threads >= 2) {
            ensure_nested_openmp_for_fused_halves(args.num_threads);
            std::exception_ptr k_error = nullptr;
            std::exception_ptr v_error = nullptr;
            quantization_args k_args = args;
            quantization_args v_args = args;
            const int inner_threads = std::max(1, args.num_threads / 2);
            k_args.num_threads = inner_threads;
            v_args.num_threads = inner_threads;

            Py_BEGIN_ALLOW_THREADS
            #pragma omp parallel sections num_threads(2)
            {
                #pragma omp section
                {
                    try {
                        dequantize_one_half_per_layer(
                            q_k, out_k, scale_id_k, k_layer_scales, num_layers, k_args);
                    } catch (...) {
                        k_error = std::current_exception();
                    }
                }
                #pragma omp section
                {
                    try {
                        dequantize_one_half_per_layer(
                            q_v, out_v, scale_id_v, v_layer_scales, num_layers, v_args);
                    } catch (...) {
                        v_error = std::current_exception();
                    }
                }
            }
            Py_END_ALLOW_THREADS

            if (k_error) std::rethrow_exception(k_error);
            if (v_error) std::rethrow_exception(v_error);
        } else
#endif
        {
            Py_BEGIN_ALLOW_THREADS
            dequantize_one_half_per_layer(
                q_k, out_k, scale_id_k, k_layer_scales, num_layers, args);
            dequantize_one_half_per_layer(
                q_v, out_v, scale_id_v, v_layer_scales, num_layers, args);
            Py_END_ALLOW_THREADS
        }
    } else {
#ifdef USE_MULTITHREADING
        if (args.num_threads >= 2) {
            ensure_nested_openmp_for_fused_halves(args.num_threads);
            std::exception_ptr k_error = nullptr;
            std::exception_ptr v_error = nullptr;
            quantization_args k_args = args;
            quantization_args v_args = args;
            const int inner_threads = std::max(1, args.num_threads / 2);
            k_args.num_threads = inner_threads;
            v_args.num_threads = inner_threads;

            Py_BEGIN_ALLOW_THREADS
            #pragma omp parallel sections num_threads(2)
            {
                #pragma omp section
                {
                    try {
                        dequantize_one_half(q_k, out_k, scale_id_k, k_scales, k_args);
                    } catch (...) {
                        k_error = std::current_exception();
                    }
                }
                #pragma omp section
                {
                    try {
                        dequantize_one_half(q_v, out_v, scale_id_v, v_scales, v_args);
                    } catch (...) {
                        v_error = std::current_exception();
                    }
                }
            }
            Py_END_ALLOW_THREADS

            if (k_error) std::rethrow_exception(k_error);
            if (v_error) std::rethrow_exception(v_error);
        } else
#endif
        {
            try {
                set_scales_for_id_impl(scale_id_k, k_scales);
                dispatch_dequantization(q_k, out_k, scale_id_k, args);
                clear_scales_for_id_impl(scale_id_k);

                set_scales_for_id_impl(scale_id_v, v_scales);
                dispatch_dequantization(q_v, out_v, scale_id_v, args);
                clear_scales_for_id_impl(scale_id_v);
            } catch (...) {
                clear_scales_for_id_impl(scale_id_k);
                clear_scales_for_id_impl(scale_id_v);
                throw;
            }
        }
    }

    return result;
}

void kvweave_dequantize_chunk_into_4d_py(
    torch::Tensor q_data,
    pybind11::bytes k_scale_bytes,
    pybind11::bytes v_scale_bytes,
    torch::Tensor dst,
    int64_t num_layers,
    int64_t chunk_tokens,
    int64_t h_merged,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    torch::ScalarType output_dtype,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads = 0,
    int layer_num_threads = 1
) {
    ensure_cpu_tensor(q_data, "q_data");
    ensure_cpu_tensor(dst, "dst");
    if (!dst.is_contiguous()) {
        throw std::invalid_argument("dst tensor must be contiguous.");
    }
    if (
        dst.dim() != 4 || dst.size(0) != 2 || dst.size(1) != num_layers ||
        dst.size(2) != chunk_tokens || dst.size(3) != h_merged
    ) {
        throw std::invalid_argument(
            "dst must be contiguous [2, num_layers, chunk_tokens, h_merged]."
        );
    }
    if (dst.scalar_type() != output_dtype) {
        throw std::invalid_argument("dst dtype must match output_dtype.");
    }

    auto q_contig = q_data.contiguous();
    auto q_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    if (q_contig.scalar_type() != q_dtype) {
        throw std::invalid_argument("q_data dtype does not match qbit.");
    }

    int64_t half_numel = num_layers * chunk_tokens * h_merged;
    int64_t half_q_numel = quantized_numel_for_qbit(half_numel, qbit);
    int64_t expected_numel = 2 * half_q_numel;
    if (q_contig.numel() < expected_numel) {
        throw std::invalid_argument("q_data is smaller than expected for K/V payload.");
    }

    auto q_k = torch::from_blob(q_contig.data_ptr(), {half_q_numel}, q_contig.options());
    auto q_v = torch::from_blob(
        static_cast<char*>(q_contig.data_ptr()) + half_q_numel * q_contig.element_size(),
        {half_q_numel}, q_contig.options());

    auto out_k = torch::from_blob(dst.data_ptr(), {half_numel}, dst.options());
    auto out_v = torch::from_blob(
        static_cast<char*>(dst.data_ptr()) + half_numel * dst.element_size(),
        {half_numel}, dst.options());

    const bool per_layer_quant = use_per_layer_quantization(
        num_layers, scaling_method
    );
    const int effective_blocks_num = blocks_num;

    auto args = build_quant_args(qbit, effective_blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;

    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    constexpr int64_t scale_id_k = 0xD201;
    constexpr int64_t scale_id_v = 0xD202;
    const std::string k_scales = std::string(k_scale_bytes);
    const std::string v_scales = std::string(v_scale_bytes);

    if (per_layer_quant) {
        auto k_layer_scales = split_scale_blob(k_scales, num_layers);
        auto v_layer_scales = split_scale_blob(v_scales, num_layers);

        if (layer_num_threads > 1) {
            Py_BEGIN_ALLOW_THREADS
            dequantize_one_half_per_layer(
                q_k, out_k, scale_id_k, k_layer_scales, num_layers, args, layer_num_threads);
            dequantize_one_half_per_layer(
                q_v, out_v, scale_id_v, v_layer_scales, num_layers, args, layer_num_threads);
            Py_END_ALLOW_THREADS
            return;
        }

#ifdef USE_MULTITHREADING
        if (args.num_threads >= 2) {
            ensure_nested_openmp_for_fused_halves(args.num_threads);
            std::exception_ptr k_error = nullptr;
            std::exception_ptr v_error = nullptr;
            quantization_args k_args = args;
            quantization_args v_args = args;
            const int inner_threads = std::max(1, args.num_threads / 2);
            k_args.num_threads = inner_threads;
            v_args.num_threads = inner_threads;

            Py_BEGIN_ALLOW_THREADS
            #pragma omp parallel sections num_threads(2)
            {
                #pragma omp section
                {
                    try {
                        dequantize_one_half_per_layer(
                            q_k, out_k, scale_id_k, k_layer_scales, num_layers, k_args);
                    } catch (...) {
                        k_error = std::current_exception();
                    }
                }
                #pragma omp section
                {
                    try {
                        dequantize_one_half_per_layer(
                            q_v, out_v, scale_id_v, v_layer_scales, num_layers, v_args);
                    } catch (...) {
                        v_error = std::current_exception();
                    }
                }
            }
            Py_END_ALLOW_THREADS

            if (k_error) std::rethrow_exception(k_error);
            if (v_error) std::rethrow_exception(v_error);
            return;
        }
#endif
        Py_BEGIN_ALLOW_THREADS
        dequantize_one_half_per_layer(
            q_k, out_k, scale_id_k, k_layer_scales, num_layers, args);
        dequantize_one_half_per_layer(
            q_v, out_v, scale_id_v, v_layer_scales, num_layers, args);
        Py_END_ALLOW_THREADS
        return;
    }

#ifdef USE_MULTITHREADING
    if (args.num_threads >= 2) {
        ensure_nested_openmp_for_fused_halves(args.num_threads);
        std::exception_ptr k_error = nullptr;
        std::exception_ptr v_error = nullptr;
        quantization_args k_args = args;
        quantization_args v_args = args;
        const int inner_threads = std::max(1, args.num_threads / 2);
        k_args.num_threads = inner_threads;
        v_args.num_threads = inner_threads;

        Py_BEGIN_ALLOW_THREADS
        #pragma omp parallel sections num_threads(2)
        {
            #pragma omp section
            {
                try {
                    dequantize_one_half(q_k, out_k, scale_id_k, k_scales, k_args);
                } catch (...) {
                    k_error = std::current_exception();
                }
            }
            #pragma omp section
            {
                try {
                    dequantize_one_half(q_v, out_v, scale_id_v, v_scales, v_args);
                } catch (...) {
                    v_error = std::current_exception();
                }
            }
        }
        Py_END_ALLOW_THREADS

        if (k_error) std::rethrow_exception(k_error);
        if (v_error) std::rethrow_exception(v_error);
        return;
    }
#endif

    try {
        set_scales_for_id_impl(scale_id_k, k_scales);
        dispatch_dequantization(q_k, out_k, scale_id_k, args);
        clear_scales_for_id_impl(scale_id_k);

        set_scales_for_id_impl(scale_id_v, v_scales);
        dispatch_dequantization(q_v, out_v, scale_id_v, args);
        clear_scales_for_id_impl(scale_id_v);
    } catch (...) {
        clear_scales_for_id_impl(scale_id_k);
        clear_scales_for_id_impl(scale_id_v);
        throw;
    }
}

// Quantize K+V and pack the KVW2 payload in C++. The GIL is released for each kernel.
//
// Arguments:
//   src          : [2, L, T, H*D] contiguous CPU tensor (fp16/bf16/fp32)
//   header_bytes : KVW2 header bytes (magic + metadata + precond + shape),
//                  built once in Python and reused across calls.
//   scale_id_k   : scale ID for K quantization (unique per call)
//   scale_id_v   : scale ID for V quantization (unique per call)
//   qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method,
//   signs, perm, num_threads : quantization parameters.
//
// Returns: complete KVW2 payload bytes (header + scale_section + q_data),
//          ready for direct disk write.
pybind11::bytes kvweave_serialize_chunk_py(
    torch::Tensor src,
    pybind11::bytes header_bytes,
    int64_t scale_id_k,
    int64_t scale_id_v,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    int64_t num_layers,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads = 0
) {
    ensure_cpu_tensor(src, "src");

    // Contiguous copy; use from_blob to avoid Python-backed views.
    auto src_contig = src.contiguous();
    int64_t half_numel = src_contig.numel() / 2;

    // Slice K and V halves via from_blob (pure C++ tensors, no Python backing).
    auto src_k = torch::from_blob(
        src_contig.data_ptr(), {half_numel}, src_contig.options()
    );
    auto src_v = torch::from_blob(
        static_cast<char*>(src_contig.data_ptr()) + half_numel * src_contig.element_size(),
        {half_numel}, src_contig.options()
    );

    auto dst_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    auto q_k = torch::empty({quantized_numel_for_qbit(src_k.numel(), qbit)}, src_k.options().dtype(dst_dtype));
    auto q_v = torch::empty({quantized_numel_for_qbit(src_v.numel(), qbit)}, src_v.options().dtype(dst_dtype));

    const bool per_layer_quant = use_per_layer_quantization(
        num_layers, scaling_method
    );
    const int effective_blocks_num = blocks_num;

    auto args = build_quant_args(qbit, effective_blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;

    // Keep sign/perm tensors alive for the duration of quantization.
    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    std::string k_scale_data;
    std::string v_scale_data;

    if (per_layer_quant) {
#ifdef USE_MULTITHREADING
        if (args.num_threads >= 2) {
            ensure_nested_openmp_for_fused_halves(args.num_threads);
            std::exception_ptr k_error = nullptr;
            std::exception_ptr v_error = nullptr;
            quantization_args k_args = args;
            quantization_args v_args = args;
            const int inner_threads = std::max(1, args.num_threads / 2);
            k_args.num_threads = inner_threads;
            v_args.num_threads = inner_threads;

            Py_BEGIN_ALLOW_THREADS
            #pragma omp parallel sections num_threads(2)
            {
                #pragma omp section
                {
                    try {
                        k_scale_data = quantize_one_half_per_layer(
                            src_k, q_k, scale_id_k, num_layers, k_args);
                    } catch (...) {
                        k_error = std::current_exception();
                    }
                }
                #pragma omp section
                {
                    try {
                        v_scale_data = quantize_one_half_per_layer(
                            src_v, q_v, scale_id_v, num_layers, v_args);
                    } catch (...) {
                        v_error = std::current_exception();
                    }
                }
            }
            Py_END_ALLOW_THREADS

            if (k_error) std::rethrow_exception(k_error);
            if (v_error) std::rethrow_exception(v_error);
        } else
#endif
        {
            Py_BEGIN_ALLOW_THREADS
            k_scale_data = quantize_one_half_per_layer(
                src_k, q_k, scale_id_k, num_layers, args);
            v_scale_data = quantize_one_half_per_layer(
                src_v, q_v, scale_id_v, num_layers, args);
            Py_END_ALLOW_THREADS
        }
    } else {
#ifdef USE_MULTITHREADING
        if (args.num_threads >= 2) {
            ensure_nested_openmp_for_fused_halves(args.num_threads);
            std::exception_ptr k_error = nullptr;
            std::exception_ptr v_error = nullptr;
            quantization_args k_args = args;
            quantization_args v_args = args;
            const int inner_threads = std::max(1, args.num_threads / 2);
            k_args.num_threads = inner_threads;
            v_args.num_threads = inner_threads;

            Py_BEGIN_ALLOW_THREADS
            #pragma omp parallel sections num_threads(2)
            {
                #pragma omp section
                {
                    try {
                        k_scale_data = quantize_one_half(src_k, q_k, scale_id_k, k_args);
                    } catch (...) {
                        k_error = std::current_exception();
                    }
                }
                #pragma omp section
                {
                    try {
                        v_scale_data = quantize_one_half(src_v, q_v, scale_id_v, v_args);
                    } catch (...) {
                        v_error = std::current_exception();
                    }
                }
            }
            Py_END_ALLOW_THREADS

            if (k_error) std::rethrow_exception(k_error);
            if (v_error) std::rethrow_exception(v_error);
        } else
#endif
        {
            Py_BEGIN_ALLOW_THREADS
            k_scale_data = quantize_one_half(src_k, q_k, scale_id_k, args);
            v_scale_data = quantize_one_half(src_v, q_v, scale_id_v, args);
            Py_END_ALLOW_THREADS
        }
    }

    // Pack: header | k_scale_len(4BE) | k_scales | v_scale_len(4BE) | v_scales | q_k | q_v
    std::string hdr_str(header_bytes);
    // Guard size_t -> uint32 narrowing in the framing.
    if (k_scale_data.size() > UINT32_MAX || v_scale_data.size() > UINT32_MAX) {
        throw std::runtime_error(
            "kvweave scale blob exceeds uint32 length framing limit");
    }
    uint32_t k_len = static_cast<uint32_t>(k_scale_data.size());
    uint32_t v_len = static_cast<uint32_t>(v_scale_data.size());
    size_t item_bytes = (qbit <= 8) ? 1 : 2;

    size_t total = hdr_str.size()
                 + 4u + k_len
                 + 4u + v_len
                 + static_cast<size_t>(q_k.numel()) * item_bytes
                 + static_cast<size_t>(q_v.numel()) * item_bytes;

    std::string out;
    out.reserve(total);
    out += hdr_str;

    // Big-endian uint32 helper
    auto append_be32 = [&](uint32_t v) {
        out += static_cast<char>((v >> 24) & 0xFF);
        out += static_cast<char>((v >> 16) & 0xFF);
        out += static_cast<char>((v >>  8) & 0xFF);
        out += static_cast<char>((v >>  0) & 0xFF);
    };

    append_be32(k_len);
    out += k_scale_data;
    append_be32(v_len);
    out += v_scale_data;

    // Quantized K and V data
    auto q_k_contig = q_k.contiguous();
    auto q_v_contig = q_v.contiguous();
    out.append(reinterpret_cast<const char*>(q_k_contig.data_ptr()),
               static_cast<size_t>(q_k_contig.numel()) * item_bytes);
    out.append(reinterpret_cast<const char*>(q_v_contig.data_ptr()),
               static_cast<size_t>(q_v_contig.numel()) * item_bytes);

    return pybind11::bytes(out);
}

// Single-tensor variant of kvweave_serialize_chunk_py (no K/V split).
pybind11::bytes kvweave_serialize_chunk_state_py(
    torch::Tensor src,
    pybind11::bytes header_bytes,
    int64_t scale_id,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    int64_t num_layers,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads = 0
) {
    ensure_cpu_tensor(src, "src");

    auto src_contig = src.contiguous();
    int64_t numel = src_contig.numel();
    auto src_view = torch::from_blob(
        src_contig.data_ptr(), {numel}, src_contig.options()
    );

    auto dst_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    auto q_data = torch::empty({quantized_numel_for_qbit(numel, qbit)}, src_contig.options().dtype(dst_dtype));

    const bool per_layer_quant = use_per_layer_quantization(num_layers, scaling_method);

    auto args = build_quant_args(qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;

    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    std::string scale_data;
    if (per_layer_quant) {
        Py_BEGIN_ALLOW_THREADS
        scale_data = quantize_one_half_per_layer(src_view, q_data, scale_id, num_layers, args);
        Py_END_ALLOW_THREADS
    } else {
        Py_BEGIN_ALLOW_THREADS
        scale_data = quantize_one_half(src_view, q_data, scale_id, args);
        Py_END_ALLOW_THREADS
    }

    // Pack: header | scale_len(4BE) | scales | q_data
    std::string hdr_str(header_bytes);
    if (scale_data.size() > UINT32_MAX) {
        throw std::runtime_error(
            "kvweave scale blob exceeds uint32 length framing limit");
    }
    uint32_t scale_len = static_cast<uint32_t>(scale_data.size());
    size_t item_bytes = (qbit <= 8) ? 1 : 2;

    size_t total = hdr_str.size()
                 + 4u + scale_len
                 + static_cast<size_t>(q_data.numel()) * item_bytes;

    std::string out;
    out.reserve(total);
    out += hdr_str;

    auto append_be32 = [&](uint32_t v) {
        out += static_cast<char>((v >> 24) & 0xFF);
        out += static_cast<char>((v >> 16) & 0xFF);
        out += static_cast<char>((v >>  8) & 0xFF);
        out += static_cast<char>((v >>  0) & 0xFF);
    };

    append_be32(scale_len);
    out += scale_data;

    auto q_data_contig = q_data.contiguous();
    out.append(reinterpret_cast<const char*>(q_data_contig.data_ptr()),
               static_cast<size_t>(q_data_contig.numel()) * item_bytes);

    return pybind11::bytes(out);
}

// Single-tensor variant of kvweave_dequantize_chunk_py.
torch::Tensor kvweave_dequantize_chunk_state_py(
    torch::Tensor q_data,
    pybind11::bytes scale_bytes,
    int64_t num_layers,
    int64_t chunk_tokens,
    int64_t h_merged,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    torch::ScalarType output_dtype,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads = 0
) {
    ensure_cpu_tensor(q_data, "q_data");
    auto q_contig = q_data.contiguous();

    auto q_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    if (q_contig.scalar_type() != q_dtype) {
        throw std::invalid_argument("q_data dtype does not match qbit.");
    }

    int64_t numel = num_layers * chunk_tokens * h_merged;
    int64_t q_numel = quantized_numel_for_qbit(numel, qbit);
    if (q_contig.numel() < q_numel) {
        throw std::invalid_argument("q_data is smaller than expected for the state payload.");
    }

    auto result = torch::empty(
        {num_layers, chunk_tokens, h_merged},
        q_contig.options().dtype(output_dtype)
    );

    auto q_view = torch::from_blob(
        q_contig.data_ptr(), {q_numel}, q_contig.options()
    );
    auto out_view = torch::from_blob(
        result.data_ptr(), {numel}, result.options()
    );

    const bool per_layer_quant = use_per_layer_quantization(num_layers, scaling_method);

    auto args = build_quant_args(qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;

    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    constexpr int64_t scale_id = 0xD003;
    const std::string scales = std::string(scale_bytes);

    if (per_layer_quant) {
        auto layer_scales = split_scale_blob(scales, num_layers);
        Py_BEGIN_ALLOW_THREADS
        dequantize_one_half_per_layer(q_view, out_view, scale_id, layer_scales, num_layers, args);
        Py_END_ALLOW_THREADS
    } else {
        try {
            set_scales_for_id_impl(scale_id, scales);
            dispatch_dequantization(q_view, out_view, scale_id, args);
            clear_scales_for_id_impl(scale_id);
        } catch (...) {
            clear_scales_for_id_impl(scale_id);
            throw;
        }
    }

    return result;
}

// Copy one Mamba sub-state's bytes out of an opaque page view.
// Precondition: the byte range must not cross a plane boundary.
// page_count is layers*blocks; consecutive pages are page_bytes apart.
void gather_mamba_substate_bytes(
    const uint8_t* raw_bytes,
    uint8_t* dst_bytes,
    int64_t page_count,
    int64_t page_bytes,
    int64_t byte_offset,
    int64_t byte_length
) {
    for (int64_t p = 0; p < page_count; ++p) {
        std::memcpy(
            dst_bytes + p * byte_length,
            raw_bytes + p * page_bytes + byte_offset,
            static_cast<size_t>(byte_length)
        );
    }
}

// Inverse of gather_mamba_substate_bytes: scatter bytes back into the page.
void scatter_mamba_substate_bytes(
    const uint8_t* src_bytes,
    uint8_t* raw_bytes,
    int64_t page_count,
    int64_t page_bytes,
    int64_t byte_offset,
    int64_t byte_length
) {
    for (int64_t p = 0; p < page_count; ++p) {
        std::memcpy(
            raw_bytes + p * page_bytes + byte_offset,
            src_bytes + p * byte_length,
            static_cast<size_t>(byte_length)
        );
    }
}

// Fused gather + quantize of one Mamba sub-state straight from the opaque page.
// Payload is identical to gather followed by kvweave_serialize_chunk_state.
// Args as in kvweave_serialize_chunk_state_py, plus raw (opaque CPU page tensor,
// read as bytes), page_bytes, byte_offset/byte_length (sub-state range within a
// page), layers, blocks, is_two_plane (sub-state must not straddle planes).
pybind11::bytes kvweave_serialize_mamba_page_substate_py(
    torch::Tensor raw,
    int64_t page_bytes,
    int64_t byte_offset,
    int64_t byte_length,
    int64_t layers,
    int64_t blocks,
    bool is_two_plane,
    pybind11::bytes header_bytes,
    int64_t scale_id,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    int64_t num_layers,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    torch::ScalarType substate_dtype,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads = 0
) {
    ensure_cpu_tensor(raw, "raw");
    if (is_two_plane) {
        throw std::invalid_argument(
            "kvweave_serialize_mamba_page_substate: two-plane pages are not "
            "yet supported by this entry point; caller must fall back to "
            "split_mamba_chunk for two-plane chunks.");
    }
    auto raw_contig = raw.contiguous();
    const int64_t page_count = layers * blocks;
    if (raw_contig.numel() * raw_contig.element_size() < page_count * page_bytes) {
        throw std::invalid_argument(
            "raw tensor is smaller than layers*blocks*page_bytes.");
    }

    const int64_t elem_size = static_cast<int64_t>(c10::elementSize(substate_dtype));
    if (byte_length % elem_size != 0) {
        throw std::invalid_argument(
            "byte_length is not a multiple of substate_dtype's element size.");
    }
    const int64_t numel = page_count * (byte_length / elem_size);

    auto gathered = torch::empty({page_count * byte_length}, torch::dtype(torch::kUInt8));
    gather_mamba_substate_bytes(
        reinterpret_cast<const uint8_t*>(raw_contig.data_ptr()),
        gathered.data_ptr<uint8_t>(),
        page_count, page_bytes, byte_offset, byte_length
    );

    auto src_view = torch::from_blob(
        gathered.data_ptr(), {numel}, torch::TensorOptions().dtype(substate_dtype)
    );

    auto dst_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    auto q_data = torch::empty({quantized_numel_for_qbit(numel, qbit)}, torch::TensorOptions().dtype(dst_dtype));

    const bool per_layer_quant = use_per_layer_quantization(num_layers, scaling_method);

    auto args = build_quant_args(qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;

    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    std::string scale_data;
    if (per_layer_quant) {
        Py_BEGIN_ALLOW_THREADS
        scale_data = quantize_one_half_per_layer(src_view, q_data, scale_id, num_layers, args);
        Py_END_ALLOW_THREADS
    } else {
        Py_BEGIN_ALLOW_THREADS
        scale_data = quantize_one_half(src_view, q_data, scale_id, args);
        Py_END_ALLOW_THREADS
    }

    std::string hdr_str(header_bytes);
    if (scale_data.size() > UINT32_MAX) {
        throw std::runtime_error(
            "kvweave scale blob exceeds uint32 length framing limit");
    }
    uint32_t scale_len = static_cast<uint32_t>(scale_data.size());
    size_t item_bytes = (qbit <= 8) ? 1 : 2;

    size_t total = hdr_str.size()
                 + 4u + scale_len
                 + static_cast<size_t>(q_data.numel()) * item_bytes;

    std::string out;
    out.reserve(total);
    out += hdr_str;

    auto append_be32 = [&](uint32_t v) {
        out += static_cast<char>((v >> 24) & 0xFF);
        out += static_cast<char>((v >> 16) & 0xFF);
        out += static_cast<char>((v >>  8) & 0xFF);
        out += static_cast<char>((v >>  0) & 0xFF);
    };

    append_be32(scale_len);
    out += scale_data;

    auto q_data_contig = q_data.contiguous();
    out.append(reinterpret_cast<const char*>(q_data_contig.data_ptr()),
               static_cast<size_t>(q_data_contig.numel()) * item_bytes);

    return pybind11::bytes(out);
}

// Fused dequantize + scatter of one Mamba sub-state into the opaque page `out`
// (in place; contiguous CPU tensor with the page's real shape/dtype).
void kvweave_dequantize_mamba_page_substate_py(
    torch::Tensor q_data,
    pybind11::bytes scale_bytes,
    torch::Tensor out,
    int64_t page_bytes,
    int64_t byte_offset,
    int64_t byte_length,
    int64_t layers,
    int64_t blocks,
    bool is_two_plane,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    torch::ScalarType substate_dtype,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads = 0
) {
    ensure_cpu_tensor(q_data, "q_data");
    ensure_cpu_tensor(out, "out");
    if (is_two_plane) {
        throw std::invalid_argument(
            "kvweave_dequantize_mamba_page_substate: two-plane pages are not "
            "yet supported by this entry point; caller must fall back to "
            "merge_mamba_chunk for two-plane chunks.");
    }
    if (!out.is_contiguous()) {
        throw std::invalid_argument("out must be a contiguous tensor.");
    }
    auto q_contig = q_data.contiguous();

    auto q_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    if (q_contig.scalar_type() != q_dtype) {
        throw std::invalid_argument("q_data dtype does not match qbit.");
    }

    const int64_t page_count = layers * blocks;
    const int64_t elem_size = static_cast<int64_t>(c10::elementSize(substate_dtype));
    if (byte_length % elem_size != 0) {
        throw std::invalid_argument(
            "byte_length is not a multiple of substate_dtype's element size.");
    }
    const int64_t numel = page_count * (byte_length / elem_size);
    const int64_t q_numel = quantized_numel_for_qbit(numel, qbit);
    if (q_contig.numel() < q_numel) {
        throw std::invalid_argument("q_data is smaller than expected for the state payload.");
    }
    if (out.numel() * out.element_size() < page_count * page_bytes) {
        throw std::invalid_argument("out tensor is smaller than layers*blocks*page_bytes.");
    }

    auto dequantized = torch::empty({numel}, torch::TensorOptions().dtype(substate_dtype));

    auto q_view = torch::from_blob(
        q_contig.data_ptr(), {q_numel}, q_contig.options()
    );
    auto out_view = torch::from_blob(
        dequantized.data_ptr(), {numel}, dequantized.options()
    );

    const bool per_layer_quant = use_per_layer_quantization(layers, scaling_method);

    auto args = build_quant_args(qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;

    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    constexpr int64_t scale_id = 0xD004;
    const std::string scales = std::string(scale_bytes);

    if (per_layer_quant) {
        auto layer_scales = split_scale_blob(scales, layers);
        Py_BEGIN_ALLOW_THREADS
        dequantize_one_half_per_layer(q_view, out_view, scale_id, layer_scales, layers, args);
        Py_END_ALLOW_THREADS
    } else {
        try {
            set_scales_for_id_impl(scale_id, scales);
            dispatch_dequantization(q_view, out_view, scale_id, args);
            clear_scales_for_id_impl(scale_id);
        } catch (...) {
            clear_scales_for_id_impl(scale_id);
            throw;
        }
    }

    scatter_mamba_substate_bytes(
        reinterpret_cast<const uint8_t*>(dequantized.data_ptr()),
        reinterpret_cast<uint8_t*>(out.data_ptr()),
        page_count, page_bytes, byte_offset, byte_length
    );
}

template <typename KVType, typename QType>
void run_quantize_kernel_mamba_page(
    uint8_t* page_base, int64_t page_bytes, int64_t byte_offset,
    torch::Tensor& dst, int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    auto* dst_ptr = reinterpret_cast<QType*>(dst.data_ptr());
    quantize_kvcache_mamba_page<KVType, QType>(
        page_base, page_bytes, byte_offset, dst_ptr, element_count,
        rows_per_page, row_width, col_offset, head_dim, scale_id, args);
}

void dispatch_quantization_kernel_mamba_page(
    torch::ScalarType substate_dtype,
    uint8_t* page_base, int64_t page_bytes, int64_t byte_offset,
    torch::Tensor& dst, int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    const auto dst_type = dst.scalar_type();
    if (dst_type == torch::kInt8) {
        if (substate_dtype == torch::kFloat32) {
            run_quantize_kernel_mamba_page<float, int8_t>(page_base, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kFloat16) {
            run_quantize_kernel_mamba_page<_Float16, int8_t>(page_base, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kBFloat16) {
            run_quantize_kernel_mamba_page<__bf16, int8_t>(page_base, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported substate dtype for quantization (int8 destination).");
        }
    } else if (dst_type == torch::kInt16) {
        if (substate_dtype == torch::kFloat32) {
            run_quantize_kernel_mamba_page<float, int16_t>(page_base, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kFloat16) {
            run_quantize_kernel_mamba_page<_Float16, int16_t>(page_base, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kBFloat16) {
            run_quantize_kernel_mamba_page<__bf16, int16_t>(page_base, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported substate dtype for quantization (int16 destination).");
        }
    } else {
        throw std::invalid_argument("Destination dtype must be int8 or int16 for quantization.");
    }
}

template <typename KVType, typename QType>
void run_dequantize_kernel_mamba_page(
    torch::Tensor& src, uint8_t* page_base, int64_t page_bytes, int64_t byte_offset,
    int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    auto* src_ptr = reinterpret_cast<QType*>(src.data_ptr());
    dequantize_kvcache_mamba_page<KVType, QType>(
        src_ptr, page_base, page_bytes, byte_offset, element_count,
        rows_per_page, row_width, col_offset, head_dim, scale_id, args);
}

void dispatch_dequantization_kernel_mamba_page(
    torch::ScalarType substate_dtype,
    torch::Tensor& src, uint8_t* page_base, int64_t page_bytes, int64_t byte_offset,
    int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    const auto src_type = src.scalar_type();
    if (src_type == torch::kInt8) {
        if (substate_dtype == torch::kFloat32) {
            run_dequantize_kernel_mamba_page<float, int8_t>(src, page_base, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kFloat16) {
            run_dequantize_kernel_mamba_page<_Float16, int8_t>(src, page_base, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kBFloat16) {
            run_dequantize_kernel_mamba_page<__bf16, int8_t>(src, page_base, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported substate dtype for dequantization (int8 source).");
        }
    } else if (src_type == torch::kInt16) {
        if (substate_dtype == torch::kFloat32) {
            run_dequantize_kernel_mamba_page<float, int16_t>(src, page_base, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kFloat16) {
            run_dequantize_kernel_mamba_page<_Float16, int16_t>(src, page_base, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kBFloat16) {
            run_dequantize_kernel_mamba_page<__bf16, int16_t>(src, page_base, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported substate dtype for dequantization (int16 source).");
        }
    } else {
        throw std::invalid_argument("Source dtype must be int8 or int16 for dequantization.");
    }
}

template <typename KVType, typename QType>
void run_quantize_kernel_mamba_page_2plane(
    uint8_t* page_base0, uint8_t* page_base1, int64_t plane_bytes,
    int64_t page_bytes, int64_t byte_offset,
    torch::Tensor& dst, int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    auto* dst_ptr = reinterpret_cast<QType*>(dst.data_ptr());
    quantize_kvcache_mamba_page_2plane<KVType, QType>(
        page_base0, page_base1, plane_bytes, page_bytes, byte_offset, dst_ptr,
        element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
}

void dispatch_quantization_kernel_mamba_page_2plane(
    torch::ScalarType substate_dtype,
    uint8_t* page_base0, uint8_t* page_base1, int64_t plane_bytes,
    int64_t page_bytes, int64_t byte_offset,
    torch::Tensor& dst, int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    const auto dst_type = dst.scalar_type();
    if (dst_type == torch::kInt8) {
        if (substate_dtype == torch::kFloat32) {
            run_quantize_kernel_mamba_page_2plane<float, int8_t>(page_base0, page_base1, plane_bytes, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kFloat16) {
            run_quantize_kernel_mamba_page_2plane<_Float16, int8_t>(page_base0, page_base1, plane_bytes, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kBFloat16) {
            run_quantize_kernel_mamba_page_2plane<__bf16, int8_t>(page_base0, page_base1, plane_bytes, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported substate dtype for quantization (int8 destination).");
        }
    } else if (dst_type == torch::kInt16) {
        if (substate_dtype == torch::kFloat32) {
            run_quantize_kernel_mamba_page_2plane<float, int16_t>(page_base0, page_base1, plane_bytes, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kFloat16) {
            run_quantize_kernel_mamba_page_2plane<_Float16, int16_t>(page_base0, page_base1, plane_bytes, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kBFloat16) {
            run_quantize_kernel_mamba_page_2plane<__bf16, int16_t>(page_base0, page_base1, plane_bytes, page_bytes, byte_offset, dst, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported substate dtype for quantization (int16 destination).");
        }
    } else {
        throw std::invalid_argument("Destination dtype must be int8 or int16 for quantization.");
    }
}

template <typename KVType, typename QType>
void run_dequantize_kernel_mamba_page_2plane(
    torch::Tensor& src, uint8_t* page_base0, uint8_t* page_base1,
    int64_t plane_bytes, int64_t page_bytes, int64_t byte_offset,
    int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    auto* src_ptr = reinterpret_cast<QType*>(src.data_ptr());
    dequantize_kvcache_mamba_page_2plane<KVType, QType>(
        src_ptr, page_base0, page_base1, plane_bytes, page_bytes, byte_offset,
        element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
}

void dispatch_dequantization_kernel_mamba_page_2plane(
    torch::ScalarType substate_dtype,
    torch::Tensor& src, uint8_t* page_base0, uint8_t* page_base1,
    int64_t plane_bytes, int64_t page_bytes, int64_t byte_offset,
    int64_t element_count, int64_t rows_per_page,
    int64_t row_width, int64_t col_offset, int64_t head_dim,
    int64_t scale_id, quantization_args& args
) {
    const auto src_type = src.scalar_type();
    if (src_type == torch::kInt8) {
        if (substate_dtype == torch::kFloat32) {
            run_dequantize_kernel_mamba_page_2plane<float, int8_t>(src, page_base0, page_base1, plane_bytes, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kFloat16) {
            run_dequantize_kernel_mamba_page_2plane<_Float16, int8_t>(src, page_base0, page_base1, plane_bytes, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kBFloat16) {
            run_dequantize_kernel_mamba_page_2plane<__bf16, int8_t>(src, page_base0, page_base1, plane_bytes, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported substate dtype for dequantization (int8 source).");
        }
    } else if (src_type == torch::kInt16) {
        if (substate_dtype == torch::kFloat32) {
            run_dequantize_kernel_mamba_page_2plane<float, int16_t>(src, page_base0, page_base1, plane_bytes, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kFloat16) {
            run_dequantize_kernel_mamba_page_2plane<_Float16, int16_t>(src, page_base0, page_base1, plane_bytes, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else if (substate_dtype == torch::kBFloat16) {
            run_dequantize_kernel_mamba_page_2plane<__bf16, int16_t>(src, page_base0, page_base1, plane_bytes, page_bytes, byte_offset, element_count, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else {
            throw std::invalid_argument("Unsupported substate dtype for dequantization (int16 source).");
        }
    } else {
        throw std::invalid_argument("Source dtype must be int8 or int16 for dequantization.");
    }
}

// Encode one Mamba sub-state directly from its opaque page range. Other
// geometries reuse the standard kernels via contiguous scratch.
// Two-plane pages require element-aligned boundaries and substate offsets;
// per_tensor without RH still requires the split path.
pybind11::bytes kvweave_serialize_mamba_page_substate_direct_py(
    torch::Tensor raw,
    int64_t page_bytes,
    int64_t byte_offset,
    int64_t row_width,
    int64_t rows_per_page_hint,
    int64_t layers,
    int64_t blocks,
    bool is_two_plane,
    pybind11::bytes header_bytes,
    int64_t scale_id,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    bool asym,
    const std::string& scaling_method,
    torch::ScalarType substate_dtype,
    int64_t col_offset = 0,
    int num_threads = 0,
    bool rh = false,
    c10::optional<torch::Tensor> signs = c10::nullopt,
    c10::optional<torch::Tensor> perm = c10::nullopt
) {
    ensure_cpu_tensor(raw, "raw");
    if (is_two_plane && scaling_method == "per_tensor" && !rh) {
        throw std::invalid_argument(
            "kvweave_serialize_mamba_page_substate_direct: two-plane pages "
            "require split_mamba_chunk for per_tensor without RH.");
    }
    if (col_offset < 0 || col_offset + head_dim > row_width) {
        throw std::invalid_argument(
            "col_offset/head_dim must select a sub-range within [0, row_width).");
    }
    torch::Tensor raw_contig;
    torch::Tensor plane0_contig, plane1_contig;
    int64_t plane_bytes = 0;
    const int64_t page_count = layers * blocks;
    if (is_two_plane) {
        if (raw.dim() != 4 || raw.size(0) != 2) {
            throw std::invalid_argument(
                "kvweave_serialize_mamba_page_substate_direct: is_two_plane=True "
                "requires raw shaped [2, layers, tokens, hidden].");
        }
        if (page_bytes % 2 != 0) {
            throw std::invalid_argument(
                "kvweave_serialize_mamba_page_substate_direct: two-plane "
                "page_bytes must be even (page_bytes = 2 * plane_bytes).");
        }
        plane_bytes = page_bytes / 2;
        plane0_contig = raw[0].contiguous();
        plane1_contig = raw[1].contiguous();
        if (plane0_contig.numel() * plane0_contig.element_size() < page_count * plane_bytes
            || plane1_contig.numel() * plane1_contig.element_size() < page_count * plane_bytes) {
            throw std::invalid_argument(
                "raw tensor's planes are smaller than layers*blocks*plane_bytes.");
        }
    } else {
        raw_contig = raw.contiguous();
        if (raw_contig.numel() * raw_contig.element_size() < page_count * page_bytes) {
            throw std::invalid_argument(
                "raw tensor is smaller than layers*blocks*page_bytes.");
        }
    }

    // row_width: elements per row in the region; head_dim: width of the quantized
    // segment (<= row_width when col_offset > 0); rows_per_page_hint: rows per
    // (layer, block) page.
    const int64_t elem_size = static_cast<int64_t>(c10::elementSize(substate_dtype));
    const int64_t rows_per_page = rows_per_page_hint;
    if (is_two_plane && (plane_bytes % elem_size != 0 || byte_offset % elem_size != 0)) {
        throw std::invalid_argument(
            "two-plane direct requires element-aligned plane_bytes and byte_offset");
    }
    if (rows_per_page <= 0) {
        throw std::invalid_argument("rows_per_page_hint must be positive.");
    }
    if (rows_per_page * row_width * elem_size + byte_offset > page_bytes) {
        throw std::invalid_argument(
            "rows_per_page_hint * row_width does not fit within page_bytes "
            "starting at byte_offset.");
    }
    const int64_t numel = page_count * rows_per_page * head_dim;

    auto dst_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    auto q_data = torch::empty({quantized_numel_for_qbit(numel, qbit)}, torch::TensorOptions().dtype(dst_dtype));

    if (scaling_method != "per_channel" && scaling_method != "per_token" && scaling_method != "per_tensor") {
        throw std::invalid_argument(
            "kvweave_serialize_mamba_page_substate_direct: scaling_method "
            "must be one of 'per_channel', 'per_token', 'per_tensor'");
    }
    if (rh && (!signs.has_value() || !perm.has_value())) {
        throw std::invalid_argument(
            "RH direct quantization requires both signs and perm tensors.");
    }
    torch::Tensor signs_contig;
    torch::Tensor perm_contig;
    if (rh) {
        ensure_cpu_tensor(*signs, "signs");
        ensure_cpu_tensor(*perm, "perm");
        signs_contig = signs->contiguous();
        perm_contig = perm->contiguous();
    }
    auto args = build_quant_args(
        qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;
    if (rh) {
        set_mamba_rh_vectors(args, signs_contig, perm_contig, numel / layers);
    }

    uint8_t* page_base = nullptr;
    uint8_t* page_base0 = nullptr;
    uint8_t* page_base1 = nullptr;
    if (is_two_plane) {
        page_base0 = reinterpret_cast<uint8_t*>(plane0_contig.data_ptr());
        page_base1 = reinterpret_cast<uint8_t*>(plane1_contig.data_ptr());
    } else {
        page_base = reinterpret_cast<uint8_t*>(raw_contig.data_ptr());
    }

    // Per-layer scale framing, matching quantize_one_half_per_layer.
    const bool per_layer = use_per_layer_quantization(layers, scaling_method);
    const int64_t numel_per_layer = numel / layers;
    const int64_t q_numel_per_layer = quantized_numel_for_qbit(numel_per_layer, qbit);
    const int64_t pages_per_layer = page_count / layers;
    std::string scale_data;
    validate_quant_args(numel_per_layer, args);
    if (uses_mamba_fused_scaling(args, numel_per_layer, row_width, col_offset, substate_dtype)) {
        const int64_t rows_per_layer = numel_per_layer / head_dim;
        const int64_t scale_count = scaling_method == "per_channel" ? head_dim : rows_per_layer;
        std::vector<float> row_scales(static_cast<size_t>(layers * scale_count));
        std::vector<float> row_zps(row_scales.size());
        const mamba_page_params params{
            page_bytes, byte_offset, rows_per_page, layers * rows_per_layer,
            head_dim, row_width, col_offset, rows_per_layer};
        dispatch_mamba_fused_scaling<true>(
            substate_dtype, page_base0 ? page_base0 : page_base, page_base1,
            q_data, row_scales, row_zps, params, args);
        scale_data = pack_mamba_dense_scales(row_scales, row_zps, layers, scale_count);
    } else if (rh || (scaling_method == "per_token"
                     && (is_two_plane || row_width != head_dim || col_offset != 0))) {
        if (!is_two_plane && (row_width != head_dim || col_offset != 0)
            && scaling_method != "per_channel" && scaling_method != "per_token"
            && scaling_method != "per_tensor") {
            throw std::invalid_argument(
                "unsupported RH direct column sub-range scaling method.");
        }
        auto gathered = torch::empty(
            {numel}, torch::TensorOptions().dtype(substate_dtype));
        copy_mamba_page_substate(
            page_base0 ? page_base0 : page_base,
            page_base1,
            reinterpret_cast<uint8_t*>(gathered.data_ptr()),
            page_bytes,
            byte_offset,
            row_width,
            rows_per_page,
            head_dim,
            col_offset,
            layers,
            blocks,
            elem_size,
            is_two_plane,
            true);
        if (per_layer) {
            scale_data = quantize_one_half_per_layer(
                gathered, q_data, scale_id, layers, args);
        } else {
            ClearScaleIdGuard scales(scale_id);
            dispatch_quantization_kernel(gathered, q_data, scale_id, args);
            scale_data = get_scales_bytes_for_id(scale_id);
        }
    } else if (per_layer) {
        for (int64_t l = 0; l < layers; ++l) {
            const int64_t layer_scale_id = scale_id + l;
            ClearScaleIdGuard scales(layer_scale_id);
            auto layer_q_data = torch::from_blob(
                static_cast<char*>(q_data.data_ptr()) + l * q_numel_per_layer * q_data.element_size(),
                {q_numel_per_layer}, q_data.options()
            );
            Py_BEGIN_ALLOW_THREADS
            if (is_two_plane) {
                dispatch_quantization_kernel_mamba_page_2plane(
                    substate_dtype, page_base0 + l * pages_per_layer * plane_bytes,
                    page_base1 + l * pages_per_layer * plane_bytes, plane_bytes,
                    page_bytes, byte_offset, layer_q_data, numel_per_layer,
                    rows_per_page, row_width, col_offset, head_dim, layer_scale_id, args);
            } else {
                dispatch_quantization_kernel_mamba_page(
                    substate_dtype, page_base + l * pages_per_layer * page_bytes,
                    page_bytes, byte_offset, layer_q_data, numel_per_layer,
                    rows_per_page, row_width, col_offset, head_dim, layer_scale_id, args);
            }
            Py_END_ALLOW_THREADS
            scale_data += get_scales_bytes_for_id(layer_scale_id);
        }
    } else {
        ClearScaleIdGuard scales(scale_id);
        Py_BEGIN_ALLOW_THREADS
        if (is_two_plane) {
            dispatch_quantization_kernel_mamba_page_2plane(
                substate_dtype, page_base0, page_base1, plane_bytes,
                page_bytes, byte_offset, q_data,
                numel, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        } else {
            dispatch_quantization_kernel_mamba_page(
                substate_dtype, page_base, page_bytes, byte_offset, q_data,
                numel, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
        }
        Py_END_ALLOW_THREADS
        scale_data = get_scales_bytes_for_id(scale_id);
    }

    std::string hdr_str(header_bytes);
    if (scale_data.size() > UINT32_MAX) {
        throw std::runtime_error(
            "kvweave scale blob exceeds uint32 length framing limit");
    }
    uint32_t scale_len = static_cast<uint32_t>(scale_data.size());
    size_t item_bytes = (qbit <= 8) ? 1 : 2;

    size_t total = hdr_str.size()
                 + 4u + scale_len
                 + static_cast<size_t>(q_data.numel()) * item_bytes;

    std::string out;
    out.reserve(total);
    out += hdr_str;

    auto append_be32 = [&](uint32_t v) {
        out += static_cast<char>((v >> 24) & 0xFF);
        out += static_cast<char>((v >> 16) & 0xFF);
        out += static_cast<char>((v >>  8) & 0xFF);
        out += static_cast<char>((v >>  0) & 0xFF);
    };

    append_be32(scale_len);
    out += scale_data;

    auto q_data_contig = q_data.contiguous();
    out.append(reinterpret_cast<const char*>(q_data_contig.data_ptr()),
               static_cast<size_t>(q_data_contig.numel()) * item_bytes);

    return pybind11::bytes(out);
}

// Decode one Mamba sub-state directly into its opaque page range. RH-disabled
// and per-token row-RH paths scatter in place; other RH modes use scratch.
void kvweave_dequantize_mamba_page_substate_direct_py(
    torch::Tensor q_data,
    pybind11::bytes scale_bytes,
    torch::Tensor out,
    int64_t page_bytes,
    int64_t byte_offset,
    int64_t row_width,
    int64_t rows_per_page_hint,
    int64_t layers,
    int64_t blocks,
    bool is_two_plane,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    bool asym,
    const std::string& scaling_method,
    torch::ScalarType substate_dtype,
    int64_t col_offset = 0,
    int num_threads = 0,
    bool rh = false,
    c10::optional<torch::Tensor> signs = c10::nullopt,
    c10::optional<torch::Tensor> perm = c10::nullopt
) {
    ensure_cpu_tensor(q_data, "q_data");
    ensure_cpu_tensor(out, "out");
    if (is_two_plane && scaling_method == "per_tensor" && !rh) {
        throw std::invalid_argument(
            "kvweave_dequantize_mamba_page_substate_direct: two-plane pages "
            "require merge_mamba_chunk for per_tensor without RH.");
    }
    if (col_offset < 0 || col_offset + head_dim > row_width) {
        throw std::invalid_argument(
            "col_offset/head_dim must select a sub-range within [0, row_width).");
    }
    auto q_contig = q_data.contiguous();

    auto q_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    if (q_contig.scalar_type() != q_dtype) {
        throw std::invalid_argument("q_data dtype does not match qbit.");
    }

    const int64_t page_count = layers * blocks;
    const int64_t elem_size = static_cast<int64_t>(c10::elementSize(substate_dtype));
    const int64_t rows_per_page = rows_per_page_hint;
    if (rows_per_page <= 0) {
        throw std::invalid_argument("rows_per_page_hint must be positive.");
    }
    if (rows_per_page * row_width * elem_size + byte_offset > page_bytes) {
        throw std::invalid_argument(
            "rows_per_page_hint * row_width does not fit within page_bytes "
            "starting at byte_offset.");
    }
    const int64_t numel = page_count * rows_per_page * head_dim;
    const int64_t q_numel = quantized_numel_for_qbit(numel, qbit);
    if (q_contig.numel() < q_numel) {
        throw std::invalid_argument("q_data is smaller than expected for the state payload.");
    }

    int64_t plane_bytes = 0;
    torch::Tensor plane0, plane1;
    if (is_two_plane) {
        if (out.dim() != 4 || out.size(0) != 2) {
            throw std::invalid_argument(
                "kvweave_dequantize_mamba_page_substate_direct: is_two_plane=True "
                "requires out shaped [2, layers, tokens, hidden].");
        }
        if (page_bytes % 2 != 0) {
            throw std::invalid_argument(
                "kvweave_dequantize_mamba_page_substate_direct: two-plane "
                "page_bytes must be even (page_bytes = 2 * plane_bytes).");
        }
        plane_bytes = page_bytes / 2;
        plane0 = out[0];
        plane1 = out[1];
        if (plane_bytes % elem_size != 0 || byte_offset % elem_size != 0) {
            throw std::invalid_argument(
                "two-plane direct requires element-aligned plane_bytes and byte_offset");
        }
        if (!plane0.is_contiguous() || !plane1.is_contiguous()) {
            throw std::invalid_argument("out's planes must be contiguous tensors.");
        }
        if (plane0.numel() * plane0.element_size() < page_count * plane_bytes
            || plane1.numel() * plane1.element_size() < page_count * plane_bytes) {
            throw std::invalid_argument("out tensor's planes are smaller than layers*blocks*plane_bytes.");
        }
    } else {
        if (!out.is_contiguous()) {
            throw std::invalid_argument("out must be a contiguous tensor.");
        }
        if (out.numel() * out.element_size() < page_count * page_bytes) {
            throw std::invalid_argument("out tensor is smaller than layers*blocks*page_bytes.");
        }
    }

    if (scaling_method != "per_channel" && scaling_method != "per_token" && scaling_method != "per_tensor") {
        throw std::invalid_argument(
            "kvweave_dequantize_mamba_page_substate_direct: scaling_method "
            "must be one of 'per_channel', 'per_token', 'per_tensor'");
    }
    if (rh && (!signs.has_value() || !perm.has_value())) {
        throw std::invalid_argument(
            "RH direct dequantization requires both signs and perm tensors.");
    }
    torch::Tensor signs_contig;
    torch::Tensor perm_contig;
    if (rh) {
        ensure_cpu_tensor(*signs, "signs");
        ensure_cpu_tensor(*perm, "perm");
        signs_contig = signs->contiguous();
        perm_contig = perm->contiguous();
    }
    auto args = build_quant_args(
        qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);
    args.num_threads = num_threads;
    if (rh) {
        set_mamba_rh_vectors(args, signs_contig, perm_contig, numel / layers);
    }

    uint8_t* page_base = nullptr;
    uint8_t* page_base0 = nullptr;
    uint8_t* page_base1 = nullptr;
    if (is_two_plane) {
        page_base0 = reinterpret_cast<uint8_t*>(plane0.data_ptr());
        page_base1 = reinterpret_cast<uint8_t*>(plane1.data_ptr());
    } else {
        page_base = reinterpret_cast<uint8_t*>(out.data_ptr());
    }
    const std::string scales = std::string(scale_bytes);

    // Per-layer scale framing, matching the serialize side.
    const bool per_layer = use_per_layer_quantization(layers, scaling_method);
    constexpr int64_t scale_id = 0xD006;
    validate_quant_args(numel / layers, args);
    if (uses_mamba_fused_scaling(args, numel / layers, row_width, col_offset, substate_dtype)) {
        const int64_t rows_per_layer = numel / layers / head_dim;
        const int64_t scale_count = scaling_method == "per_channel" ? head_dim : rows_per_layer;
        std::vector<float> row_scales(static_cast<size_t>(layers * scale_count));
        std::vector<float> row_zps(row_scales.size());
        unpack_mamba_dense_scales(scales, layers, scale_count, row_scales, row_zps);
        const mamba_page_params params{
            page_bytes, byte_offset, rows_per_page, layers * rows_per_layer,
            head_dim, row_width, col_offset, rows_per_layer};
        dispatch_mamba_fused_scaling<false>(
            substate_dtype, page_base0 ? page_base0 : page_base, page_base1,
            q_contig, row_scales, row_zps, params, args);
    } else if (rh || (scaling_method == "per_token"
                     && (is_two_plane || row_width != head_dim || col_offset != 0))) {
        if (!is_two_plane && (row_width != head_dim || col_offset != 0)
            && scaling_method != "per_channel" && scaling_method != "per_token"
            && scaling_method != "per_tensor") {
            throw std::invalid_argument(
                "unsupported RH direct column sub-range scaling method.");
        }
        auto gathered = torch::empty(
            {numel}, torch::TensorOptions().dtype(substate_dtype));
        if (per_layer) {
            auto layer_scales = split_scale_blob(scales, layers);
            dequantize_one_half_per_layer(
                q_contig, gathered, scale_id, layer_scales, layers, args);
        } else {
            try {
                set_scales_for_id_impl(scale_id, scales);
                dispatch_dequantization_kernel(q_contig, gathered, scale_id, args);
                clear_scales_for_id_impl(scale_id);
            } catch (...) {
                clear_scales_for_id_impl(scale_id);
                throw;
            }
        }
        copy_mamba_page_substate(
            page_base0 ? page_base0 : page_base,
            page_base1,
            reinterpret_cast<uint8_t*>(gathered.data_ptr()),
            page_bytes,
            byte_offset,
            row_width,
            rows_per_page,
            head_dim,
            col_offset,
            layers,
            blocks,
            elem_size,
            is_two_plane,
            false);
    } else if (per_layer) {
        auto layer_scales = split_scale_blob(scales, layers);
        const int64_t numel_per_layer = numel / layers;
        const int64_t q_numel_per_layer = quantized_numel_for_qbit(numel_per_layer, qbit);
        const int64_t pages_per_layer = page_count / layers;
        for (int64_t l = 0; l < layers; ++l) {
            auto layer_q_data = torch::from_blob(
                static_cast<char*>(q_contig.data_ptr()) + l * q_numel_per_layer * q_contig.element_size(),
                {q_numel_per_layer}, q_contig.options()
            );
            try {
                set_scales_for_id_impl(scale_id, layer_scales[static_cast<size_t>(l)]);
                Py_BEGIN_ALLOW_THREADS
                if (is_two_plane) {
                    dispatch_dequantization_kernel_mamba_page_2plane(
                        substate_dtype, layer_q_data,
                        page_base0 + l * pages_per_layer * plane_bytes,
                        page_base1 + l * pages_per_layer * plane_bytes, plane_bytes,
                        page_bytes, byte_offset, numel_per_layer, rows_per_page,
                        row_width, col_offset, head_dim, scale_id, args);
                } else {
                    dispatch_dequantization_kernel_mamba_page(
                        substate_dtype, layer_q_data, page_base + l * pages_per_layer * page_bytes,
                        page_bytes, byte_offset, numel_per_layer, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
                }
                Py_END_ALLOW_THREADS
                clear_scales_for_id_impl(scale_id);
            } catch (...) {
                clear_scales_for_id_impl(scale_id);
                throw;
            }
        }
    } else {
        try {
            set_scales_for_id_impl(scale_id, scales);
            Py_BEGIN_ALLOW_THREADS
            if (is_two_plane) {
                dispatch_dequantization_kernel_mamba_page_2plane(
                    substate_dtype, q_contig, page_base0, page_base1, plane_bytes,
                    page_bytes, byte_offset, numel, rows_per_page, row_width,
                    col_offset, head_dim, scale_id, args);
            } else {
                dispatch_dequantization_kernel_mamba_page(
                    substate_dtype, q_contig, page_base, page_bytes, byte_offset,
                    numel, rows_per_page, row_width, col_offset, head_dim, scale_id, args);
            }
            Py_END_ALLOW_THREADS
            clear_scales_for_id_impl(scale_id);
        } catch (...) {
            clear_scales_for_id_impl(scale_id);
            throw;
        }
    }
}

// Reorder [layers, tokens, H*D] into [layers*H, tokens, D] (OpenMP).
torch::Tensor kvweave_split_fused_heads_py(
    torch::Tensor src,
    int64_t head_num,
    int64_t head_dim,
    int num_threads = 0,
    c10::optional<torch::Tensor> out_opt = c10::nullopt
) {
    ensure_cpu_tensor(src, "src");
    auto src_contig = src.contiguous();
    if (src_contig.dim() != 3) {
        throw std::invalid_argument("src must be a 3-D [layers, tokens, head_num*head_dim] tensor");
    }
    int64_t layers = src_contig.size(0);
    int64_t tokens = src_contig.size(1);
    int64_t hidden = src_contig.size(2);
    if (hidden != head_num * head_dim) {
        throw std::invalid_argument("src's trailing dim must equal head_num * head_dim");
    }

    torch::Tensor dst;
    if (out_opt.has_value() && out_opt->defined()) {
        dst = *out_opt;
        std::vector<int64_t> expected = {layers * head_num, tokens, head_dim};
        if (dst.sizes().vec() != expected || dst.scalar_type() != src_contig.scalar_type() || !dst.is_contiguous()) {
            throw std::invalid_argument("out does not match the expected split shape/dtype/contiguity");
        }
    } else {
        dst = torch::empty({layers * head_num, tokens, head_dim}, src_contig.options());
    }

    AT_DISPATCH_FLOATING_TYPES_AND2(
        at::kHalf, at::kBFloat16, src_contig.scalar_type(), "kvweave_split_fused_heads", [&] {
            Py_BEGIN_ALLOW_THREADS
            split_fused_attention_heads_native<scalar_t>(
                src_contig.data_ptr<scalar_t>(), dst.data_ptr<scalar_t>(),
                layers, tokens, head_num, head_dim, num_threads
            );
            Py_END_ALLOW_THREADS
        }
    );
    return dst;
}

// Inverse of kvweave_split_fused_heads_py: merges
// [layers*head_num, tokens, head_dim] back into [layers, tokens, head_num*head_dim].
torch::Tensor kvweave_merge_fused_heads_py(
    torch::Tensor src,
    int64_t layers,
    int64_t head_num,
    int64_t head_dim,
    int num_threads = 0,
    c10::optional<torch::Tensor> out_opt = c10::nullopt
) {
    ensure_cpu_tensor(src, "src");
    auto src_contig = src.contiguous();
    if (src_contig.dim() != 3) {
        throw std::invalid_argument("src must be a 3-D [layers*head_num, tokens, head_dim] tensor");
    }
    int64_t tokens = src_contig.size(1);
    if (src_contig.size(0) != layers * head_num || src_contig.size(2) != head_dim) {
        throw std::invalid_argument("src shape does not match layers*head_num, head_dim");
    }

    torch::Tensor dst;
    if (out_opt.has_value() && out_opt->defined()) {
        dst = *out_opt;
        std::vector<int64_t> expected = {layers, tokens, head_num * head_dim};
        if (dst.sizes().vec() != expected || dst.scalar_type() != src_contig.scalar_type() || !dst.is_contiguous()) {
            throw std::invalid_argument("out does not match the expected merged shape/dtype/contiguity");
        }
    } else {
        dst = torch::empty({layers, tokens, head_num * head_dim}, src_contig.options());
    }

    AT_DISPATCH_FLOATING_TYPES_AND2(
        at::kHalf, at::kBFloat16, src_contig.scalar_type(), "kvweave_merge_fused_heads", [&] {
            Py_BEGIN_ALLOW_THREADS
            merge_fused_attention_heads_native<scalar_t>(
                src_contig.data_ptr<scalar_t>(), dst.data_ptr<scalar_t>(),
                layers, tokens, head_num, head_dim, num_threads
            );
            Py_END_ALLOW_THREADS
        }
    );
    return dst;
}

// Quantizes fused [layers, tokens, head_num*head_dim] attention without a head
// split. Payload bytes match kvweave_serialize_chunk_state run on the split
// [layers*head_num, tokens, head_dim] tensor (scale entries are emitted in index order).
pybind11::object kvweave_serialize_fused_chunk_direct_py(
    torch::Tensor src,
    pybind11::bytes header_bytes,
    int qbit,
    int64_t head_num,
    int64_t head_dim,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads,
    c10::optional<torch::Tensor> out_opt
) {
    ensure_cpu_tensor(src, "src");
    auto src_contig = src.contiguous();
    if (src_contig.dim() != 3) {
        throw std::invalid_argument("src must be a 3-D [layers, tokens, head_num*head_dim] tensor");
    }
    const int64_t layers = src_contig.size(0);
    const int64_t tokens = src_contig.size(1);
    const int64_t hidden = src_contig.size(2);
    if (layers <= 0 || tokens <= 0 || head_num <= 0 || head_dim <= 0 || hidden != head_num * head_dim) {
        throw std::invalid_argument("src's trailing dim must equal head_num * head_dim");
    }
    if (qbit < 2 || qbit > 8) {
        throw std::invalid_argument("direct fused quantization supports qbit in [2, 8]");
    }
    const bool per_channel = scaling_method == "per_channel";
    if (!per_channel && scaling_method != "per_token") {
        throw std::invalid_argument("direct fused quantization supports per_channel/per_token only");
    }
    if (qbit == 4 && (head_dim % 2) != 0) {
        throw std::invalid_argument("4-bit direct fused quantization requires an even head_dim");
    }
    const auto dtype = src_contig.scalar_type();
    if (dtype != torch::kHalf && dtype != torch::kBFloat16 && dtype != torch::kFloat32) {
        throw std::invalid_argument("src dtype must be float16, bfloat16 or float32");
    }

    fused_direct_params params;
    params.layers = layers;
    params.tokens = tokens;
    params.head_num = head_num;
    params.head_dim = head_dim;
    params.qbit = qbit;
    params.rh = rh;
    params.asym = asym;
    params.per_channel = per_channel;
    params.num_threads = num_threads;

    const int64_t transform_len = per_channel ? tokens : head_dim;
    if (rh && (transform_len & (transform_len - 1)) != 0) {
        throw std::invalid_argument("rh (Hadamard) requires the transform length to be a power of 2");
    }
    torch::Tensor signs_t, perm_t;
    if (rh && signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        if (signs_t.numel() != transform_len) {
            throw std::invalid_argument("signs length must equal the RH transform length");
        }
        params.signs = signs_t.data_ptr<float>();
    }
    if (rh && perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        if (perm_t.numel() != transform_len) {
            throw std::invalid_argument("perm length must equal the RH transform length");
        }
        const int32_t* perm = perm_t.data_ptr<int32_t>();
        for (int64_t i = 0; i < transform_len; ++i) {
            if (perm[i] < 0 || perm[i] >= transform_len) {
                throw std::invalid_argument("perm entry out of range");
            }
        }
        params.perm = perm;
    }

    const int64_t units = layers * head_num;
    const int64_t nchunks = per_channel ? head_dim : tokens;
    const int64_t unit_elems = tokens * head_dim;
    const int64_t unit_q_bytes = (qbit == 4) ? unit_elems / 2 : unit_elems;
    constexpr size_t entry_size = sizeof(uint32_t) + 2 * sizeof(float);
    const size_t scale_len = static_cast<size_t>(units)
        * (sizeof(uint32_t) + static_cast<size_t>(nchunks) * entry_size);
    if (scale_len > UINT32_MAX) {
        throw std::runtime_error("kvweave scale blob exceeds uint32 length framing limit");
    }
    std::string hdr_str(header_bytes);
    const size_t q_bytes = static_cast<size_t>(units * unit_q_bytes);
    const size_t total = hdr_str.size() + 4u + scale_len + q_bytes;

    pybind11::object result;
    uint8_t* base = nullptr;
    if (out_opt.has_value() && out_opt->defined()) {
        auto& out = *out_opt;
        ensure_cpu_tensor(out, "out");
        if (out.scalar_type() != torch::kUInt8 || !out.is_contiguous()
            || static_cast<size_t>(out.numel()) < total) {
            throw std::invalid_argument("out must be a contiguous uint8 tensor large enough for the payload");
        }
        base = out.data_ptr<uint8_t>();
        result = pybind11::int_(total);
    } else {
        PyObject* raw = PyBytes_FromStringAndSize(nullptr, static_cast<Py_ssize_t>(total));
        if (raw == nullptr) {
            throw pybind11::error_already_set();
        }
        result = pybind11::reinterpret_steal<pybind11::object>(raw);
        base = reinterpret_cast<uint8_t*>(PyBytes_AS_STRING(raw));
    }

    std::memcpy(base, hdr_str.data(), hdr_str.size());
    uint8_t* cursor = base + hdr_str.size();
    const uint32_t scale_len32 = static_cast<uint32_t>(scale_len);
    cursor[0] = static_cast<uint8_t>((scale_len32 >> 24) & 0xFF);
    cursor[1] = static_cast<uint8_t>((scale_len32 >> 16) & 0xFF);
    cursor[2] = static_cast<uint8_t>((scale_len32 >> 8) & 0xFF);
    cursor[3] = static_cast<uint8_t>(scale_len32 & 0xFF);
    uint8_t* scale_blob = cursor + 4;
    int8_t* q_dst = reinterpret_cast<int8_t*>(scale_blob + scale_len);

    std::vector<float> scales(static_cast<size_t>(units * nchunks));
    std::vector<float> zps(static_cast<size_t>(units * nchunks));
    const void* src_ptr = src_contig.data_ptr();
    Py_BEGIN_ALLOW_THREADS
    if (dtype == torch::kHalf) {
        quantize_fused_direct<_Float16>(static_cast<const _Float16*>(src_ptr), q_dst,
                                        scales.data(), zps.data(), params);
    } else if (dtype == torch::kBFloat16) {
        quantize_fused_direct<__bf16>(static_cast<const __bf16*>(src_ptr), q_dst,
                                      scales.data(), zps.data(), params);
    } else {
        quantize_fused_direct<float>(static_cast<const float*>(src_ptr), q_dst,
                                     scales.data(), zps.data(), params);
    }
    Py_END_ALLOW_THREADS

    uint8_t* sp = scale_blob;
    const uint32_t count = static_cast<uint32_t>(nchunks);
    for (int64_t unit = 0; unit < units; ++unit) {
        std::memcpy(sp, &count, sizeof(uint32_t));
        sp += sizeof(uint32_t);
        for (int64_t k = 0; k < nchunks; ++k) {
            const uint32_t idx = static_cast<uint32_t>(k);
            const size_t pos = static_cast<size_t>(unit * nchunks + k);
            std::memcpy(sp, &idx, sizeof(uint32_t));
            sp += sizeof(uint32_t);
            std::memcpy(sp, &scales[pos], sizeof(float));
            sp += sizeof(float);
            std::memcpy(sp, &zps[pos], sizeof(float));
            sp += sizeof(float);
        }
    }
    return result;
}

// Inverse of kvweave_serialize_fused_chunk_direct: dequantizes per-(layer, head)
// unit planes and writes them straight into fused dst [layers, tokens,
// head_num*head_dim], skipping the split-plane temporary and head merge.
void kvweave_dequantize_fused_chunk_direct_py(
    torch::Tensor q_data,
    pybind11::bytes scale_bytes,
    torch::Tensor dst,
    int64_t layers,
    int64_t tokens,
    int64_t head_num,
    int64_t head_dim,
    int qbit,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt,
    int num_threads
) {
    ensure_cpu_tensor(q_data, "q_data");
    ensure_cpu_tensor(dst, "dst");
    if (layers <= 0 || tokens <= 0 || head_num <= 0 || head_dim <= 0) {
        throw std::invalid_argument("layers, tokens, head_num and head_dim must be positive");
    }
    if (qbit < 2 || qbit > 8) {
        throw std::invalid_argument("direct fused dequantization supports qbit in [2, 8]");
    }
    const bool per_channel = scaling_method == "per_channel";
    if (!per_channel && scaling_method != "per_token") {
        throw std::invalid_argument("direct fused dequantization supports per_channel/per_token only");
    }
    if (qbit == 4 && (head_dim % 2) != 0) {
        throw std::invalid_argument("4-bit direct fused dequantization requires an even head_dim");
    }
    const auto dtype = dst.scalar_type();
    if (dtype != torch::kHalf && dtype != torch::kBFloat16 && dtype != torch::kFloat32) {
        throw std::invalid_argument("dst dtype must be float16, bfloat16 or float32");
    }
    if (!dst.is_contiguous() || dst.numel() != layers * tokens * head_num * head_dim) {
        throw std::invalid_argument("dst must be contiguous with layers*tokens*head_num*head_dim elements");
    }
    if (q_data.scalar_type() != torch::kInt8 && q_data.scalar_type() != torch::kUInt8) {
        throw std::invalid_argument("q_data must be int8 or uint8");
    }
    auto q_contig = q_data.contiguous();
    const int64_t units = layers * head_num;
    const int64_t unit_elems = tokens * head_dim;
    const int64_t unit_q_bytes = (qbit == 4) ? unit_elems / 2 : unit_elems;
    // Trailing bytes (e.g. SHM slot padding) are allowed and ignored.
    if (q_contig.numel() < units * unit_q_bytes) {
        throw std::invalid_argument("q_data is smaller than expected for the fused payload");
    }

    fused_direct_params params;
    params.layers = layers;
    params.tokens = tokens;
    params.head_num = head_num;
    params.head_dim = head_dim;
    params.qbit = qbit;
    params.rh = rh;
    params.asym = asym;
    params.per_channel = per_channel;
    params.num_threads = num_threads;

    const int64_t transform_len = per_channel ? tokens : head_dim;
    if (rh && (transform_len & (transform_len - 1)) != 0) {
        throw std::invalid_argument("rh (Hadamard) requires the transform length to be a power of 2");
    }
    torch::Tensor signs_t, perm_t;
    if (rh && signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).contiguous();
        if (signs_t.numel() != transform_len) {
            throw std::invalid_argument("signs length must equal the RH transform length");
        }
        params.signs = signs_t.data_ptr<float>();
    }
    if (rh && perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).contiguous();
        if (perm_t.numel() != transform_len) {
            throw std::invalid_argument("perm length must equal the RH transform length");
        }
        const int32_t* perm = perm_t.data_ptr<int32_t>();
        for (int64_t i = 0; i < transform_len; ++i) {
            if (perm[i] < 0 || perm[i] >= transform_len) {
                throw std::invalid_argument("perm entry out of range");
            }
        }
        params.perm = perm;
    }

    const int64_t nchunks = per_channel ? head_dim : tokens;
    constexpr size_t entry_size = sizeof(uint32_t) + 2 * sizeof(float);
    const std::string blob(scale_bytes);
    std::vector<float> scales(static_cast<size_t>(units * nchunks), 0.0f);
    std::vector<float> zps(static_cast<size_t>(units * nchunks), 0.0f);
    size_t off = 0;
    for (int64_t unit = 0; unit < units; ++unit) {
        uint32_t count = 0;
        if (off + sizeof(uint32_t) > blob.size()) {
            throw std::invalid_argument("scale blob too short for the fused payload");
        }
        std::memcpy(&count, blob.data() + off, sizeof(uint32_t));
        off += sizeof(uint32_t);
        if (static_cast<int64_t>(count) != nchunks
            || off + static_cast<size_t>(count) * entry_size > blob.size()) {
            throw std::invalid_argument("scale blob does not match the fused payload layout");
        }
        for (uint32_t k = 0; k < count; ++k) {
            uint32_t idx = 0;
            std::memcpy(&idx, blob.data() + off, sizeof(uint32_t));
            if (idx >= count) {
                throw std::invalid_argument("scale blob chunk index out of range");
            }
            const size_t pos = static_cast<size_t>(unit * nchunks + idx);
            std::memcpy(&scales[pos], blob.data() + off + sizeof(uint32_t), sizeof(float));
            std::memcpy(&zps[pos], blob.data() + off + sizeof(uint32_t) + sizeof(float), sizeof(float));
            off += entry_size;
        }
    }

    const int8_t* q_ptr = reinterpret_cast<const int8_t*>(q_contig.data_ptr());
    void* dst_ptr = dst.data_ptr();
    Py_BEGIN_ALLOW_THREADS
    if (dtype == torch::kHalf) {
        dequantize_fused_direct<_Float16>(q_ptr, static_cast<_Float16*>(dst_ptr),
                                          scales.data(), zps.data(), params);
    } else if (dtype == torch::kBFloat16) {
        dequantize_fused_direct<__bf16>(q_ptr, static_cast<__bf16*>(dst_ptr),
                                        scales.data(), zps.data(), params);
    } else {
        dequantize_fused_direct<float>(q_ptr, static_cast<float*>(dst_ptr),
                                       scales.data(), zps.data(), params);
    }
    Py_END_ALLOW_THREADS
}

PYBIND11_MODULE(kvweave_quant, m) {
    m.attr("MAMBA_FUSED_SCALING") = true;
    m.doc() = "PyBind11 bindings for kvweave quantization utilities";

    m.attr("__compiler__") = KVWEAVE_BUILD_COMPILER;
    m.attr("__isa__") = KVWEAVE_BUILD_ISA;
    m.attr("__multithread__") = static_cast<bool>(KVWEAVE_BUILD_MULTITHREAD);

    m.def(
        "build_info",
        []() {
            pybind11::dict info;
            info["compiler"] = KVWEAVE_BUILD_COMPILER;
            info["isa"] = KVWEAVE_BUILD_ISA;
            info["multithread"] = static_cast<bool>(KVWEAVE_BUILD_MULTITHREAD);
#ifdef __INTEL_LLVM_COMPILER
            info["intel_llvm_compiler"] = __INTEL_LLVM_COMPILER;
#else
            info["intel_llvm_compiler"] = pybind11::none();
#endif
#ifdef __GNUC__
            info["gnu_major"] = __GNUC__;
            info["gnu_minor"] = __GNUC_MINOR__;
#endif
            return info;
        },
        "Return compiler, ISA, and threading metadata for this extension build."
    );

    m.def(
        "get_scales_for_id",
        [](int64_t scale_id) -> pybind11::bytes {
            std::string buf = get_scales_bytes_for_id(scale_id);
            return pybind11::bytes(buf);
        },
        pybind11::arg("scale_id"),
        R"doc(Serialize all scale/zeropoint entries for a given scale_id from the thread-local maps.

Returns bytes packed as: [uint32 count][ {uint32 chunk_idx, float scale, float zp} × count ].
Must be called from the same thread that called quantize_kvcache() with scale_id.)doc"
    );

    m.def(
        "clear_scales_for_id",
        [](int64_t scale_id) {
            clear_scales_for_id_impl(scale_id);
        },
        pybind11::arg("scale_id"),
        R"doc(Remove all scale/zeropoint entries for a given scale_id from the thread-local maps.

Call this after get_scales_for_id() to prevent unbounded memory growth in
long-running processes.)doc"
    );

    m.def(
        "set_scales_for_id",
        [](int64_t scale_id, pybind11::bytes data) {
            set_scales_for_id_impl(scale_id, std::string(data));
        },
        pybind11::arg("scale_id"),
        pybind11::arg("data"),
        R"doc(Restore scale/zeropoint entries into the thread-local maps under a new scale_id.

data must be bytes produced by get_scales_for_id().  After this call,
dequantize_kvcache() invoked with scale_id from the same thread will find
the restored scales.)doc"
    );

    m.def(
        "quantize_kvcache",
        &quantize_kvcache_py,
        pybind11::arg("src"),
        pybind11::arg("scale_id"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_token",
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        R"doc(Quantize a KV-cache tensor using kvweave's block quantization kernels.

Arguments:
    src (torch.Tensor): Float/half/BFloat16 tensor on CPU.
    scale_id (int): Identifier used to index cached scales.
    qbit (int): Bit-width (<=8 -> int8, else int16 outputs).
    blocks_num, block_size, head_num, head_dim: Layout metadata.
    rh (bool): Apply randomized Hadamard transform before quantization.
    asym (bool): Use asymmetric quantization.
    scaling_method (str): "per_token" or "per_channel".
    signs (torch.Tensor, optional): 1D sign-flip diagonal ({+1,-1}), length = chunk_size.
    perm (torch.Tensor, optional): 1D permutation indices, length = chunk_size.
    num_threads (int): OpenMP thread count for this call. 0 = omp_get_max_threads().
        Set to 1 when called from a multi-worker pool to avoid oversubscription.
)doc"
    );

    m.def(
        "dequantize_kvcache",
        &dequantize_kvcache_py,
        pybind11::arg("src"),
        pybind11::arg("scale_id"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_token",
        pybind11::arg("output_dtype"),
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        R"doc(Dequantize an int8/int16 KV-cache tensor using kvweave's block kernels.

Arguments:
    src (torch.Tensor): Quantized tensor (int8/int16) on CPU.
    scale_id (int): Identifier used to index cached scales.
    qbit (int): Bit-width used during quantization.
    blocks_num, block_size, head_num, head_dim: Layout metadata.
    rh (bool): Whether RH transform was applied before quantization.
    asym (bool): Whether asymmetric quantization was used.
    scaling_method (str): "per_token" or "per_channel".
    output_dtype (torch.dtype): Destination dtype (float32/float16/bfloat16).
    signs (torch.Tensor, optional): 1D sign-flip diagonal ({+1,-1}), length = chunk_size.
    perm (torch.Tensor, optional): 1D permutation indices, length = chunk_size.
    num_threads (int): OpenMP thread count for this call. 0 = omp_get_max_threads().
        Set to 1 when called from a multi-worker pool to avoid oversubscription.
)doc"
    );

    m.def(
        "kvweave_dequantize_chunk",
        &kvweave_dequantize_chunk_py,
        pybind11::arg("q_data"),
        pybind11::arg("k_scale_bytes"),
        pybind11::arg("v_scale_bytes"),
        pybind11::arg("num_layers"),
        pybind11::arg("chunk_tokens"),
        pybind11::arg("h_merged"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_token",
        pybind11::arg("output_dtype"),
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        R"doc(Dequantize K+V quant payloads and return [2, L, T, H] in one call.

This is a fused Python/C++ API boundary over the existing per-half kernels. It
reduces Python overhead and intermediate copies while preserving the same math.
)doc"
    );

    m.def(
        "kvweave_dequantize_chunk_into_4d",
        &kvweave_dequantize_chunk_into_4d_py,
        pybind11::arg("q_data"),
        pybind11::arg("k_scale_bytes"),
        pybind11::arg("v_scale_bytes"),
        pybind11::arg("dst"),
        pybind11::arg("num_layers"),
        pybind11::arg("chunk_tokens"),
        pybind11::arg("h_merged"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_token",
        pybind11::arg("output_dtype"),
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        pybind11::arg("layer_num_threads") = 1,
        R"doc(Dequantize K+V quant payloads directly into contiguous [2, L, T, H] dst.

This path writes each half into its final destination layout and avoids the
    extra allocate-and-copy step used by kvweave_dequantize_chunk().

    For multi-layer per_token/per_channel/per_tensor payloads, `layer_num_threads`
    can be used to parallelize the per-layer loop experimentally instead of relying
    only on the inner block-level dequant threading.
)doc"
    );

    // All-in-one serialize (quantize + pack header+scales+qdata in C++).
    m.def(
        "kvweave_serialize_chunk",
        &kvweave_serialize_chunk_py,
        pybind11::arg("src"),
        pybind11::arg("header_bytes"),
        pybind11::arg("scale_id_k"),
        pybind11::arg("scale_id_v"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("num_layers") = static_cast<int64_t>(1),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_token",
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        R"doc(Quantize K+V and pack complete KVW2 payload in C++.

Eliminates Python GIL-held buffer copies (bytearray() + tobytes()).
The GIL is released for each quantization kernel, allowing 8 workers
to run their quant kernels in parallel.

Arguments:
    src (torch.Tensor): [2, L, T, H*D] contiguous CPU tensor (fp16/bf16/fp32).
    header_bytes (bytes): Pre-built KVW2 header (magic+metadata+precond+shape).
    scale_id_k, scale_id_v (int): Unique scale IDs for K and V halves.
    qbit, blocks_num, block_size: Layout metadata.
    num_layers (int): Number of layers packed in the tensor. When > 1 with
        per_token/per_channel/per_tensor, quantization is always done
        per-layer, so each layer gets its own independent scale (also
        satisfies the power-of-2 Hadamard constraint when rh is enabled).
    head_num, head_dim: Head layout metadata.
    rh (bool): Use RH transform.
    asym (bool): Use asymmetric quantization.
    scaling_method (str): "per_token" or "per_channel".
    signs, perm (torch.Tensor, optional): Preconditioning tensors.
    num_threads (int): OpenMP threads. 0 = omp_get_max_threads().

Returns: bytes — complete KVW2 payload (header + scales + q_data),
         ready for isal compression or direct disk write.
)doc"
    );

    m.def(
        "kvweave_serialize_chunk_state",
        &kvweave_serialize_chunk_state_py,
        pybind11::arg("src"),
        pybind11::arg("header_bytes"),
        pybind11::arg("scale_id"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("num_layers") = static_cast<int64_t>(1),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_token",
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        R"doc(Quantize a single tensor (no K/V split) and pack a complete payload in C++.

Single-tensor analog of kvweave_serialize_chunk, for payloads with no real
K/V split (e.g. Mamba conv_state/ssm_state).

Arguments:
    src (torch.Tensor): contiguous CPU tensor (fp16/bf16/fp32), no leading K/V axis.
    header_bytes (bytes): Pre-built header (magic+metadata+precond+shape).
    scale_id (int): Unique scale ID for this call.
    qbit, blocks_num, block_size, head_num, head_dim: Layout metadata.
    num_layers (int): Number of layers packed in the tensor. When > 1 with
        per_token/per_channel/per_tensor, quantization is always done
        per-layer, so each layer gets its own independent scale (also
        satisfies the power-of-2 Hadamard constraint when rh is enabled).
    rh (bool): Use RH transform.
    asym (bool): Use asymmetric quantization.
    scaling_method (str): "per_token", "per_channel", or "per_tensor".
    signs, perm (torch.Tensor, optional): Preconditioning tensors.
    num_threads (int): OpenMP threads. 0 = omp_get_max_threads().

    rh (bool): Apply randomized Hadamard preconditioning. RH uses a
        contiguous native scratch sub-state; the RH-disabled path remains
        zero-copy. ``signs`` and ``perm`` are required when RH is enabled.

Returns: bytes — complete payload (header + scale_section + q_data).
)doc"
    );

    m.def(
        "kvweave_dequantize_chunk_state",
        &kvweave_dequantize_chunk_state_py,
        pybind11::arg("q_data"),
        pybind11::arg("scale_bytes"),
        pybind11::arg("num_layers"),
        pybind11::arg("chunk_tokens"),
        pybind11::arg("h_merged"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_token",
        pybind11::arg("output_dtype"),
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        R"doc(Dequantize a single-tensor (no K/V split) quant payload in one call.

Single-tensor analog of kvweave_dequantize_chunk, for payloads with no real
K/V split (e.g. Mamba conv_state/ssm_state). Returns shape
[num_layers, chunk_tokens, h_merged].
)doc"
    );

    m.def(
        "kvweave_serialize_mamba_page_substate",
        &kvweave_serialize_mamba_page_substate_py,
        pybind11::arg("raw"),
        pybind11::arg("page_bytes"),
        pybind11::arg("byte_offset"),
        pybind11::arg("byte_length"),
        pybind11::arg("layers"),
        pybind11::arg("blocks"),
        pybind11::arg("is_two_plane"),
        pybind11::arg("header_bytes"),
        pybind11::arg("scale_id"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("num_layers") = static_cast<int64_t>(1),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_token",
        pybind11::arg("substate_dtype"),
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        R"doc(Gather one Mamba sub-state's bytes directly out of an opaque page
tensor (C++ memcpy loop) and quantize it in the same call.

Payload bytes are bit-identical to calling
_KVWeaveCodec.split_mamba_chunk followed by kvweave_serialize_chunk_state
on the recovered sub-state tensor -- this only replaces the Python-level
strided copy_() with a tighter C++ gather, it does not change the wire
format or the quantization math.

Arguments:
    raw (torch.Tensor): the opaque CPU page tensor (contiguous), shape
        [layers, blocks*block_size, hidden].
    page_bytes (int): bytes per (layer, block) page.
    byte_offset, byte_length (int): the sub-state's byte range within one
        page (same semantics as MambaSubStateWireLayout).
    layers, blocks (int): opaque page's logical layer/block counts.
    is_two_plane (bool): must be False -- two-plane pages are not yet
        supported by this entry point; callers must fall back to
        split_mamba_chunk for those.
    header_bytes, scale_id, qbit, blocks_num, block_size, head_num,
    head_dim, num_layers, rh, asym, scaling_method, signs, perm,
    num_threads: same as kvweave_serialize_chunk_state.
    substate_dtype (torch.dtype): the sub-state's real dtype (may differ
        from raw's dtype -- the gathered bytes are reinterpreted as this
        dtype before quantizing).

Returns: bytes — complete payload (header + scale_section + q_data).
)doc"
    );

    m.def(
        "kvweave_dequantize_mamba_page_substate",
        &kvweave_dequantize_mamba_page_substate_py,
        pybind11::arg("q_data"),
        pybind11::arg("scale_bytes"),
        pybind11::arg("out"),
        pybind11::arg("page_bytes"),
        pybind11::arg("byte_offset"),
        pybind11::arg("byte_length"),
        pybind11::arg("layers"),
        pybind11::arg("blocks"),
        pybind11::arg("is_two_plane"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_token",
        pybind11::arg("substate_dtype"),
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        R"doc(Dequantize one Mamba sub-state payload and scatter it directly into
the caller's opaque page tensor (C++ memcpy loop), in place.

Mirrors kvweave_serialize_mamba_page_substate: writes bytes identical to
calling kvweave_dequantize_chunk_state followed by
_KVWeaveCodec.merge_mamba_chunk's out= write path -- only the scatter
implementation differs (C++ memcpy vs. Python slice-assign).

Arguments:
    q_data, scale_bytes: quantized payload pieces (as produced by
        kvweave_serialize_mamba_page_substate or kvweave_serialize_chunk_state).
    out (torch.Tensor): contiguous CPU opaque page tensor to write into,
        shape [layers, blocks*block_size, hidden]. Modified in place.
    page_bytes, byte_offset, byte_length, layers, blocks, is_two_plane:
        same as kvweave_serialize_mamba_page_substate (is_two_plane must
        be False).
        qbit, blocks_num, block_size, head_num, head_dim, asym,
        scaling_method, num_threads: same as kvweave_dequantize_chunk_state.
        rh (bool): Apply inverse randomized Hadamard preconditioning using the
            supplied signs and perm tensors. RH uses a contiguous native
            scratch sub-state; the RH-disabled path remains zero-copy.
    substate_dtype (torch.dtype): the sub-state's real dtype.

Returns: None (writes into out).
)doc"
    );

    m.def(
        "kvweave_serialize_mamba_page_substate_direct",
        &kvweave_serialize_mamba_page_substate_direct_py,
        pybind11::arg("raw"),
        pybind11::arg("page_bytes"),
        pybind11::arg("byte_offset"),
        pybind11::arg("row_width"),
        pybind11::arg("rows_per_page_hint"),
        pybind11::arg("layers"),
        pybind11::arg("blocks"),
        pybind11::arg("is_two_plane"),
        pybind11::arg("header_bytes"),
        pybind11::arg("scale_id"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_channel",
        pybind11::arg("substate_dtype"),
        pybind11::arg("col_offset") = static_cast<int64_t>(0),
        pybind11::arg("num_threads") = 0,
        pybind11::arg("rh") = false,
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        R"doc(Quantize one Mamba sub-state (or a column sub-range of one, e.g.
one of conv's q/k/v segments) directly out of an opaque page tensor.

Supports per_channel/per_token with or without RH, including column
sub-ranges (conv Q/K/V) and element-aligned two-plane pages. For qbit 4/8,
eligible token rows or channel tiles fuse page access, optional RH and
packing across layers, with per-thread scratch instead of a full sub-state.
Int4 requires even head_dim for fused packing; other geometries retain the
standard kernels. Per_tensor retains its existing paths and restrictions.
Payloads preserve the standard Mamba wire format; scale entries may be
serialized in index order.

Arguments:
    raw (torch.Tensor): the opaque CPU page tensor (contiguous), shape
        [layers, blocks*block_size, hidden].
    page_bytes (int): bytes per (layer, block) page.
    byte_offset (int): the sub-state's region's byte offset within one page
        (where row 0, column 0 of row_width starts).
    row_width (int): real number of elements per logical row in the
        sub-state's region (e.g. Mamba conv's full conv_dim). May exceed
        head_dim when col_offset selects a sub-range of each row.
    rows_per_page_hint (int): number of row_width-wide rows per page.
    layers, blocks (int): opaque page's logical layer/block counts.
    is_two_plane (bool): when True, `raw` must be shaped
        [2, layers, blocks*block_size, hidden] (vLLM's two-plane KV
        layout -- raw[0]/raw[1] are each treated as a page_bytes/2-sized
        plane). Without RH per_channel/per_token are supported (ssm is
        the only substate expected to need this; conv always fits in plane
        0, so callers should pass raw[0] as a single-plane 3-D tensor with
        page_bytes halved for conv instead of setting this True). When
        False, `raw` is the single-plane 3-D tensor as before.
    header_bytes, scale_id, qbit, blocks_num, block_size, head_num,
    asym, scaling_method, num_threads: same as kvweave_serialize_chunk_state.
    head_dim (int): width of the segment actually being quantized (equals
        row_width when col_offset=0).
    rh (bool): Apply RH using the supplied signs and perm tensors.
    signs, perm (torch.Tensor, optional): Required when rh=True.
    substate_dtype (torch.dtype): the sub-state's real dtype (may differ
        from raw's dtype -- read bytes are reinterpreted as this dtype
        before quantizing).
    col_offset (int): starting column within each row_width-wide row where
        the head_dim-wide segment begins (0 for substates with no sub-row
        split, e.g. ssm; > 0 to select e.g. conv's key or value segment).

Returns: bytes — complete payload (header + scale_section + q_data).
)doc"
    );

    m.def(
        "kvweave_dequantize_mamba_page_substate_direct",
        &kvweave_dequantize_mamba_page_substate_direct_py,
        pybind11::arg("q_data"),
        pybind11::arg("scale_bytes"),
        pybind11::arg("out"),
        pybind11::arg("page_bytes"),
        pybind11::arg("byte_offset"),
        pybind11::arg("row_width"),
        pybind11::arg("rows_per_page_hint"),
        pybind11::arg("layers"),
        pybind11::arg("blocks"),
        pybind11::arg("is_two_plane"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_channel",
        pybind11::arg("substate_dtype"),
        pybind11::arg("col_offset") = static_cast<int64_t>(0),
        pybind11::arg("num_threads") = 0,
        pybind11::arg("rh") = false,
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        R"doc(Dequantize one Mamba sub-state (or column sub-range) payload
directly into an opaque page tensor.

Mirrors kvweave_serialize_mamba_page_substate_direct -- see its docstring
for row_width/col_offset/is_two_plane semantics. Eligible per_token rows and
per_channel tiles fuse optional inverse RH and page scatter using per-thread
scratch; other geometries retain the standard kernels.
With RH disabled, it scatters directly from the native kernel into the page.

    rh (bool): Apply inverse RH using the supplied signs and perm tensors.
    signs, perm (torch.Tensor, optional): Required when rh=True.

Returns: None (writes into out).
)doc"
    );

    m.def(
        "kvweave_split_fused_heads",
        &kvweave_split_fused_heads_py,
        pybind11::arg("src"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("num_threads") = 0,
        pybind11::arg("out") = c10::optional<torch::Tensor>(),
        R"doc(Reorder [layers, tokens, head_num*head_dim] into
[layers*head_num, tokens, head_dim] via a native OpenMP-parallel copy --
an alternative to _KVWeaveCodec.split_fused_attention_heads's ATen
permute()/reshape()/copy_() for the same reorder. Pass `out` to write
directly into a pre-allocated buffer instead of allocating a fresh tensor.
)doc"
    );

    m.def(
        "kvweave_merge_fused_heads",
        &kvweave_merge_fused_heads_py,
        pybind11::arg("src"),
        pybind11::arg("layers"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("num_threads") = 0,
        pybind11::arg("out") = c10::optional<torch::Tensor>(),
        R"doc(Inverse of kvweave_split_fused_heads: merges
[layers*head_num, tokens, head_dim] back into [layers, tokens, head_num*head_dim].
Pass `out` to write directly into a pre-allocated buffer.
)doc"
    );

    m.def(
        "kvweave_serialize_fused_chunk_direct",
        &kvweave_serialize_fused_chunk_direct_py,
        pybind11::arg("src"),
        pybind11::arg("header_bytes"),
        pybind11::arg("qbit"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_channel",
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        pybind11::arg("out") = c10::optional<torch::Tensor>(),
        R"doc(Quantize fused [layers, tokens, head_num*head_dim] attention per
(layer, head) without a separate head-split copy. Produces the same payload as
kvweave_serialize_chunk_state on the split tensor with num_layers=layers*head_num.
Supports per_channel/per_token. Returns bytes, or the written length when `out`
(contiguous uint8 tensor) is given.
)doc"
    );

    m.def(
        "kvweave_dequantize_fused_chunk_direct",
        &kvweave_dequantize_fused_chunk_direct_py,
        pybind11::arg("q_data"),
        pybind11::arg("scale_bytes"),
        pybind11::arg("dst"),
        pybind11::arg("layers"),
        pybind11::arg("tokens"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("qbit"),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_channel",
        pybind11::arg("signs") = c10::optional<torch::Tensor>(),
        pybind11::arg("perm") = c10::optional<torch::Tensor>(),
        pybind11::arg("num_threads") = 0,
        R"doc(Inverse of kvweave_serialize_fused_chunk_direct: dequantize the per-(layer,
head) q planes + scale blob and write straight into the contiguous fused dst
[layers, tokens, head_num*head_dim] (no split temporary, no head merge).
Supports per_channel/per_token.
)doc"
    );
}
