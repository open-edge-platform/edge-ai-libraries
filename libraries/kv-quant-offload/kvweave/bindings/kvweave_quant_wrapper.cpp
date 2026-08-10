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
    // Release the GIL during the kernel using Python C API.
    // Py_BEGIN_ALLOW_THREADS/Py_END_ALLOW_THREADS only use PyEval_SaveThread /
    // PyEval_RestoreThread, avoiding the pybind11 TensorImpl::decref_pyobject
    // symbol that is missing from PyTorch 2.9.0+xpu.
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
        ScaleIdGuard guard(scale_id, layer_scales[l]);
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

// Fused API-boundary dequantization for a layerwise K/V chunk.
// This still uses the existing per-half dequant kernels internally, but avoids
// two Python calls, two Python scale-map restore/clear sequences, two bytearray
// slice copies, and the Python-side torch.stack().
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

// All-in-one serialize — quantize K+V and pack KVW2 payload in C++.
// Eliminates Python GIL-held buffer copies (bytearray + tobytes).
// The GIL is released for each quantization kernel.
//
// Arguments:
//   src          : [2, L, T, H*D] contiguous CPU tensor (fp16/bf16/fp32)
//   header_bytes : KVW2 header bytes (magic + metadata + precond + shape),
//                  built once in Python and reused across calls.
//   scale_id_k   : scale ID for K quantization (unique per call)
//   scale_id_v   : scale ID for V quantization (unique per call)
//   qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method,
//   signs, perm, num_threads : quantization parameters (same as quantize_kvcache).
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

    // Make a contiguous copy upfront to ensure we have a pure C++ buffer.
    // Using from_blob on raw data pointers avoids creating Python-backed views
    // (which would emit TensorImpl::decref_pyobject on destruction — a symbol
    // not exported by PyTorch 2.9.0+xpu).
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
    // The scale-blob lengths are framed as 4-byte big-endian fields; guard the
    // size_t -> uint32_t narrowing so an oversized blob fails loudly instead of
    // silently corrupting the framing.
    if (k_scale_data.size() > UINT32_MAX || v_scale_data.size() > UINT32_MAX) {
        throw std::runtime_error(
            "kvweave scale blob exceeds uint32 length framing limit");
    }
    uint32_t k_len = static_cast<uint32_t>(k_scale_data.size());
    uint32_t v_len = static_cast<uint32_t>(v_scale_data.size());
    int item_bytes = (qbit <= 8) ? 1 : 2;

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

// Single-tensor analog of kvweave_serialize_chunk_py, for payloads with no
// real K/V split (e.g. Mamba conv_state/ssm_state). Quantizes the whole
// tensor once (no numel()/2 halving) under one scale_id.
//
// Arguments:
//   src          : contiguous CPU tensor (fp16/bf16/fp32), no leading K/V axis.
//   header_bytes : caller-built header bytes, reused across calls.
//   scale_id     : scale ID for this quantization call (unique per call).
//   qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method,
//   signs, perm, num_threads : quantization parameters (same as quantize_kvcache).
//
// Returns: payload bytes (header + scale_section + q_data).
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
    int item_bytes = (qbit <= 8) ? 1 : 2;

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

// Single-tensor analog of kvweave_dequantize_chunk_py, for payloads with no
// real K/V split. Uses one fixed scale-id sentinel (distinct from the K/V
// function's 0xD001/0xD002) to install/clear the caller-supplied scale bytes.
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

PYBIND11_MODULE(kvweave_quant, m) {
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
}
