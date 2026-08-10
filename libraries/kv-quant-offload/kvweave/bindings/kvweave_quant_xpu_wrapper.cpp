// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <torch/extension.h>
#include <c10/xpu/XPUStream.h>
#include <sycl/sycl.hpp>
#include <cstring>
#include <stdexcept>
#include <tuple>
#include <vector>

#include "quant_sycl.hpp"

namespace {

void ensure_xpu_tensor(const torch::Tensor& tensor, const char* name) {
    if (!tensor.device().is_xpu()) {
        throw std::invalid_argument(
            std::string(name) + " tensor must reside on XPU.");
    }
}

sycl::queue& get_current_queue() {
    return c10::xpu::getCurrentXPUStream().queue();
}

int64_t packed_size_q4(int64_t logical_count) {
    return (logical_count + 1) / 2;
}

// Serialize scales/zps from host buffer into the same binary format as CPU wrapper.
// Format: count(u32) | [chunk_idx(u32) | scale(f32) | zp(f32)] * count
std::string serialize_scales(const float* scales, const float* zps, int64_t num_chunks) {
    uint32_t count = static_cast<uint32_t>(num_chunks);
    constexpr size_t entry_size = sizeof(uint32_t) + 2 * sizeof(float);
    std::string buf;
    buf.resize(sizeof(uint32_t) + count * entry_size);
    char* ptr = buf.data();
    std::memcpy(ptr, &count, sizeof(uint32_t));
    ptr += sizeof(uint32_t);
    for (uint32_t i = 0; i < count; ++i) {
        std::memcpy(ptr, &i, sizeof(uint32_t));
        ptr += sizeof(uint32_t);
        float s = scales[i];
        float z = zps[i];
        std::memcpy(ptr, &s, sizeof(float));
        ptr += sizeof(float);
        std::memcpy(ptr, &z, sizeof(float));
        ptr += sizeof(float);
    }
    return buf;
}

// Deserialize scale blob into flat scale/zp vectors (ordered by chunk_idx).
void deserialize_scales(
    const std::string& blob,
    std::vector<float>& scales,
    std::vector<float>& zps)
{
    const char* ptr = blob.data();
    const char* end = ptr + blob.size();

    if (static_cast<size_t>(end - ptr) < sizeof(uint32_t)) {
        throw std::invalid_argument("Scale blob too small.");
    }
    uint32_t count = 0;
    std::memcpy(&count, ptr, sizeof(uint32_t));
    ptr += sizeof(uint32_t);

    constexpr size_t entry_size = sizeof(uint32_t) + 2 * sizeof(float);
    if (static_cast<size_t>(end - ptr) < count * entry_size) {
        throw std::invalid_argument("Scale blob truncated.");
    }

    scales.resize(count);
    zps.resize(count);
    for (uint32_t i = 0; i < count; ++i) {
        uint32_t chunk_idx = 0;
        std::memcpy(&chunk_idx, ptr, sizeof(uint32_t));
        ptr += sizeof(uint32_t);
        float s = 0.0f, z = 0.0f;
        std::memcpy(&s, ptr, sizeof(float));
        ptr += sizeof(float);
        std::memcpy(&z, ptr, sizeof(float));
        ptr += sizeof(float);
        if (chunk_idx < count) {
            scales[chunk_idx] = s;
            zps[chunk_idx] = z;
        }
    }
}

sycl_quantization_args build_sycl_args(
    int qbit, int blocks_num, int block_size,
    int head_num, int head_dim,
    bool rh, bool asym,
    const std::string& scaling_method)
{
    sycl_quantization_args args;
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

int64_t compute_num_chunks(const sycl_quantization_args& args, int64_t element_count) {
    if (args.scaling_method == "per_token") {
        return static_cast<int64_t>(args.blocks_num) * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        return args.head_dim;
    }
    return 1;
}

// Dispatch quantize by input dtype
template<typename QType>
sycl::event dispatch_quantize_by_kvtype(
    sycl::queue& q,
    const torch::Tensor& src,
    QType* dst,
    float* scales_out,
    float* zps_out,
    int64_t element_count,
    const sycl_quantization_args& args,
    const std::vector<sycl::event>& deps)
{
    auto src_type = src.scalar_type();
    if (src_type == torch::kFloat16) {
        return quantize_kvcache_sycl<sycl::half, QType>(
            q, reinterpret_cast<const sycl::half*>(src.data_ptr()),
            dst, scales_out, zps_out, element_count, args, deps);
    } else if (src_type == torch::kBFloat16) {
        return quantize_kvcache_sycl<sycl::ext::oneapi::bfloat16, QType>(
            q, reinterpret_cast<const sycl::ext::oneapi::bfloat16*>(src.data_ptr()),
            dst, scales_out, zps_out, element_count, args, deps);
    } else if (src_type == torch::kFloat32) {
        return quantize_kvcache_sycl<float, QType>(
            q, src.data_ptr<float>(),
            dst, scales_out, zps_out, element_count, args, deps);
    }
    throw std::invalid_argument("Unsupported input dtype for XPU quantization.");
}

// Dispatch dequantize by output dtype
template<typename QType>
sycl::event dispatch_dequantize_by_kvtype(
    sycl::queue& q,
    const QType* src,
    torch::Tensor& dst,
    const float* scales_in,
    const float* zps_in,
    int64_t element_count,
    const sycl_quantization_args& args,
    const std::vector<sycl::event>& deps)
{
    auto dst_type = dst.scalar_type();
    if (dst_type == torch::kFloat16) {
        return dequantize_kvcache_sycl<sycl::half, QType>(
            q, src,
            reinterpret_cast<sycl::half*>(dst.data_ptr()),
            scales_in, zps_in, element_count, args, deps);
    } else if (dst_type == torch::kBFloat16) {
        return dequantize_kvcache_sycl<sycl::ext::oneapi::bfloat16, QType>(
            q, src,
            reinterpret_cast<sycl::ext::oneapi::bfloat16*>(dst.data_ptr()),
            scales_in, zps_in, element_count, args, deps);
    } else if (dst_type == torch::kFloat32) {
        return dequantize_kvcache_sycl<float, QType>(
            q, src,
            dst.data_ptr<float>(),
            scales_in, zps_in, element_count, args, deps);
    }
    throw std::invalid_argument("Unsupported output dtype for XPU dequantization.");
}

}  // namespace

// ---------------------------------------------------------------------------
// Public API: quantize_kvcache_xpu
// ---------------------------------------------------------------------------
// Input: XPU tensor (fp16/bf16/fp32)
// Returns: (quantized_xpu_tensor, scale_bytes)
// Scale bytes use the same binary format as CPU wrapper (compatible with KVW3).
std::tuple<torch::Tensor, pybind11::bytes>
quantize_kvcache_xpu(
    torch::Tensor src,
    int qbit,
    int blocks_num,
    int block_size,
    int head_num,
    int head_dim,
    bool rh,
    bool asym,
    const std::string& scaling_method,
    c10::optional<torch::Tensor> signs_opt,
    c10::optional<torch::Tensor> perm_opt)
{
    ensure_xpu_tensor(src, "src");
    auto src_contig = src.contiguous();
    int64_t element_count = src_contig.numel();

    auto args = build_sycl_args(
        qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);

    // Handle preconditioning tensors (move to XPU if needed)
    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).to(src.device()).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).to(src.device()).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    // Allocate output tensor
    auto q_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    int64_t dst_numel = (qbit == 4)
        ? packed_size_q4(element_count)
        : element_count;
    auto dst = torch::empty(
        {dst_numel}, src_contig.options().dtype(q_dtype));

    // Use PyTorch tensors for device scale buffers (avoids sycl::malloc_device leak on iGPU)
    int64_t num_chunks = compute_num_chunks(args, element_count);
    auto scale_opts = src_contig.options().dtype(torch::kFloat32);
    auto d_scales_t = torch::empty({num_chunks}, scale_opts);
    auto d_zps_t = torch::zeros({num_chunks}, scale_opts);
    float* d_scales = d_scales_t.data_ptr<float>();
    float* d_zps = d_zps_t.data_ptr<float>();

    // Launch quantize kernel
    auto& queue = get_current_queue();
    sycl::event quant_event;
    if (qbit <= 8) {
        quant_event = dispatch_quantize_by_kvtype<int8_t>(
            queue, src_contig,
            reinterpret_cast<int8_t*>(dst.data_ptr()),
            d_scales, d_zps, element_count, args, {});
    } else {
        quant_event = dispatch_quantize_by_kvtype<int16_t>(
            queue, src_contig,
            reinterpret_cast<int16_t*>(dst.data_ptr()),
            d_scales, d_zps, element_count, args, {});
    }
    quant_event.wait();

    // Copy scales/zps to host
    std::vector<float> h_scales(num_chunks);
    std::vector<float> h_zps(num_chunks);
    queue.memcpy(h_scales.data(), d_scales, num_chunks * sizeof(float)).wait();
    queue.memcpy(h_zps.data(), d_zps, num_chunks * sizeof(float)).wait();

    // Serialize to the same format as CPU wrapper
    std::string scale_blob = serialize_scales(
        h_scales.data(), h_zps.data(), num_chunks);

    return std::make_tuple(dst, pybind11::bytes(scale_blob));
}

