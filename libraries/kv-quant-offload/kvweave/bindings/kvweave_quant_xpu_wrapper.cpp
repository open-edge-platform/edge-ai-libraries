// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include <torch/extension.h>
#include <c10/xpu/XPUStream.h>
#include <sycl/sycl.hpp>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <tuple>
#include <unordered_map>
#include <vector>

#include "quant_sycl.hpp"

namespace {

void ensure_xpu_tensor(const torch::Tensor& tensor, const char* name) {
    if (!tensor.device().is_xpu()) {
        throw std::invalid_argument(
            std::string(name) + " tensor must reside on XPU.");
    }
}

void ensure_cpu_tensor(const torch::Tensor& tensor, const char* name) {
    if (!tensor.device().is_cpu()) {
        throw std::invalid_argument(
            std::string(name) + " tensor must reside on CPU.");
    }
}

sycl::queue& get_current_queue() {
    return c10::xpu::getCurrentXPUStream().queue();
}

// RAII guard for sycl::malloc_host (pinned) memory; much faster H2D/D2H for small
// scale transfers than pageable memory.
template <typename T>
class HostScratch {
public:
    HostScratch(int64_t count, sycl::queue& q)
        : ptr_(sycl::malloc_host<T>(static_cast<size_t>(count), q)), q_(q) {}
    ~HostScratch() {
        if (ptr_) sycl::free(ptr_, q_);
    }
    HostScratch(const HostScratch&) = delete;
    HostScratch& operator=(const HostScratch&) = delete;
    T* get() const { return ptr_; }

private:
    T* ptr_;
    sycl::queue& q_;
};

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

// Pack/split per-layer scale segments (byte-compatible with the CPU wrapper).
std::string pack_scale_blob_per_layer(
    const float* scales, const float* zps, int64_t num_layers, int64_t chunks_per_layer) {
    std::string blob;
    for (int64_t l = 0; l < num_layers; ++l) {
        blob += serialize_scales(
            scales + l * chunks_per_layer, zps + l * chunks_per_layer, chunks_per_layer);
    }
    return blob;
}

// Inverse of pack_scale_blob_per_layer; also validates each segment's count.
void parse_scale_blob_per_layer(
    const std::string& blob, int64_t num_layers, int64_t chunks_per_layer,
    std::vector<float>& scales, std::vector<float>& zps) {
    constexpr size_t entry_size = sizeof(uint32_t) + 2 * sizeof(float);
    scales.resize(static_cast<size_t>(num_layers * chunks_per_layer));
    zps.resize(static_cast<size_t>(num_layers * chunks_per_layer));
    size_t offset = 0;
    for (int64_t l = 0; l < num_layers; ++l) {
        if (offset + sizeof(uint32_t) > blob.size()) {
            throw std::invalid_argument("kvweave scale blob too short for per-layer split.");
        }
        uint32_t count = 0;
        std::memcpy(&count, blob.data() + offset, sizeof(uint32_t));
        if (static_cast<int64_t>(count) != chunks_per_layer) {
            throw std::invalid_argument("kvweave scale blob chunk count does not match expected layout.");
        }
        size_t segment_bytes = sizeof(uint32_t) + static_cast<size_t>(count) * entry_size;
        if (offset + segment_bytes > blob.size()) {
            throw std::invalid_argument("kvweave scale blob truncated within a layer segment.");
        }
        std::vector<float> layer_scales, layer_zps;
        deserialize_scales(blob.substr(offset, segment_bytes), layer_scales, layer_zps);
        std::copy(layer_scales.begin(), layer_scales.end(),
                   scales.begin() + l * chunks_per_layer);
        std::copy(layer_zps.begin(), layer_zps.end(),
                   zps.begin() + l * chunks_per_layer);
        offset += segment_bytes;
    }
}

sycl_quantization_args build_sycl_args(
    int qbit, int blocks_num, int block_size,
    int head_num, int head_dim,
    bool rh, bool asym,
    const std::string& scaling_method,
    int64_t num_layers = 1)
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
    args.num_layers = num_layers > 0 ? num_layers : 1;
    return args;
}

int64_t compute_chunks_per_layer(const sycl_quantization_args& args) {
    int64_t chunks_per_layer = 1;
    if (args.scaling_method == "per_token") {
        chunks_per_layer = static_cast<int64_t>(args.blocks_num) * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        chunks_per_layer = args.head_dim;
    }
    return chunks_per_layer;
}

int64_t compute_num_chunks(const sycl_quantization_args& args, [[maybe_unused]] int64_t element_count) {
    const int64_t num_layers = args.num_layers > 0 ? args.num_layers : 1;
    return num_layers * compute_chunks_per_layer(args);
}