// ---------------------------------------------------------------------------
// Public API: dequantize_kvcache_xpu
// ---------------------------------------------------------------------------
// Input: XPU quantized tensor + scale bytes
// Returns: dequantized XPU tensor (fp16/bf16/fp32)
torch::Tensor dequantize_kvcache_xpu(
    torch::Tensor src,
    pybind11::bytes scale_bytes_py,
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
    c10::optional<torch::Tensor> perm_opt)
{
    ensure_xpu_tensor(src, "src");
    auto src_contig = src.contiguous();

    int64_t element_count = static_cast<int64_t>(blocks_num)
        * block_size * head_num * head_dim;

    auto args = build_sycl_args(
        qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method);

    // Handle preconditioning tensors
    torch::Tensor signs_t, perm_t;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_t = signs_opt->to(torch::kFloat32).to(src.device()).contiguous();
        args.signs = signs_t.data_ptr<float>();
    }
    if (perm_opt.has_value() && perm_opt->defined()) {
        perm_t = perm_opt->to(torch::kInt32).to(src.device()).contiguous();
        args.perm = perm_t.data_ptr<int32_t>();
    }

    // Allocate output tensor
    auto dst = torch::empty(
        {element_count},
        src_contig.options().dtype(output_dtype));

    // Deserialize scales from blob
    std::string scale_blob(scale_bytes_py);
    std::vector<float> h_scales, h_zps;
    deserialize_scales(scale_blob, h_scales, h_zps);
    int64_t num_chunks = static_cast<int64_t>(h_scales.size());

    // Use PyTorch tensors for device scale buffers (avoids sycl::malloc_device leak on iGPU)
    auto scale_opts = src_contig.options().dtype(torch::kFloat32);
    auto d_scales_t = torch::from_blob(h_scales.data(), {num_chunks}, torch::kFloat32)
                          .to(scale_opts.device(), /*non_blocking=*/false);
    auto d_zps_t = torch::from_blob(h_zps.data(), {num_chunks}, torch::kFloat32)
                       .to(scale_opts.device(), /*non_blocking=*/false);
    float* d_scales = d_scales_t.data_ptr<float>();
    float* d_zps = d_zps_t.data_ptr<float>();

    // Launch dequantize kernel
    auto& queue = get_current_queue();
    sycl::event dequant_event;
    if (qbit <= 8) {
        dequant_event = dispatch_dequantize_by_kvtype<int8_t>(
            queue,
            reinterpret_cast<const int8_t*>(src_contig.data_ptr()),
            dst, d_scales, d_zps, element_count, args, {});
    } else {
        dequant_event = dispatch_dequantize_by_kvtype<int16_t>(
            queue,
            reinterpret_cast<const int16_t*>(src_contig.data_ptr()),
            dst, d_scales, d_zps, element_count, args, {});
    }
    dequant_event.wait();

    return dst;
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------
PYBIND11_MODULE(kvweave_quant_xpu, m) {
    m.doc() = "KVWeave XPU quantization kernels (SYCL/DPC++)";

    m.def("quantize_kvcache", &quantize_kvcache_xpu,
        "Quantize KV cache on XPU. Returns (quantized_tensor, scale_bytes).",
        pybind11::arg("src"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("rh"),
        pybind11::arg("asym"),
        pybind11::arg("scaling_method"),
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt);

    m.def("dequantize_kvcache", &dequantize_kvcache_xpu,
        "Dequantize KV cache on XPU. Returns restored tensor.",
        pybind11::arg("src"),
        pybind11::arg("scale_bytes"),
        pybind11::arg("qbit"),
        pybind11::arg("blocks_num"),
        pybind11::arg("block_size"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("rh"),
        pybind11::arg("asym"),
        pybind11::arg("scaling_method"),
        pybind11::arg("output_dtype"),
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt);
}