int64_t packed_numel_for_qbit(int64_t logical_numel, int qbit) {
    return (qbit == 4) ? packed_size_q4(logical_numel) : logical_numel;
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

// Stage groups per direction (each sums to ~100%).
bool is_quantize_stage(const char* name) {
    return std::string(name) == "LoadGather"
        || std::string(name) == "Hadamard"
        || std::string(name) == "ReduceQuantize"
        || std::string(name) == "Pack4bit";
}

pybind11::dict get_profile_stats_impl() {
    auto stats = quant_profile_snapshot();

    uint64_t quantize_total_ns = 0, dequantize_total_ns = 0;
    for (const auto& s : stats) {
        if (is_quantize_stage(s.name)) {
            quantize_total_ns += s.total_ns;
        } else {
            dequantize_total_ns += s.total_ns;
        }
    }

    pybind11::dict result;
    for (const auto& s : stats) {
        uint64_t group_total = is_quantize_stage(s.name) ? quantize_total_ns : dequantize_total_ns;
        double pct = (group_total > 0)
            ? (100.0 * static_cast<double>(s.total_ns) / static_cast<double>(group_total))
            : 0.0;
        pybind11::dict entry;
        entry["total_ms"] = static_cast<double>(s.total_ns) / 1.0e6;
        entry["calls"] = s.calls;
        entry["pct"] = pct;
        result[s.name] = entry;
    }
    return result;
}

// ---------------------------------------------------------------------------
// Content-keyed LRU cache of device perm/signs (plus inv_perm/signs_reordered).
// Entries are shared_ptr so eviction cannot free tensors in use.
// ---------------------------------------------------------------------------
struct PrecondCacheEntry {
    torch::Tensor perm_cpu;         // caller's perm bytes, kept for hit validation
    torch::Tensor signs_cpu;        // caller's signs bytes (undefined if no signs)
    int64_t device_index = -1;
    uint64_t last_used = 0;
    torch::Tensor perm_device;      // forward perm, cast+moved to device once
    torch::Tensor signs_device;     // forward signs, moved to device once (undefined if no signs)
    torch::Tensor inv_perm;
    torch::Tensor signs_reordered;  // undefined if no signs were provided
};
using PrecondHandle = std::shared_ptr<PrecondCacheEntry>;

constexpr size_t kPrecondCacheCap = 64;

struct PrecondCacheStats {
    uint64_t hits = 0, misses = 0, evictions = 0;
};

std::mutex g_precond_cache_mutex;
std::unordered_map<uint64_t, PrecondHandle> g_precond_cache;
PrecondCacheStats g_precond_stats;
uint64_t g_precond_clock = 0;

// 8 bytes per step (FNV-style multiply); hashes the tensors' raw bytes.
uint64_t hash_bytes(const void* data, size_t bytes, uint64_t h) {
    const auto* p = static_cast<const unsigned char*>(data);
    size_t i = 0;
    for (; i + 8 <= bytes; i += 8) {
        uint64_t w;
        std::memcpy(&w, p + i, 8);
        h = (h ^ w) * 1099511628211ULL;
        h ^= h >> 29;
    }
    for (; i < bytes; ++i) { h = (h ^ p[i]) * 1099511628211ULL; }
    return h;
}

bool same_content(const torch::Tensor& a, const torch::Tensor& b) {
    if (a.defined() != b.defined()) return false;
    if (!a.defined()) return true;
    return a.scalar_type() == b.scalar_type() && a.numel() == b.numel()
        && std::memcmp(a.data_ptr(), b.data_ptr(), static_cast<size_t>(a.nbytes())) == 0;
}

PrecondHandle get_or_build_precond_cache(
    const torch::Tensor& perm_tensor,
    c10::optional<torch::Tensor> signs_opt,
    const torch::Device& device)
{
    // Hash/compare the tensors in whatever dtype they arrive (no conversion
    // on the hit path); dtype conversion happens only when building an entry.
    auto perm_in = perm_tensor.to(torch::kCPU).contiguous();
    torch::Tensor signs_in;
    if (signs_opt.has_value() && signs_opt->defined()) {
        signs_in = signs_opt->to(torch::kCPU).contiguous();
    }
    const int64_t dev_index = device.index();

    const int32_t perm_dtype = static_cast<int32_t>(perm_in.scalar_type());
    uint64_t key = hash_bytes(&dev_index, sizeof(dev_index), 1469598103934665603ULL);
    key = hash_bytes(&perm_dtype, sizeof(perm_dtype), key);
    key = hash_bytes(perm_in.data_ptr(), static_cast<size_t>(perm_in.nbytes()), key);
    const uint8_t has_signs = signs_in.defined() ? 1 : 0;
    key = hash_bytes(&has_signs, 1, key);
    if (has_signs) {
        const int32_t signs_dtype = static_cast<int32_t>(signs_in.scalar_type());
        key = hash_bytes(&signs_dtype, sizeof(signs_dtype), key);
        key = hash_bytes(signs_in.data_ptr(), static_cast<size_t>(signs_in.nbytes()), key);
    }

    {
        std::lock_guard<std::mutex> lock(g_precond_cache_mutex);
        auto it = g_precond_cache.find(key);
        if (it != g_precond_cache.end()
            && it->second->device_index == dev_index
            && same_content(it->second->perm_cpu, perm_in)
            && same_content(it->second->signs_cpu, signs_in)) {
            it->second->last_used = ++g_precond_clock;
            ++g_precond_stats.hits;
            return it->second;
        }
    }

    auto perm_cpu = perm_in.to(torch::kInt64);
    torch::Tensor signs_cpu;
    if (signs_in.defined()) signs_cpu = signs_in.to(torch::kFloat32).contiguous();
    auto inv_perm_cpu_long = perm_cpu.argsort();

    auto entry = std::make_shared<PrecondCacheEntry>();
    // Own copies (the caller may mutate its tensors later) for hit validation.
    entry->perm_cpu = perm_in.clone();
    if (signs_in.defined()) entry->signs_cpu = signs_in.clone();
    entry->device_index = dev_index;
    entry->perm_device = perm_cpu.to(torch::kInt32).to(device).contiguous();
    entry->inv_perm = inv_perm_cpu_long.to(torch::kInt32).contiguous().to(device).contiguous();
    if (signs_cpu.defined()) {
        entry->signs_device = signs_cpu.to(device).contiguous();
        entry->signs_reordered =
            signs_cpu.index_select(0, inv_perm_cpu_long).contiguous().to(device).contiguous();
    }

    std::lock_guard<std::mutex> lock(g_precond_cache_mutex);
    ++g_precond_stats.misses;
    entry->last_used = ++g_precond_clock;
    // A same-key entry here is a lost build race or a hash collision; replace it.
    g_precond_cache[key] = entry;
    while (g_precond_cache.size() > kPrecondCacheCap) {
        auto victim = g_precond_cache.begin();
        for (auto it = g_precond_cache.begin(); it != g_precond_cache.end(); ++it) {
            if (it->second->last_used < victim->second->last_used) victim = it;
        }
        g_precond_cache.erase(victim);
        ++g_precond_stats.evictions;
    }
    return entry;
}

pybind11::dict precond_cache_stats_impl() {
    std::lock_guard<std::mutex> lock(g_precond_cache_mutex);
    pybind11::dict d;
    d["size"] = g_precond_cache.size();
    d["hits"] = g_precond_stats.hits;
    d["misses"] = g_precond_stats.misses;
    d["evictions"] = g_precond_stats.evictions;
    return d;
}

// Apply signs/perm tensors to args. precond_keepalive must outlive the kernel call.
// signs_owned is only populated for the signs-without-perm case.
void apply_precond_args(
    sycl_quantization_args& args,
    const c10::optional<torch::Tensor>& signs_opt,
    const c10::optional<torch::Tensor>& perm_opt,
    const torch::Device& device,
    torch::Tensor& signs_owned,
    PrecondHandle& precond_keepalive)
{
    if (perm_opt.has_value() && perm_opt->defined()) {
        precond_keepalive = get_or_build_precond_cache(*perm_opt, signs_opt, device);
        const auto& precond = *precond_keepalive;
        args.perm = precond.perm_device.data_ptr<int32_t>();
        args.inv_perm = precond.inv_perm.data_ptr<int32_t>();
        if (precond.signs_device.defined()) {
            args.signs = precond.signs_device.data_ptr<float>();
            args.signs_reordered = precond.signs_reordered.data_ptr<float>();
        }
    } else if (signs_opt.has_value() && signs_opt->defined()) {
        signs_owned = signs_opt->to(torch::kFloat32).to(device).contiguous();
        args.signs = signs_owned.data_ptr<float>();
        args.signs_reordered = signs_owned.data_ptr<float>();
    }
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
    torch::Tensor signs_t;
    PrecondHandle perm_t;
    apply_precond_args(args, signs_opt, perm_opt, src.device(), signs_t, perm_t);

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
    // Copy scales/zps to host via pinned memory; one wait.
    size_t num_chunks_bytes = static_cast<size_t>(num_chunks) * sizeof(float);
    HostScratch<float> h_scales(num_chunks, queue);
    HostScratch<float> h_zps(num_chunks, queue);
    sycl::event scales_evt = queue.memcpy(h_scales.get(), d_scales, num_chunks_bytes, {quant_event});
    sycl::event zps_evt = queue.memcpy(h_zps.get(), d_zps, num_chunks_bytes, {quant_event});
    sycl::event::wait({scales_evt, zps_evt});

    // Serialize to the same format as CPU wrapper
    std::string scale_blob = serialize_scales(
        h_scales.get(), h_zps.get(), num_chunks);

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
    torch::Tensor signs_t;
    PrecondHandle perm_t;
    apply_precond_args(args, signs_opt, perm_opt, src.device(), signs_t, perm_t);

    // Allocate output tensor
    auto dst = torch::empty(
        {element_count},
        src_contig.options().dtype(output_dtype));

    // Deserialize scales from blob (host-only, not the bottleneck).
    std::string scale_blob(scale_bytes_py);
    std::vector<float> h_scales, h_zps;
    deserialize_scales(scale_blob, h_scales, h_zps);
    int64_t num_chunks = static_cast<int64_t>(h_scales.size());

    auto& queue = get_current_queue();

    // Stage scales/zps through pinned host memory for the H2D copy.
    size_t num_chunks_bytes = static_cast<size_t>(num_chunks) * sizeof(float);
    HostScratch<float> h_scales_pinned(num_chunks, queue);
    HostScratch<float> h_zps_pinned(num_chunks, queue);
    std::memcpy(h_scales_pinned.get(), h_scales.data(), num_chunks_bytes);
    std::memcpy(h_zps_pinned.get(), h_zps.data(), num_chunks_bytes);

    auto scale_opts = src_contig.options().dtype(torch::kFloat32);
    auto d_scales_t = torch::empty({num_chunks}, scale_opts);
    auto d_zps_t = torch::empty({num_chunks}, scale_opts);
    float* d_scales = d_scales_t.data_ptr<float>();
    float* d_zps = d_zps_t.data_ptr<float>();
    sycl::event scales_evt = queue.memcpy(d_scales, h_scales_pinned.get(), num_chunks_bytes);
    sycl::event zps_evt = queue.memcpy(d_zps, h_zps_pinned.get(), num_chunks_bytes);

    // Launch dequantize kernel, chained on the H2D copies above (no extra
    // host wait in between).
    sycl::event dequant_event;
    if (qbit <= 8) {
        dequant_event = dispatch_dequantize_by_kvtype<int8_t>(
            queue,
            reinterpret_cast<const int8_t*>(src_contig.data_ptr()),
            dst, d_scales, d_zps, element_count, args, {scales_evt, zps_evt});
    } else {
        dequant_event = dispatch_dequantize_by_kvtype<int16_t>(
            queue,
            reinterpret_cast<const int16_t*>(src_contig.data_ptr()),
            dst, d_scales, d_zps, element_count, args, {scales_evt, zps_evt});
    }
    // Sync point guarding dst.
    dequant_event.wait();

    return dst;
}

// Shared per-plane quantize/dequantize core.
struct XpuPlaneQuantResult {
    // XPU-resident if keep_on_device=true, else CPU.
    torch::Tensor q_data_cpu;
    std::string scale_data;
};

XpuPlaneQuantResult quantize_plane_xpu(
    sycl::queue& queue, const torch::Tensor& plane_xpu, int qbit,
    const sycl_quantization_args& args, int64_t num_layers, int64_t element_count,
    bool keep_on_device = false)
{
    auto q_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    int64_t dst_numel = packed_numel_for_qbit(element_count, qbit);
    auto dst = torch::empty({dst_numel}, plane_xpu.options().dtype(q_dtype));

    int64_t num_chunks = compute_num_chunks(args, element_count);
    auto scale_opts = plane_xpu.options().dtype(torch::kFloat32);
    auto d_scales_t = torch::empty({num_chunks}, scale_opts);
    auto d_zps_t = torch::zeros({num_chunks}, scale_opts);
    float* d_scales = d_scales_t.data_ptr<float>();
    float* d_zps = d_zps_t.data_ptr<float>();

    sycl::event quant_event;
    if (qbit <= 8) {
        quant_event = dispatch_quantize_by_kvtype<int8_t>(
            queue, plane_xpu, reinterpret_cast<int8_t*>(dst.data_ptr()),
            d_scales, d_zps, element_count, args, {});
    } else {
        quant_event = dispatch_quantize_by_kvtype<int16_t>(
            queue, plane_xpu, reinterpret_cast<int16_t*>(dst.data_ptr()),
            d_scales, d_zps, element_count, args, {});
    }

    size_t num_chunks_bytes = static_cast<size_t>(num_chunks) * sizeof(float);
    HostScratch<float> h_scales(num_chunks, queue);
    HostScratch<float> h_zps(num_chunks, queue);
    sycl::event scales_evt = queue.memcpy(h_scales.get(), d_scales, num_chunks_bytes, {quant_event});
    sycl::event zps_evt = queue.memcpy(h_zps.get(), d_zps, num_chunks_bytes, {quant_event});
    sycl::event::wait({scales_evt, zps_evt});

    int64_t chunks_per_layer = compute_chunks_per_layer(args);
    std::string scale_data = pack_scale_blob_per_layer(
        h_scales.get(), h_zps.get(), num_layers > 0 ? num_layers : 1, chunks_per_layer);

    // In-order XPU stream: dst.cpu() waits for the kernel. keep_on_device=true skips
    // the D2H so batched callers can download once.
    if (keep_on_device) {
        return {dst, scale_data};
    }
    auto dst_cpu = dst.to(torch::kCPU).contiguous();
    return {dst_cpu, scale_data};
}

torch::Tensor dequantize_plane_xpu(
    sycl::queue& queue, const torch::Tensor& q_xpu, const std::string& scale_blob,
    int qbit, const sycl_quantization_args& args, int64_t num_layers,
    int64_t element_count, torch::ScalarType output_dtype)
{
    int64_t chunks_per_layer = compute_chunks_per_layer(args);
    int64_t layers_in_blob = num_layers > 0 ? num_layers : 1;
    std::vector<float> h_scales, h_zps;
    parse_scale_blob_per_layer(scale_blob, layers_in_blob, chunks_per_layer, h_scales, h_zps);
    int64_t num_chunks = static_cast<int64_t>(h_scales.size());

    size_t num_chunks_bytes = static_cast<size_t>(num_chunks) * sizeof(float);
    HostScratch<float> h_scales_pinned(num_chunks, queue);
    HostScratch<float> h_zps_pinned(num_chunks, queue);
    std::memcpy(h_scales_pinned.get(), h_scales.data(), num_chunks_bytes);
    std::memcpy(h_zps_pinned.get(), h_zps.data(), num_chunks_bytes);

    auto scale_opts = q_xpu.options().dtype(torch::kFloat32);
    auto d_scales_t = torch::empty({num_chunks}, scale_opts);
    auto d_zps_t = torch::empty({num_chunks}, scale_opts);
    float* d_scales = d_scales_t.data_ptr<float>();
    float* d_zps = d_zps_t.data_ptr<float>();
    sycl::event scales_evt = queue.memcpy(d_scales, h_scales_pinned.get(), num_chunks_bytes);
    sycl::event zps_evt = queue.memcpy(d_zps, h_zps_pinned.get(), num_chunks_bytes);

    auto dst_xpu = torch::empty({element_count}, q_xpu.options().dtype(output_dtype));
    sycl::event dequant_event;
    if (qbit <= 8) {
        dequant_event = dispatch_dequantize_by_kvtype<int8_t>(
            queue, reinterpret_cast<const int8_t*>(q_xpu.data_ptr()),
            dst_xpu, d_scales, d_zps, element_count, args, {scales_evt, zps_evt});
    } else {
        dequant_event = dispatch_dequantize_by_kvtype<int16_t>(
            queue, reinterpret_cast<const int16_t*>(q_xpu.data_ptr()),
            dst_xpu, d_scales, d_zps, element_count, args, {scales_evt, zps_evt});
    }
    dequant_event.wait();
    return dst_xpu;
}

// ---------------------------------------------------------------------------
// Public API: kvweave_serialize_chunk_state_multi /
// kvweave_dequantize_chunk_state_multi
// ---------------------------------------------------------------------------
// Batched variant of the *_chunk_state functions for N planes. One H2D upload and
// one D2H download. Per-item framing is identical to the single-item calls.
// Requires a homogeneous input (quantize) or output (dequantize) dtype across
// items; qbit, scaling method, rh, asym and layout may differ.
std::vector<pybind11::bytes> kvweave_serialize_chunk_state_multi_xpu(
    std::vector<torch::Tensor> srcs,
    std::vector<pybind11::bytes> header_bytes_list,
    std::vector<int64_t> scale_ids,
    std::vector<int> qbits,
    std::vector<int64_t> blocks_nums,
    std::vector<int64_t> block_sizes,
    std::vector<int64_t> head_nums,
    std::vector<int64_t> head_dims,
    std::vector<int64_t> num_layers_list,
    std::vector<bool> rhs,
    std::vector<bool> asyms,
    std::vector<std::string> scaling_methods,
    std::vector<c10::optional<torch::Tensor>> signs_list,
    std::vector<c10::optional<torch::Tensor>> perm_list,
    int num_threads = 0)
{
    (void)scale_ids;
    (void)num_threads;
    const size_t n = srcs.size();
    if (n == 0) {
        return {};
    }
    if (header_bytes_list.size() != n || qbits.size() != n || blocks_nums.size() != n ||
        block_sizes.size() != n || head_nums.size() != n || head_dims.size() != n ||
        num_layers_list.size() != n || rhs.size() != n || asyms.size() != n ||
        scaling_methods.size() != n || signs_list.size() != n || perm_list.size() != n) {
        throw std::invalid_argument(
            "kvweave_serialize_chunk_state_multi: all per-item argument lists must have the same length as srcs.");
    }
    for (auto& s : srcs) {
        ensure_cpu_tensor(s, "src");
    }
    auto common_dtype = srcs[0].scalar_type();
    for (const auto& s : srcs) {
        if (s.scalar_type() != common_dtype) {
            throw std::invalid_argument(
                "kvweave_serialize_chunk_state_multi requires all items to share one input dtype.");
        }
    }

    // Single combined H2D upload (item dtypes share common_dtype).
    std::vector<torch::Tensor> flat_inputs(n);
    std::vector<int64_t> elem_offsets(n + 1, 0);
    for (size_t i = 0; i < n; ++i) {
        flat_inputs[i] = srcs[i].contiguous().view({-1});
        elem_offsets[i + 1] = elem_offsets[i] + flat_inputs[i].numel();
    }
    auto concat_cpu = torch::cat(flat_inputs, 0);
    auto& queue = get_current_queue();
    auto concat_xpu = concat_cpu.to(torch::Device(torch::kXPU));

    std::vector<XpuPlaneQuantResult> results(n);
    std::vector<torch::Tensor> signs_owned(n);
    std::vector<PrecondHandle> perm_owned(n);
    for (size_t i = 0; i < n; ++i) {
        int64_t element_count = elem_offsets[i + 1] - elem_offsets[i];
        auto plane_xpu = concat_xpu.narrow(0, elem_offsets[i], element_count);

        auto args = build_sycl_args(
            qbits[i], static_cast<int>(blocks_nums[i]), static_cast<int>(block_sizes[i]),
            static_cast<int>(head_nums[i]), static_cast<int>(head_dims[i]),
            rhs[i], asyms[i], scaling_methods[i], num_layers_list[i]);
        apply_precond_args(
            args, signs_list[i], perm_list[i], plane_xpu.device(), signs_owned[i], perm_owned[i]);

        results[i] = quantize_plane_xpu(
            queue, plane_xpu, qbits[i], args, num_layers_list[i], element_count,
            /*keep_on_device=*/true);
    }

    // Single combined D2H download (byte view; item dtypes may differ).
    std::vector<torch::Tensor> flat_outputs(n);
    std::vector<int64_t> byte_offsets(n + 1, 0);
    for (size_t i = 0; i < n; ++i) {
        flat_outputs[i] = results[i].q_data_cpu.view(torch::kUInt8).view({-1});
        byte_offsets[i + 1] = byte_offsets[i] + flat_outputs[i].numel();
    }
    auto concat_out_xpu = torch::cat(flat_outputs, 0);
    auto concat_out_cpu = concat_out_xpu.to(torch::kCPU).contiguous();

    std::vector<pybind11::bytes> payloads(n);
    for (size_t i = 0; i < n; ++i) {
        auto q_bytes = concat_out_cpu.narrow(0, byte_offsets[i], byte_offsets[i + 1] - byte_offsets[i]);
        std::string hdr_str(header_bytes_list[i]);
        const std::string& scale_data = results[i].scale_data;
        if (scale_data.size() > UINT32_MAX) {
            throw std::runtime_error("kvweave scale blob exceeds uint32 length framing limit");
        }
        uint32_t scale_len = static_cast<uint32_t>(scale_data.size());
        size_t total = hdr_str.size() + 4u + scale_len + static_cast<size_t>(q_bytes.numel());
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
        out.append(reinterpret_cast<const char*>(q_bytes.data_ptr()), static_cast<size_t>(q_bytes.numel()));
        payloads[i] = pybind11::bytes(out);
    }
    return payloads;
}

std::vector<torch::Tensor> kvweave_dequantize_chunk_state_multi_xpu(
    std::vector<torch::Tensor> q_datas,
    std::vector<pybind11::bytes> scale_bytes_list,
    std::vector<int64_t> num_layers_list,
    std::vector<int64_t> chunk_tokens_list,
    std::vector<int64_t> h_merged_list,
    std::vector<int> qbits,
    std::vector<int64_t> blocks_nums,
    std::vector<int64_t> block_sizes,
    std::vector<int64_t> head_nums,
    std::vector<int64_t> head_dims,
    std::vector<bool> rhs,
    std::vector<bool> asyms,
    std::vector<std::string> scaling_methods,
    std::vector<torch::ScalarType> output_dtypes,
    std::vector<c10::optional<torch::Tensor>> signs_list,
    std::vector<c10::optional<torch::Tensor>> perm_list,
    int num_threads = 0)
{
    (void)num_threads;
    const size_t n = q_datas.size();
    if (n == 0) {
        return {};
    }
    if (scale_bytes_list.size() != n || num_layers_list.size() != n || chunk_tokens_list.size() != n ||
        h_merged_list.size() != n || qbits.size() != n || blocks_nums.size() != n ||
        block_sizes.size() != n || head_nums.size() != n || head_dims.size() != n ||
        rhs.size() != n || asyms.size() != n || scaling_methods.size() != n ||
        output_dtypes.size() != n || signs_list.size() != n || perm_list.size() != n) {
        throw std::invalid_argument(
            "kvweave_dequantize_chunk_state_multi: all per-item argument lists must have the same length as q_datas.");
    }
    for (auto& q : q_datas) {
        ensure_cpu_tensor(q, "q_data");
    }
    auto common_output_dtype = output_dtypes[0];
    for (const auto& dt : output_dtypes) {
        if (dt != common_output_dtype) {
            throw std::invalid_argument(
                "kvweave_dequantize_chunk_state_multi requires all items to share one output dtype.");
        }
    }

    // Single combined H2D upload (byte view; item dtypes may differ).
    std::vector<torch::Tensor> flat_inputs(n);
    std::vector<int64_t> byte_offsets(n + 1, 0);
    for (size_t i = 0; i < n; ++i) {
        auto contig = q_datas[i].contiguous();
        auto expected_dtype = (qbits[i] <= 8) ? torch::kInt8 : torch::kInt16;
        if (contig.scalar_type() != expected_dtype) {
            throw std::invalid_argument("q_data dtype does not match qbit.");
        }
        flat_inputs[i] = contig.view(torch::kUInt8).view({-1});
        byte_offsets[i + 1] = byte_offsets[i] + flat_inputs[i].numel();
    }
    auto concat_cpu = torch::cat(flat_inputs, 0);
    auto& queue = get_current_queue();
    auto concat_xpu = concat_cpu.to(torch::Device(torch::kXPU));

    std::vector<torch::Tensor> results(n);
    std::vector<torch::Tensor> signs_owned(n);
    std::vector<PrecondHandle> perm_owned(n);
    for (size_t i = 0; i < n; ++i) {
        auto q_xpu = concat_xpu.narrow(0, byte_offsets[i], byte_offsets[i + 1] - byte_offsets[i]);

        auto args = build_sycl_args(
            qbits[i], static_cast<int>(blocks_nums[i]), static_cast<int>(block_sizes[i]),
            static_cast<int>(head_nums[i]), static_cast<int>(head_dims[i]),
            rhs[i], asyms[i], scaling_methods[i], num_layers_list[i]);
        apply_precond_args(
            args, signs_list[i], perm_list[i], q_xpu.device(), signs_owned[i], perm_owned[i]);

        int64_t numel = num_layers_list[i] * chunk_tokens_list[i] * h_merged_list[i];
        std::string scale_blob(scale_bytes_list[i]);
        results[i] = dequantize_plane_xpu(
            queue, q_xpu, scale_blob, qbits[i], args, num_layers_list[i], numel, output_dtypes[i]);
    }

    // Single combined D2H download.
    auto concat_out_xpu = torch::cat(results, 0);
    auto concat_out_cpu = concat_out_xpu.to(torch::kCPU).contiguous();

    std::vector<torch::Tensor> final_results(n);
    int64_t elem_offset = 0;
    for (size_t i = 0; i < n; ++i) {
        int64_t numel = num_layers_list[i] * chunk_tokens_list[i] * h_merged_list[i];
        final_results[i] = concat_out_cpu.narrow(0, elem_offset, numel)
            .view({num_layers_list[i], chunk_tokens_list[i], h_merged_list[i]})
            .contiguous();
        elem_offset += numel;
    }
    return final_results;
}

// ---------------------------------------------------------------------------
// Public API: kvweave_serialize_chunk_state / kvweave_dequantize_chunk_state
// ---------------------------------------------------------------------------
// Single-tensor fused multi-layer entry points; same name, argument order and wire
// framing as the CPU module.
//
// The SYCL kernel spans all layers in one launch, so a single scale segment is
// emitted. scale_id is unused (signature parity with the CPU module).
// Allocate an uninitialised bytes object; the caller must fill all `size` bytes.
pybind11::bytes alloc_bytes(size_t size, char** data) {
    PyObject* obj = PyBytes_FromStringAndSize(nullptr, static_cast<Py_ssize_t>(size));
    if (!obj) throw pybind11::error_already_set();
    *data = PyBytes_AS_STRING(obj);
    return pybind11::reinterpret_steal<pybind11::bytes>(obj);
}

void write_be32(char* out, uint32_t v) {
    out[0] = static_cast<char>((v >> 24) & 0xFF);
    out[1] = static_cast<char>((v >> 16) & 0xFF);
    out[2] = static_cast<char>((v >>  8) & 0xFF);
    out[3] = static_cast<char>((v >>  0) & 0xFF);
}

// A quantized single-plane state payload whose q data is still on the device.
// Wire format: header | scale_len(4BE) | scales | q_data.
struct StatePayload {
    XpuPlaneQuantResult plane;
    std::string header;
    size_t q_bytes = 0;
    size_t total = 0;
};

StatePayload quantize_state_payload(
    sycl::queue& queue,
    const torch::Tensor& src,
    const pybind11::bytes& header_bytes,
    int qbit, int blocks_num, int block_size, int head_num, int head_dim,
    int64_t num_layers, bool rh, bool asym, const std::string& scaling_method,
    const c10::optional<torch::Tensor>& signs_opt,
    const c10::optional<torch::Tensor>& perm_opt)
{
    ensure_cpu_tensor(src, "src");
    auto src_xpu = src.contiguous().to(torch::Device(torch::kXPU)).contiguous();

    auto args = build_sycl_args(
        qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method, num_layers);

    torch::Tensor signs_t;
    PrecondHandle perm_t;
    apply_precond_args(args, signs_opt, perm_opt, src_xpu.device(), signs_t, perm_t);

    StatePayload p;
    // keep_on_device=true: q stays on the XPU so write_state_payload controls
    // the single D2H into the final destination.
    p.plane = quantize_plane_xpu(
        queue, src_xpu, qbit, args, num_layers, src_xpu.numel(), true);
    p.header = std::string(header_bytes);
    if (p.plane.scale_data.size() > UINT32_MAX) {
        throw std::runtime_error("kvweave scale blob exceeds uint32 length framing limit");
    }
    p.q_bytes = static_cast<size_t>(p.plane.q_data_cpu.numel()) * ((qbit <= 8) ? 1 : 2);
    p.total = p.header.size() + 4u + p.plane.scale_data.size() + p.q_bytes;
    return p;
}

// Write the payload into out[0, p.total). The q data is DMA'd straight from the
// device into `out`.
void write_state_payload(sycl::queue& queue, const StatePayload& p, char* out) {
    size_t off = 0;
    std::memcpy(out, p.header.data(), p.header.size());
    off += p.header.size();
    write_be32(out + off, static_cast<uint32_t>(p.plane.scale_data.size()));
    off += 4;
    std::memcpy(out + off, p.plane.scale_data.data(), p.plane.scale_data.size());
    off += p.plane.scale_data.size();
    queue.memcpy(out + off, p.plane.q_data_cpu.data_ptr(), p.q_bytes).wait();
}

pybind11::bytes kvweave_serialize_chunk_state_xpu(
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
    int num_threads = 0)
{
    (void)scale_id;
    (void)num_threads;
    auto& queue = get_current_queue();
    auto p = quantize_state_payload(
        queue, src, header_bytes, qbit, blocks_num, block_size, head_num, head_dim,
        num_layers, rh, asym, scaling_method, signs_opt, perm_opt);
    char* data = nullptr;
    auto result = alloc_bytes(p.total, &data);
    write_state_payload(queue, p, data);
    return result;
}

// Same wire format as kvweave_serialize_chunk_state_xpu, but written straight
// into a caller-owned contiguous uint8 CPU tensor (e.g. LMCache's SHM slot)
// instead of being returned as bytes, so the caller needs no further copy.
// Returns the number of payload bytes written; throws if dst is too small.
int64_t kvweave_serialize_chunk_state_into_xpu(
    torch::Tensor src,
    torch::Tensor dst,
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
    int num_threads = 0)
{
    (void)scale_id;
    (void)num_threads;
    ensure_cpu_tensor(dst, "dst");
    if (dst.scalar_type() != torch::kUInt8 || !dst.is_contiguous()) {
        throw std::invalid_argument("dst must be a contiguous uint8 CPU tensor.");
    }
    auto& queue = get_current_queue();
    auto p = quantize_state_payload(
        queue, src, header_bytes, qbit, blocks_num, block_size, head_num, head_dim,
        num_layers, rh, asym, scaling_method, signs_opt, perm_opt);
    if (p.total > static_cast<size_t>(dst.numel())) {
        throw std::invalid_argument(
            "encoded payload (" + std::to_string(p.total) + " bytes) exceeds dst capacity ("
            + std::to_string(dst.numel()) + " bytes)");
    }
    write_state_payload(queue, p, reinterpret_cast<char*>(dst.data_ptr()));
    return static_cast<int64_t>(p.total);
}

// XPU analog of the CPU module's kvweave_serialize_fused_chunk_direct: quantizes
// fused [layers, tokens, head_num*head_dim] attention per (layer, head) with the
// kernel reading the fused layout in place. Payload bytes match
// kvweave_serialize_chunk_state (this module) on the head-split tensor.
pybind11::object kvweave_serialize_fused_chunk_direct_xpu(
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
    c10::optional<torch::Tensor> out_opt)
{
    (void)num_threads;
    ensure_cpu_tensor(src, "src");
    if (src.dim() != 3) {
        throw std::invalid_argument("src must be a 3-D [layers, tokens, head_num*head_dim] tensor");
    }
    const int64_t layers = src.size(0);
    const int64_t tokens = src.size(1);
    const int64_t hidden = src.size(2);
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
    const auto dtype = src.scalar_type();
    if (dtype != torch::kHalf && dtype != torch::kBFloat16 && dtype != torch::kFloat32) {
        throw std::invalid_argument("src dtype must be float16, bfloat16 or float32");
    }
    if (tokens > INT32_MAX) {
        throw std::invalid_argument("tokens exceeds int32 range");
    }
    const int64_t transform_len = per_channel ? tokens : head_dim;
    if (rh && (transform_len & (transform_len - 1)) != 0) {
        throw std::invalid_argument("rh (Hadamard) requires the transform length to be a power of 2");
    }
    c10::optional<torch::Tensor> signs_use, perm_use;
    if (rh && signs_opt.has_value() && signs_opt->defined()) {
        if (signs_opt->numel() != transform_len) {
            throw std::invalid_argument("signs length must equal the RH transform length");
        }
        signs_use = signs_opt;
    }
    if (rh && perm_opt.has_value() && perm_opt->defined()) {
        auto perm_cpu = perm_opt->to(torch::kCPU).to(torch::kInt64).contiguous();
        if (perm_cpu.numel() != transform_len) {
            throw std::invalid_argument("perm length must equal the RH transform length");
        }
        const int64_t* perm = perm_cpu.data_ptr<int64_t>();
        for (int64_t i = 0; i < transform_len; ++i) {
            if (perm[i] < 0 || perm[i] >= transform_len) {
                throw std::invalid_argument("perm entry out of range");
            }
        }
        perm_use = perm_opt;
    }

    const int64_t units = layers * head_num;
    // blocks_num * block_size == tokens gives one per_token scale per token.
    auto args = build_sycl_args(
        qbit, 1, static_cast<int>(tokens), static_cast<int>(head_num),
        static_cast<int>(head_dim), rh, asym, scaling_method, units);
    args.fused_src_head_num = head_num;

    auto& queue = get_current_queue();
    auto src_xpu = src.contiguous().to(torch::Device(torch::kXPU)).contiguous();
    torch::Tensor signs_t;
    PrecondHandle perm_t;
    apply_precond_args(args, signs_use, perm_use, src_xpu.device(), signs_t, perm_t);

    StatePayload p;
    p.plane = quantize_plane_xpu(
        queue, src_xpu, qbit, args, units, src_xpu.numel(), /*keep_on_device=*/true);
    p.header = std::string(header_bytes);
    if (p.plane.scale_data.size() > UINT32_MAX) {
        throw std::runtime_error("kvweave scale blob exceeds uint32 length framing limit");
    }
    p.q_bytes = static_cast<size_t>(p.plane.q_data_cpu.numel());
    p.total = p.header.size() + 4u + p.plane.scale_data.size() + p.q_bytes;

    if (out_opt.has_value() && out_opt->defined()) {
        auto& out = *out_opt;
        ensure_cpu_tensor(out, "out");
        if (out.scalar_type() != torch::kUInt8 || !out.is_contiguous()
            || static_cast<size_t>(out.numel()) < p.total) {
            throw std::invalid_argument("out must be a contiguous uint8 tensor large enough for the payload");
        }
        write_state_payload(queue, p, reinterpret_cast<char*>(out.data_ptr()));
        return pybind11::int_(p.total);
    }
    char* data = nullptr;
    auto result = alloc_bytes(p.total, &data);
    write_state_payload(queue, p, data);
    return std::move(result);
}

// XPU analog of the CPU module's kvweave_dequantize_fused_chunk_direct: the
// dequantize kernel writes the fused [layers, tokens, head_num*head_dim]
// layout directly (no split plane + device permute), then one D2H into dst.
void kvweave_dequantize_fused_chunk_direct_xpu(
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
    int num_threads)
{
    (void)num_threads;
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
    const int64_t numel = layers * tokens * head_num * head_dim;
    if (!dst.is_contiguous() || dst.numel() != numel) {
        throw std::invalid_argument("dst must be contiguous with layers*tokens*head_num*head_dim elements");
    }
    if (q_data.scalar_type() != torch::kInt8 && q_data.scalar_type() != torch::kUInt8) {
        throw std::invalid_argument("q_data must be int8 or uint8");
    }
    if (tokens > INT32_MAX) {
        throw std::invalid_argument("tokens exceeds int32 range");
    }
    const int64_t q_numel = packed_numel_for_qbit(numel, qbit);
    // Trailing bytes (e.g. SHM slot padding) are allowed and never read.
    if (q_data.numel() < q_numel) {
        throw std::invalid_argument("q_data is smaller than expected for the fused payload");
    }
    const int64_t transform_len = per_channel ? tokens : head_dim;
    if (rh && (transform_len & (transform_len - 1)) != 0) {
        throw std::invalid_argument("rh (Hadamard) requires the transform length to be a power of 2");
    }
    c10::optional<torch::Tensor> signs_use, perm_use;
    if (rh && signs_opt.has_value() && signs_opt->defined()) {
        if (signs_opt->numel() != transform_len) {
            throw std::invalid_argument("signs length must equal the RH transform length");
        }
        signs_use = signs_opt;
    }
    if (rh && perm_opt.has_value() && perm_opt->defined()) {
        auto perm_cpu = perm_opt->to(torch::kCPU).to(torch::kInt64).contiguous();
        if (perm_cpu.numel() != transform_len) {
            throw std::invalid_argument("perm length must equal the RH transform length");
        }
        const int64_t* perm = perm_cpu.data_ptr<int64_t>();
        for (int64_t i = 0; i < transform_len; ++i) {
            if (perm[i] < 0 || perm[i] >= transform_len) {
                throw std::invalid_argument("perm entry out of range");
            }
        }
        perm_use = perm_opt;
    }

    const int64_t units = layers * head_num;
    auto args = build_sycl_args(
        qbit, 1, static_cast<int>(tokens), static_cast<int>(head_num),
        static_cast<int>(head_dim), rh, asym, scaling_method, units);
    args.fused_dst_head_num = head_num;

    auto& queue = get_current_queue();
    auto q_xpu = q_data.contiguous().view(torch::kInt8).narrow(0, 0, q_numel)
                     .to(torch::Device(torch::kXPU)).contiguous();
    torch::Tensor signs_t;
    PrecondHandle perm_t;
    apply_precond_args(args, signs_use, perm_use, q_xpu.device(), signs_t, perm_t);

    auto dst_xpu = dequantize_plane_xpu(
        queue, q_xpu, std::string(scale_bytes), qbit, args, units, numel, dtype);
    queue.memcpy(dst.data_ptr(), dst_xpu.data_ptr(),
                 static_cast<size_t>(numel) * static_cast<size_t>(dst_xpu.element_size())).wait();
}

// Shared front half of the state-payload decoders: upload q, dequantize on the
// device. Returns the dequantized tensor still on the XPU, flat, in the
// native [num_layers, chunk_tokens, h_merged] element order.
torch::Tensor dequantize_state_on_device(
    torch::Tensor q_data,
    const pybind11::bytes& scale_bytes,
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
    const c10::optional<torch::Tensor>& signs_opt,
    const c10::optional<torch::Tensor>& perm_opt)
{
    ensure_cpu_tensor(q_data, "q_data");
    auto q_contig = q_data.contiguous();

    auto q_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    if (q_contig.scalar_type() != q_dtype) {
        throw std::invalid_argument("q_data dtype does not match qbit.");
    }

    const int64_t numel = num_layers * chunk_tokens * h_merged;
    const int64_t q_numel = packed_numel_for_qbit(numel, qbit);
    // Minimum-length check only; trailing bytes (e.g. SHM slot padding) are never read.
    if (q_contig.numel() < q_numel) {
        throw std::invalid_argument("q_data is smaller than expected for the state payload.");
    }

    auto& queue = get_current_queue();
    auto q_xpu = q_contig.to(torch::Device(torch::kXPU)).contiguous();

    auto args = build_sycl_args(
        qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method, num_layers);

    torch::Tensor signs_t;
    PrecondHandle perm_t;
    apply_precond_args(args, signs_opt, perm_opt, q_xpu.device(), signs_t, perm_t);

    std::string scale_blob(scale_bytes);
    return dequantize_plane_xpu(
        queue, q_xpu, scale_blob, qbit, args, num_layers, numel, output_dtype);
}

torch::Tensor kvweave_dequantize_chunk_state_xpu(
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
    int num_threads = 0)
{
    (void)num_threads;
    auto dst_xpu = dequantize_state_on_device(
        q_data, scale_bytes, num_layers, chunk_tokens, h_merged, qbit, blocks_num,
        block_size, head_num, head_dim, rh, asym, scaling_method, output_dtype,
        signs_opt, perm_opt);
    return dst_xpu.view({num_layers, chunk_tokens, h_merged}).to(torch::kCPU).contiguous();
}

// Like kvweave_dequantize_chunk_state, but DMAs the result straight into the
// caller-owned contiguous CPU tensor `dst` (e.g. LMCache's decode scratch)
// instead of returning a fresh tensor the caller must copy/merge from.
//
// merge_head_num > 1 declares that the payload holds per-head planes
// [num_layers = layers*merge_head_num, chunk_tokens, h_merged = head_dim] and
// folds them back to [layers, chunk_tokens, merge_head_num*head_dim] on the
// device before the D2H, so dst is written in its final layout (replaces the
// CPU-side kvweave_merge_fused_heads step). dst must hold exactly
// num_layers*chunk_tokens*h_merged elements of output_dtype.
void kvweave_dequantize_chunk_state_into_xpu(
    torch::Tensor q_data,
    pybind11::bytes scale_bytes,
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
    int merge_head_num = 0,
    int num_threads = 0)
{
    (void)num_threads;
    ensure_cpu_tensor(dst, "dst");
    if (!dst.is_contiguous() || dst.scalar_type() != output_dtype) {
        throw std::invalid_argument("dst must be a contiguous CPU tensor of output_dtype.");
    }
    const int64_t numel = num_layers * chunk_tokens * h_merged;
    if (dst.numel() != numel) {
        throw std::invalid_argument("dst has the wrong number of elements for this payload.");
    }
    if (merge_head_num > 1 && num_layers % merge_head_num != 0) {
        throw std::invalid_argument("num_layers is not a multiple of merge_head_num.");
    }

    auto dev = dequantize_state_on_device(
        q_data, scale_bytes, num_layers, chunk_tokens, h_merged, qbit, blocks_num,
        block_size, head_num, head_dim, rh, asym, scaling_method, output_dtype,
        signs_opt, perm_opt);
    if (merge_head_num > 1) {
        dev = dev.view({num_layers / merge_head_num, merge_head_num, chunk_tokens, h_merged})
                 .permute({0, 2, 1, 3})
                 .contiguous();
    }
    // DMA straight into dst.
    get_current_queue().memcpy(
        dst.data_ptr(), dev.data_ptr(),
        static_cast<size_t>(numel) * static_cast<size_t>(dev.element_size())).wait();
}

// ---------------------------------------------------------------------------
// Public API: kvweave_serialize_chunk / kvweave_dequantize_chunk /
// kvweave_dequantize_chunk_into_4d
// ---------------------------------------------------------------------------
// Fused K/V (two-plane) entry points mirroring the CPU wrapper's *_chunk_py
// functions. K and V run back-to-back on the same in-order queue, with no host wait
// in between.
pybind11::bytes kvweave_serialize_chunk_xpu(
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
    int num_threads = 0)
{
    (void)scale_id_k;
    (void)scale_id_v;
    (void)num_threads;
    ensure_cpu_tensor(src, "src");
    auto src_contig = src.contiguous();
    int64_t half_numel = src_contig.numel() / 2;

    auto& queue = get_current_queue();
    auto flat_xpu = src_contig.to(torch::Device(torch::kXPU)).contiguous().view({-1});
    auto plane_k_xpu = flat_xpu.narrow(0, 0, half_numel).contiguous();
    auto plane_v_xpu = flat_xpu.narrow(0, half_numel, half_numel).contiguous();

    auto args = build_sycl_args(
        qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method, num_layers);

    torch::Tensor signs_t;
    PrecondHandle perm_t;
    apply_precond_args(args, signs_opt, perm_opt, flat_xpu.device(), signs_t, perm_t);

    auto plane_k = quantize_plane_xpu(queue, plane_k_xpu, qbit, args, num_layers, half_numel, true);
    auto plane_v = quantize_plane_xpu(queue, plane_v_xpu, qbit, args, num_layers, half_numel, true);

    // Pack: header | k_scale_len(4BE) | k_scales | v_scale_len(4BE) | v_scales | q_k | q_v
    std::string hdr_str(header_bytes);
    if (plane_k.scale_data.size() > UINT32_MAX || plane_v.scale_data.size() > UINT32_MAX) {
        throw std::runtime_error("kvweave scale blob exceeds uint32 length framing limit");
    }
    uint32_t k_len = static_cast<uint32_t>(plane_k.scale_data.size());
    uint32_t v_len = static_cast<uint32_t>(plane_v.scale_data.size());
    size_t item_bytes = (qbit <= 8) ? 1 : 2;
    size_t k_q_bytes = static_cast<size_t>(plane_k.q_data_cpu.numel()) * item_bytes;
    size_t v_q_bytes = static_cast<size_t>(plane_v.q_data_cpu.numel()) * item_bytes;
    size_t q_bytes = k_q_bytes + v_q_bytes;

    size_t total = hdr_str.size()
                 + 4u + k_len
                 + 4u + v_len
                 + q_bytes;
    char* data = nullptr;
    auto result = alloc_bytes(total, &data);
    size_t off = 0;
    std::memcpy(data, hdr_str.data(), hdr_str.size());
    off += hdr_str.size();
    write_be32(data + off, k_len);
    off += 4;
    std::memcpy(data + off, plane_k.scale_data.data(), k_len);
    off += k_len;
    write_be32(data + off, v_len);
    off += 4;
    std::memcpy(data + off, plane_v.scale_data.data(), v_len);
    off += v_len;
    // DMA both q planes straight into the result bytes (see write_state_payload).
    sycl::event q_k_evt = queue.memcpy(data + off, plane_k.q_data_cpu.data_ptr(), k_q_bytes);
    sycl::event q_v_evt = queue.memcpy(data + off + k_q_bytes, plane_v.q_data_cpu.data_ptr(), v_q_bytes);
    sycl::event::wait({q_k_evt, q_v_evt});
    return result;
}

torch::Tensor kvweave_dequantize_chunk_xpu(
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
    int num_threads = 0)
{
    (void)num_threads;
    ensure_cpu_tensor(q_data, "q_data");
    auto q_contig = q_data.contiguous();

    auto q_dtype = (qbit <= 8) ? torch::kInt8 : torch::kInt16;
    if (q_contig.scalar_type() != q_dtype) {
        throw std::invalid_argument("q_data dtype does not match qbit.");
    }

    int64_t half_numel = num_layers * chunk_tokens * h_merged;
    int64_t half_q_numel = packed_numel_for_qbit(half_numel, qbit);
    int64_t expected_numel = 2 * half_q_numel;
    if (q_contig.numel() < expected_numel) {
        throw std::invalid_argument("q_data is smaller than expected for K/V payload.");
    }

    auto& queue = get_current_queue();
    auto q_xpu_flat = q_contig.to(torch::Device(torch::kXPU)).contiguous().view({-1});
    auto q_k_xpu = q_xpu_flat.narrow(0, 0, half_q_numel).contiguous();
    auto q_v_xpu = q_xpu_flat.narrow(0, half_q_numel, half_q_numel).contiguous();

    auto args = build_sycl_args(
        qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method, num_layers);

    torch::Tensor signs_t;
    PrecondHandle perm_t;
    apply_precond_args(args, signs_opt, perm_opt, q_xpu_flat.device(), signs_t, perm_t);

    std::string k_scale_blob(k_scale_bytes);
    std::string v_scale_blob(v_scale_bytes);
    auto dst_k = dequantize_plane_xpu(
        queue, q_k_xpu, k_scale_blob, qbit, args, num_layers, half_numel, output_dtype);
    auto dst_v = dequantize_plane_xpu(
        queue, q_v_xpu, v_scale_blob, qbit, args, num_layers, half_numel, output_dtype);

    auto result = torch::empty({2, num_layers, chunk_tokens, h_merged}, dst_k.options());
    result.select(0, 0).copy_(dst_k.view({num_layers, chunk_tokens, h_merged}));
    result.select(0, 1).copy_(dst_v.view({num_layers, chunk_tokens, h_merged}));
    return result.to(torch::kCPU).contiguous();
}

void kvweave_dequantize_chunk_into_4d_xpu(
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
    int layer_num_threads = 1)
{
    // layer_num_threads is CPU-only; accepted for signature parity.
    (void)num_threads;
    (void)layer_num_threads;
    ensure_cpu_tensor(dst, "dst");
    if (!dst.is_contiguous()) {
        throw std::invalid_argument("dst tensor must be contiguous.");
    }
    if (
        dst.dim() != 4 || dst.size(0) != 2 || dst.size(1) != num_layers ||
        dst.size(2) != chunk_tokens || dst.size(3) != h_merged
    ) {
        throw std::invalid_argument(
            "dst must be contiguous [2, num_layers, chunk_tokens, h_merged].");
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
    int64_t half_q_numel = packed_numel_for_qbit(half_numel, qbit);
    int64_t expected_numel = 2 * half_q_numel;
    if (q_contig.numel() < expected_numel) {
        throw std::invalid_argument("q_data is smaller than expected for K/V payload.");
    }

    auto& queue = get_current_queue();
    auto q_xpu_flat = q_contig.to(torch::Device(torch::kXPU)).contiguous().view({-1});
    auto q_k_xpu = q_xpu_flat.narrow(0, 0, half_q_numel).contiguous();
    auto q_v_xpu = q_xpu_flat.narrow(0, half_q_numel, half_q_numel).contiguous();

    auto args = build_sycl_args(
        qbit, blocks_num, block_size, head_num, head_dim, rh, asym, scaling_method, num_layers);

    torch::Tensor signs_t;
    PrecondHandle perm_t;
    apply_precond_args(args, signs_opt, perm_opt, q_xpu_flat.device(), signs_t, perm_t);

    std::string k_scale_blob(k_scale_bytes);
    std::string v_scale_blob(v_scale_bytes);
    auto dst_k_xpu = dequantize_plane_xpu(
        queue, q_k_xpu, k_scale_blob, qbit, args, num_layers, half_numel, output_dtype);
    auto dst_v_xpu = dequantize_plane_xpu(
        queue, q_v_xpu, v_scale_blob, qbit, args, num_layers, half_numel, output_dtype);

    dst.select(0, 0).copy_(dst_k_xpu.view({num_layers, chunk_tokens, h_merged}));
    dst.select(0, 1).copy_(dst_v_xpu.view({num_layers, chunk_tokens, h_merged}));
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

    m.def("kvweave_serialize_chunk_state", &kvweave_serialize_chunk_state_xpu,
        "Quantize a single tensor (no K/V split) and pack a complete payload, "
        "on XPU. Single-tensor analog of a fused K/V serialize; mirrors the "
        "CPU module's kvweave_serialize_chunk_state signature so callers can "
        "select the native module without branching. Accepts/returns CPU "
        "tensors/bytes, transferring to/from XPU internally.",
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
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt,
        pybind11::arg("num_threads") = 0);

    m.def("kvweave_serialize_chunk_state_into", &kvweave_serialize_chunk_state_into_xpu,
        "Like kvweave_serialize_chunk_state, but writes the payload directly "
        "into the caller-provided contiguous uint8 CPU tensor `dst` and "
        "returns the number of bytes written (raises if dst is too small).",
        pybind11::arg("src"),
        pybind11::arg("dst"),
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
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt,
        pybind11::arg("num_threads") = 0);

    m.def("kvweave_serialize_fused_chunk_direct", &kvweave_serialize_fused_chunk_direct_xpu,
        "Quantize fused [layers, tokens, head_num*head_dim] attention per "
        "(layer, head) on XPU, reading the fused layout in place (no head "
        "split). Same payload as kvweave_serialize_chunk_state on the split "
        "tensor with num_layers=layers*head_num. Supports per_channel/"
        "per_token. Returns bytes, or the written length when `out` "
        "(contiguous uint8 CPU tensor) is given. Mirrors the CPU module's "
        "signature.",
        pybind11::arg("src"),
        pybind11::arg("header_bytes"),
        pybind11::arg("qbit"),
        pybind11::arg("head_num"),
        pybind11::arg("head_dim"),
        pybind11::arg("rh") = false,
        pybind11::arg("asym") = false,
        pybind11::arg("scaling_method") = "per_channel",
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt,
        pybind11::arg("num_threads") = 0,
        pybind11::arg("out") = c10::nullopt);

    m.def("kvweave_dequantize_fused_chunk_direct", &kvweave_dequantize_fused_chunk_direct_xpu,
        "Inverse of kvweave_serialize_fused_chunk_direct on XPU: dequantize the "
        "per-(layer, head) q planes + scale blob straight into the contiguous "
        "fused CPU dst [layers, tokens, head_num*head_dim] (no split plane, no "
        "device head merge). Supports per_channel/per_token. Mirrors the CPU "
        "module's signature.",
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
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt,
        pybind11::arg("num_threads") = 0);

    m.def("kvweave_dequantize_chunk_state", &kvweave_dequantize_chunk_state_xpu,
        "Dequantize a single-tensor (no K/V split) quant payload, on XPU. "
        "Mirrors the CPU module's kvweave_dequantize_chunk_state signature.",
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
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt,
        pybind11::arg("num_threads") = 0);

    m.def("kvweave_dequantize_chunk_state_into", &kvweave_dequantize_chunk_state_into_xpu,
        "Like kvweave_dequantize_chunk_state, but writes the result into the "
        "caller-provided contiguous CPU tensor `dst` (exactly num_layers*"
        "chunk_tokens*h_merged elements of output_dtype). merge_head_num > 1 "
        "folds per-head planes back to [layers, tokens, heads*head_dim] on the "
        "device first.",
        pybind11::arg("q_data"),
        pybind11::arg("scale_bytes"),
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
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt,
        pybind11::arg("merge_head_num") = 0,
        pybind11::arg("num_threads") = 0);

    m.def("kvweave_serialize_chunk_state_multi", &kvweave_serialize_chunk_state_multi_xpu,
        "Batched analog of kvweave_serialize_chunk_state for N independently"
        "-configured planes (e.g. Mamba conv-query/conv-key/conv-value/ssm). "
        "Collapses N host<->XPU round trips into 1 by uploading/downloading "
        "all N planes together; per-item output is byte-identical to N calls "
        "of kvweave_serialize_chunk_state. Requires all srcs share one dtype.",
        pybind11::arg("srcs"),
        pybind11::arg("header_bytes_list"),
        pybind11::arg("scale_ids"),
        pybind11::arg("qbits"),
        pybind11::arg("blocks_nums"),
        pybind11::arg("block_sizes"),
        pybind11::arg("head_nums"),
        pybind11::arg("head_dims"),
        pybind11::arg("num_layers_list"),
        pybind11::arg("rhs"),
        pybind11::arg("asyms"),
        pybind11::arg("scaling_methods"),
        pybind11::arg("signs_list"),
        pybind11::arg("perm_list"),
        pybind11::arg("num_threads") = 0);

    m.def("kvweave_dequantize_chunk_state_multi", &kvweave_dequantize_chunk_state_multi_xpu,
        "Batched analog of kvweave_dequantize_chunk_state for N independently"
        "-configured planes. Collapses N host<->XPU round trips into 1. "
        "Requires all items share one output_dtype.",
        pybind11::arg("q_datas"),
        pybind11::arg("scale_bytes_list"),
        pybind11::arg("num_layers_list"),
        pybind11::arg("chunk_tokens_list"),
        pybind11::arg("h_merged_list"),
        pybind11::arg("qbits"),
        pybind11::arg("blocks_nums"),
        pybind11::arg("block_sizes"),
        pybind11::arg("head_nums"),
        pybind11::arg("head_dims"),
        pybind11::arg("rhs"),
        pybind11::arg("asyms"),
        pybind11::arg("scaling_methods"),
        pybind11::arg("output_dtypes"),
        pybind11::arg("signs_list"),
        pybind11::arg("perm_list"),
        pybind11::arg("num_threads") = 0);

    m.def("kvweave_serialize_chunk", &kvweave_serialize_chunk_xpu,
        "Quantize a fused K/V tensor and pack a complete payload, on XPU. "
        "Mirrors the CPU module's kvweave_serialize_chunk signature so "
        "callers can select the native module without branching. Accepts/"
        "returns CPU tensors/bytes, transferring to/from XPU internally.",
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
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt,
        pybind11::arg("num_threads") = 0);

    m.def("kvweave_dequantize_chunk", &kvweave_dequantize_chunk_xpu,
        "Dequantize a fused K/V quant payload, on XPU. Mirrors the CPU "
        "module's kvweave_dequantize_chunk signature.",
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
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt,
        pybind11::arg("num_threads") = 0);

    m.def("kvweave_dequantize_chunk_into_4d", &kvweave_dequantize_chunk_into_4d_xpu,
        "Dequantize a fused K/V quant payload directly into a caller-provided "
        "[2, num_layers, chunk_tokens, h_merged] CPU tensor, on XPU. Mirrors "
        "the CPU module's kvweave_dequantize_chunk_into_4d signature "
        "(layer_num_threads is accepted but ignored -- XPU has no OMP "
        "layer-thread-sweep concept).",
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
        pybind11::arg("signs") = c10::nullopt,
        pybind11::arg("perm") = c10::nullopt,
        pybind11::arg("num_threads") = 0,
        pybind11::arg("layer_num_threads") = 1);

    m.def("set_quant_profiling", &quant_profile_set_enabled,
        "Enable/disable component-level SYCL kernel profiling "
        "(also settable via KVWEAVE_QUANT_PROFILE=1). When enabled, "
        "quantize/dequantize always use the multi-kernel code path so each "
        "algorithmic stage can be timed independently; this adds overhead "
        "and is intended for offline profiling, not production use.",
        pybind11::arg("enabled"));

    m.def("get_profile_stats", &get_profile_stats_impl,
        "Return cumulative per-stage timing stats collected since the last "
        "reset_profile_stats() call, as {stage_name: {total_ms, calls, pct}}. "
        "'pct' is computed independently within the quantize stages "
        "(LoadGather/Hadamard/ReduceQuantize/Pack4bit) and the dequantize "
        "stages (Unpack4bit/DequantLoad/HadamardInverse/PrecondWriteback), "
        "so each group sums to ~100% on its own.");

    m.def("precond_cache_stats", &precond_cache_stats_impl,
        "Precond cache counters {size, hits, misses, evictions} (for tests).");
    m.def("reset_profile_stats", &quant_profile_reset,
        "Reset all cumulative profiling stats to zero.");
}
