// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "quant_sycl.hpp"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <memory>
#include <mutex>
#include <type_traits>

// Work-group size for quantization kernels.
static constexpr int WG_SIZE = 256;

// ---------------------------------------------------------------------------
// Component-level performance profiling (see quant_sycl.hpp for the public
// API and the design rationale). Disabled by default; zero overhead on the
// default code path when off.
// ---------------------------------------------------------------------------
namespace {

constexpr size_t kStageCount = static_cast<size_t>(QuantStage::Count);

// Zero-initialized by static storage duration; no explicit init needed.
std::atomic<uint64_t> g_stage_ns[kStageCount];
std::atomic<uint64_t> g_stage_calls[kStageCount];
std::atomic<int> g_profiling_enabled{-1};  // -1 = uninitialized, 0 = off, 1 = on

bool profiling_enabled_from_env() {
    const char* v = std::getenv("KVWEAVE_QUANT_PROFILE");
    return v && v[0] != '\0' && v[0] != '0';
}

const char* stage_name(QuantStage s) {
    switch (s) {
        case QuantStage::LoadGather: return "LoadGather";
        case QuantStage::Hadamard: return "Hadamard";
        case QuantStage::ReduceQuantize: return "ReduceQuantize";
        case QuantStage::Pack4bit: return "Pack4bit";
        case QuantStage::Unpack4bit: return "Unpack4bit";
        case QuantStage::DequantLoad: return "DequantLoad";
        case QuantStage::HadamardInverse: return "HadamardInverse";
        case QuantStage::PrecondWriteback: return "PrecondWriteback";
        default: return "Unknown";
    }
}

void record_stage(QuantStage stage, uint64_t ns) {
    const size_t idx = static_cast<size_t>(stage);
    g_stage_ns[idx].fetch_add(ns, std::memory_order_relaxed);
    g_stage_calls[idx].fetch_add(1, std::memory_order_relaxed);
}

uint64_t event_duration_ns(const sycl::event& e) {
    const auto start = e.get_profiling_info<sycl::info::event_profiling::command_start>();
    const auto end = e.get_profiling_info<sycl::info::event_profiling::command_end>();
    return end > start ? (end - start) : uint64_t{0};
}

// Lazily creates (and caches) a profiling-enabled queue sharing the device and
// context of `base`. Only reached when profiling is enabled; the caller's
// production queue (e.g. PyTorch's XPU stream queue) is never modified.
sycl::queue& get_profiling_queue(sycl::queue& base) {
    static std::mutex mutex;
    static std::unique_ptr<sycl::queue> cached;
    static std::unique_ptr<sycl::device> cached_device;

    std::lock_guard<std::mutex> lock(mutex);
    if (!cached || *cached_device != base.get_device()) {
        cached_device = std::make_unique<sycl::device>(base.get_device());
        cached = std::make_unique<sycl::queue>(
            base.get_context(), *cached_device,
            sycl::property_list{sycl::property::queue::enable_profiling{}});
    }
    return *cached;
}

// Returns log4(chunk_size) (the number of radix-4 register-tile +
// one-time-transpose rounds needed) when chunk_size is an exact power of 4,
// else -1. Used to gate the SLM Hadamard path's transpose-based
// decomposition, which only applies cleanly when every round can process
// whole groups of 4 contiguous elements.
int64_t compute_log4_rounds(int64_t chunk_size) {
    int64_t c = chunk_size;
    int64_t rounds = 0;
    while (c > 1 && (c % 4) == 0) {
        c /= 4;
        ++rounds;
    }
    return (c == 1) ? rounds : -1;
}

// Computes the largest power-of-two chunk_size that can safely use the SLM/
// fused-kernel path on `dev`, derived from its actual reported local memory
// capacity rather than a value tuned to one specific GPU.
int64_t compute_max_slm_chunk(sycl::device& dev) {
    // Env override for backends where the device query misbehaves.
    if (const char* v = std::getenv("KVWEAVE_MAX_SLM_CHUNK")) {
        const int64_t override_val = std::atoll(v);
        if (override_val > 0 && (override_val & (override_val - 1)) == 0) {
            return override_val;
        }
    }

    const int64_t local_mem_bytes =
        static_cast<int64_t>(dev.get_info<sycl::info::device::local_mem_size>());

    // Stay clear of the exact SLM capacity (can hang the driver):
    // budget = min(90% of nominal, nominal - 4KB).
    constexpr double kPercentBudget = 0.90;
    constexpr int64_t kAbsoluteReserveBytes = 4096;
    const int64_t budget_bytes = std::min(
        static_cast<int64_t>(static_cast<double>(local_mem_bytes) * kPercentBudget),
        local_mem_bytes - kAbsoluteReserveBytes);

    // Reserve reduce_mem (2*WG_SIZE floats); a threshold safe for quantize is
    // safe for dequantize.
    const int64_t reduce_mem_floats = 2 * WG_SIZE;
    int64_t max_data_floats = budget_bytes / static_cast<int64_t>(sizeof(float)) - reduce_mem_floats;

    // Reserve a second chunk_size scratch for the radix-4 Hadamard ping-pong.
    max_data_floats /= 2;

    // Degenerate query: disable the SLM path (0 forces the large-chunk path).
    if (max_data_floats < WG_SIZE) return 0;

    int64_t chunk = 1;
    while (chunk * 2 <= max_data_floats) chunk *= 2;
    return chunk;
}

// Caches compute_max_slm_chunk() per device so the query only runs once per
// distinct device for the process lifetime (this is on the hot path).
int64_t get_max_slm_chunk(sycl::queue& q) {
    static std::mutex mutex;
    static std::unique_ptr<sycl::device> cached_device;
    static int64_t cached_value = -1;

    std::lock_guard<std::mutex> lock(mutex);
    if (!cached_device || *cached_device != q.get_device()) {
        cached_device = std::make_unique<sycl::device>(q.get_device());
        cached_value = compute_max_slm_chunk(*cached_device);
    }
    return cached_value;
}

}  // namespace

void quant_profile_set_enabled(bool enabled) {
    g_profiling_enabled.store(enabled ? 1 : 0, std::memory_order_relaxed);
}

bool quant_profile_is_enabled() {
    int state = g_profiling_enabled.load(std::memory_order_relaxed);
    if (state < 0) {
        state = profiling_enabled_from_env() ? 1 : 0;
        g_profiling_enabled.store(state, std::memory_order_relaxed);
    }
    return state != 0;
}

void quant_profile_reset() {
    for (auto& v : g_stage_ns) v.store(0, std::memory_order_relaxed);
    for (auto& v : g_stage_calls) v.store(0, std::memory_order_relaxed);
}

std::vector<QuantStageStat> quant_profile_snapshot() {
    std::vector<QuantStageStat> out;
    out.reserve(kStageCount);
    for (size_t i = 0; i < kStageCount; ++i) {
        out.push_back({stage_name(static_cast<QuantStage>(i)),
                       g_stage_ns[i].load(std::memory_order_relaxed),
                       g_stage_calls[i].load(std::memory_order_relaxed)});
    }
    return out;
}

// RAII guard for a SYCL device scratch allocation.  On normal completion the
// caller calls release() and hands the pointer to an async host_task free
// chained on the final kernel.  If a submit throws before that hand-off, the
// guard drains the queue and frees the buffer, so scratch is never leaked on
// the exception path.
template <typename T>
class DeviceScratch {
public:
    DeviceScratch(T* ptr, sycl::queue& q) : ptr_(ptr), q_(q) {}
    ~DeviceScratch() {
        if (ptr_) {
            try { q_.wait(); } catch (...) {}
            sycl::free(ptr_, q_);
        }
    }
    DeviceScratch(const DeviceScratch&) = delete;
    DeviceScratch& operator=(const DeviceScratch&) = delete;
    T* get() const { return ptr_; }
    void release() { ptr_ = nullptr; }

private:
    T* ptr_;
    sycl::queue& q_;
};

// ---------------------------------------------------------------------------
// vec4 contiguous load/write-back: stride==1, no permutation,
// element_count % 4 == 0.
// ---------------------------------------------------------------------------
template<typename KVType>
class LoadGatherVec4Kernel;

template<typename KVType>
static sycl::event load_gather_contiguous_vec4(
    sycl::queue& q,
    const KVType* src,
    float* scratch,
    int64_t element_count,
    const std::vector<sycl::event>& deps)
{
    const int64_t num_groups = element_count / 4;
    const int64_t global_size = ((num_groups + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        cgh.parallel_for<LoadGatherVec4Kernel<KVType>>(
            sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t g = static_cast<int64_t>(item.get_global_id(0));
                if (g >= num_groups) return;
                auto src_mptr = sycl::address_space_cast<
                    sycl::access::address_space::global_space,
                    sycl::access::decorated::no>(src);
                auto dst_mptr = sycl::address_space_cast<
                    sycl::access::address_space::global_space,
                    sycl::access::decorated::no>(scratch);
                sycl::vec<KVType, 4> sv;
                sv.load(static_cast<size_t>(g), src_mptr);
                sv.template convert<float>().store(static_cast<size_t>(g), dst_mptr);
            });
    });
}

template<typename KVType>
class PrecondWritebackVec4Kernel;

template<typename KVType>
static sycl::event precond_writeback_contiguous_vec4(
    sycl::queue& q,
    const float* scratch,
    KVType* dst,
    int64_t element_count,
    const std::vector<sycl::event>& deps)
{
    const int64_t num_groups = element_count / 4;
    const int64_t global_size = ((num_groups + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        cgh.parallel_for<PrecondWritebackVec4Kernel<KVType>>(
            sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t g = static_cast<int64_t>(item.get_global_id(0));
                if (g >= num_groups) return;
                auto src_mptr = sycl::address_space_cast<
                    sycl::access::address_space::global_space,
                    sycl::access::decorated::no>(scratch);
                auto dst_mptr = sycl::address_space_cast<
                    sycl::access::address_space::global_space,
                    sycl::access::decorated::no>(dst);
                sycl::vec<float, 4> fv;
                fv.load(static_cast<size_t>(g), src_mptr);
                fv.template convert<KVType>().store(static_cast<size_t>(g), dst_mptr);
            });
    });
}

// ---------------------------------------------------------------------------
// Quantize kernel: one work-group per chunk
// Small chunks use SLM; large chunks use global scratch with multi-kernel
// Hadamard.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Global-memory Hadamard: one butterfly stage over all chunks per launch;
// log2(chunk_size) launches total.
// ---------------------------------------------------------------------------
class HadamardStageBatchedKernel;

static sycl::event hadamard_stage_global_batched(
    sycl::queue& q,
    float* base,             // scratch: num_chunks contiguous chunks of chunk_size
    int64_t chunk_size,      // n, power of two, same for every chunk
    int64_t num_chunks,
    int64_t h,                // butterfly half-stride for this stage
    const std::vector<sycl::event>& deps)
{
    const int64_t num_pairs = chunk_size / 2;
    const int64_t total_pairs = num_chunks * num_pairs;
    const int64_t global_size = ((total_pairs + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;

    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        cgh.parallel_for<HadamardStageBatchedKernel>(
            sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t gid = static_cast<int64_t>(item.get_global_id(0));
                if (gid >= total_pairs) return;
                const int64_t chunk_id = gid / num_pairs;
                const int64_t local_idx = gid % num_pairs;
                float* buf = base + chunk_id * chunk_size;
                const int64_t stride = h << 1;
                int64_t block = local_idx / h;
                int64_t off_in_block = local_idx % h;
                int64_t i = block * stride + off_in_block;
                float a = buf[i];
                float b = buf[i + h];
                buf[i]     = a + b;
                buf[i + h] = a - b;
            });
    });
}

// Vec4 variant for h >= 4 (contiguous on both sides).
class HadamardStageBatchedVec4Kernel;

static sycl::event hadamard_stage_global_batched_vec4(
    sycl::queue& q,
    float* base,
    int64_t chunk_size,
    int64_t num_chunks,
    int64_t h,                // butterfly half-stride; caller guarantees h >= 4
    const std::vector<sycl::event>& deps)
{
    const int64_t groups_per_h = h / 4;
    const int64_t groups_per_chunk = chunk_size / 8;  // (chunk_size/2)/4
    const int64_t total_groups = num_chunks * groups_per_chunk;
    const int64_t global_size = ((total_groups + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;

    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        cgh.parallel_for<HadamardStageBatchedVec4Kernel>(
            sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t gid = static_cast<int64_t>(item.get_global_id(0));
                if (gid >= total_groups) return;
                const int64_t chunk_id = gid / groups_per_chunk;
                const int64_t group_idx = gid % groups_per_chunk;
                float* buf = base + chunk_id * chunk_size;
                const int64_t stride = h << 1;
                const int64_t block = group_idx / groups_per_h;
                const int64_t group_in_block = group_idx % groups_per_h;
                const int64_t i = block * stride + group_in_block * 4;

                auto mptr = sycl::address_space_cast<
                    sycl::access::address_space::global_space,
                    sycl::access::decorated::no>(buf);
                const size_t vidx_a = static_cast<size_t>(i / 4);
                const size_t vidx_b = static_cast<size_t>((i + h) / 4);
                sycl::vec<float, 4> va, vb;
                va.load(vidx_a, mptr);
                vb.load(vidx_b, mptr);
                const sycl::vec<float, 4> sum = va + vb;
                const sycl::vec<float, 4> diff = va - vb;
                sum.store(vidx_a, mptr);
                diff.store(vidx_b, mptr);
            });
    });
}

// Fuses stages h=1..block_size/2 into one launch (pairs stay within a block
// when 2h <= block_size). Plain per-stage SLM loop.
class HadamardBlockLocalKernel;

static sycl::event hadamard_block_local_batched(
    sycl::queue& q,
    float* base,
    int64_t block_size,      // B, power of two, always >= WG_SIZE when > 1
    int64_t num_blocks,      // total blocks across all chunks
    const std::vector<sycl::event>& deps)
{
    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        auto local_block = sycl::local_accessor<float, 1>(sycl::range<1>(static_cast<size_t>(block_size)), cgh);
        cgh.parallel_for<HadamardBlockLocalKernel>(
            sycl::nd_range<1>(static_cast<size_t>(num_blocks) * WG_SIZE, WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t block_id = static_cast<int64_t>(item.get_group(0));
                const int lid = static_cast<int>(item.get_local_id(0));
                const int wg_size = static_cast<int>(item.get_local_range(0));
                float* blk = base + block_id * block_size;
                float* local_buf = local_block.get_multi_ptr<sycl::access::decorated::no>().get_raw();

                for (int64_t i = lid; i < block_size; i += wg_size)
                    local_buf[i] = blk[i];
                sycl::group_barrier(item.get_group());

                for (int64_t h = 1; h < block_size; h <<= 1) {
                    const int64_t bfly_stride = h << 1;
                    for (int64_t p = lid; p < block_size / 2; p += wg_size) {
                        int64_t blk_idx = p / h;
                        int64_t off_in_block = p % h;
                        int64_t idx = blk_idx * bfly_stride + off_in_block;
                        float a = local_buf[idx];
                        float b = local_buf[idx + h];
                        local_buf[idx]     = a + b;
                        local_buf[idx + h] = a - b;
                    }
                    sycl::group_barrier(item.get_group());
                }

                for (int64_t i = lid; i < block_size; i += wg_size)
                    blk[i] = local_buf[i];
            });
    });
}

// Multiply buffer by a constant (vec4 body + scalar tail).
class ScaleKernelVec4;
class ScaleKernelTail;

static sycl::event scale_buffer(
    sycl::queue& q,
    float* buf,
    int64_t n,
    float factor,
    const std::vector<sycl::event>& deps)
{
    const int64_t num_groups = n / 4;
    const int64_t tail = n - num_groups * 4;

    sycl::event main_event;
    if (num_groups > 0) {
        const int64_t global_size = ((num_groups + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
        main_event = q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(deps);
            cgh.parallel_for<ScaleKernelVec4>(
                sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int64_t idx = static_cast<int64_t>(item.get_global_id(0));
                    if (idx >= num_groups) return;
                    auto mptr = sycl::address_space_cast<
                        sycl::access::address_space::global_space,
                        sycl::access::decorated::no>(buf);
                    const size_t vidx = static_cast<size_t>(idx);
                    sycl::vec<float, 4> v;
                    v.load(vidx, mptr);
                    v *= factor;
                    v.store(vidx, mptr);
                });
        });
    }

    if (tail == 0) {
        return main_event;
    }

    std::vector<sycl::event> tail_deps = deps;
    if (num_groups > 0) tail_deps.push_back(main_event);
    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(tail_deps);
        cgh.parallel_for<ScaleKernelTail>(
            sycl::range<1>(static_cast<size_t>(tail)),
            [=](sycl::item<1> item) {
                const int64_t idx = num_groups * 4 + static_cast<int64_t>(item.get_id(0));
                buf[idx] *= factor;
            });
    });
}

template<typename KVType, typename QType, bool Pack4Bit>
class QuantizeKernel;

template<typename KVType, typename QType, bool Pack4Bit>
class QuantizeKernelLarge;

// Pack4Bit: write two 4-bit values per byte, chunk-contiguous layout
// (private to quantize/dequantize_kvcache_sycl; only instantiated with
// int8_t).
template<typename KVType, typename QType, bool Pack4Bit = false>
sycl::event quantize_block_sycl_impl(
    sycl::queue& q,
    const KVType* src,
    QType* dst,
    float* scales_out,
    float* zps_out,
    int64_t element_count,
    const sycl_quantization_args& args,
    const std::vector<sycl::event>& deps)
{
    static_assert(!Pack4Bit || std::is_same_v<QType, int8_t>,
                  "Pack4Bit is only valid for QType=int8_t");

    int64_t chunks_per_layer = 1;
    if (args.scaling_method == "per_token") {
        chunks_per_layer = static_cast<int64_t>(args.blocks_num) * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        chunks_per_layer = args.head_dim;
    }

    const int64_t num_layers = args.num_layers > 0 ? args.num_layers : 1;
    const int64_t num_chunks = num_layers * chunks_per_layer;
    const int64_t chunk_size = element_count / num_chunks;
    // Per-layer element count; for per_channel, chunk_id/stride is the layer and
    // chunk_id%stride the channel.
    const int64_t single_layer_numel = element_count / num_layers;
    const bool is_per_channel = (args.scaling_method == "per_channel");
    const int64_t stride = is_per_channel ? args.head_dim : 1;

    // Fused-source addressing (SLM path only; quantize_kvcache_sycl routes
    // fused calls that can't take the SLM path through a split gather first).
    const bool fused_src = args.fused_src_head_num > 0;
    const int64_t f_head_num = fused_src ? args.fused_src_head_num : 1;
    const int64_t f_head_dim = args.head_dim;
    const int64_t f_hidden = f_head_num * f_head_dim;
    const int64_t f_tokens = fused_src ? single_layer_numel / f_head_dim : 0;
    const int64_t src_stride = fused_src ? (is_per_channel ? f_hidden : 1) : stride;

    const int qbit = args.qbit;
    const bool asym = args.asym;
    const bool rh = args.rh;
    // Large-chunk path: forward gather.
    const int32_t* perm = args.perm;
    const float* signs = args.signs;
    // SLM path: inverse-permutation scatter.
    const int32_t* inv_perm = args.inv_perm;
    const float* signs_reordered = args.signs_reordered;

    const int64_t qmax_int = (1 << (qbit - 1)) - 1;
    const int64_t qmin_int = -(1 << (qbit - 1));
    const float qmax_float = static_cast<float>(qmax_int);
    const float qmin_float = static_cast<float>(qmin_int);
    const float inv_sqrt_n = 1.0f / std::sqrt(static_cast<float>(chunk_size));

    const bool profiling = quant_profile_is_enabled();
    const int64_t max_slm_chunk = get_max_slm_chunk(q);
    const bool use_local_mem = !profiling && (chunk_size <= max_slm_chunk);

    if (!use_local_mem && profiling) {
        std::fprintf(stderr,
                      "[kvweave-quant] chunk_size=%lld exceeds detected SLM capacity "
                      "(max_slm_chunk=%lld); quantize falling back to the global-memory "
                      "scratch path\n",
                      static_cast<long long>(chunk_size), static_cast<long long>(max_slm_chunk));
    }

    if (use_local_mem) {
        // Small-chunk path: local memory for data + Hadamard
        const int64_t rounds_L = rh ? compute_log4_rounds(chunk_size) : -1;
        const bool use_transpose_scheme = rounds_L >= 1;
        return q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(deps);
            auto local_data = sycl::local_accessor<float, 1>(sycl::range<1>(static_cast<size_t>(chunk_size)), cgh);
            auto reduce_mem = sycl::local_accessor<float, 1>(sycl::range<1>(2 * WG_SIZE), cgh);
            auto local_scratch = sycl::local_accessor<float, 1>(
                sycl::range<1>(static_cast<size_t>(use_transpose_scheme ? chunk_size : 1)), cgh);

            cgh.parallel_for<QuantizeKernel<KVType, QType, Pack4Bit>>(
                sycl::nd_range<1>(static_cast<size_t>(num_chunks) * WG_SIZE, WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int chunk_id = static_cast<int>(item.get_group(0));
                    const int lid = static_cast<int>(item.get_local_id(0));
                    const int wg_size = static_cast<int>(item.get_local_range(0));
                    float* local_buf = local_data.get_multi_ptr<sycl::access::decorated::no>().get_raw();
                    float* red_buf = reduce_mem.get_multi_ptr<sycl::access::decorated::no>().get_raw();

                    const int64_t offset = is_per_channel
                        ? (chunk_id / stride) * single_layer_numel + (chunk_id % stride)
                        : chunk_id * chunk_size;
                    int64_t src_offset = offset;
                    if (fused_src) {
                        const int64_t unit = chunk_id / chunks_per_layer;
                        const int64_t in_unit = chunk_id % chunks_per_layer;
                        src_offset = (unit / f_head_num) * f_tokens * f_hidden
                            + (unit % f_head_num) * f_head_dim
                            + (is_per_channel ? in_unit : in_unit * f_hidden);
                    }

                    // Iterate over physical index m (sequential HBM read); apply inv_perm[m] on
                    // the SLM write.
                    if (rh && (inv_perm || signs_reordered)) {
                        for (int64_t m = lid; m < chunk_size; m += wg_size) {
                            float v = static_cast<float>(src[m * src_stride + src_offset]);
                            if (signs_reordered) v *= signs_reordered[m];
                            int64_t k = inv_perm ? static_cast<int64_t>(inv_perm[m]) : m;
                            local_buf[k] = v;
                        }
                    } else if constexpr (!std::is_same_v<KVType, sycl::ext::oneapi::bfloat16>) {
                        // vec4 load when stride==1 (no vec for bfloat16).
                        if (src_stride == 1 && (!fused_src || chunk_size % 4 == 0)) {
                            const int64_t num_vec_groups = chunk_size / 4;
                            auto src_mptr = sycl::address_space_cast<
                                sycl::access::address_space::global_space,
                                sycl::access::decorated::no>(src + src_offset);
                            auto local_mptr = sycl::address_space_cast<
                                sycl::access::address_space::local_space,
                                sycl::access::decorated::no>(local_buf);
                            for (int64_t g = lid; g < num_vec_groups; g += wg_size) {
                                sycl::vec<KVType, 4> sv;
                                sv.load(static_cast<size_t>(g), src_mptr);
                                sv.template convert<float>().store(static_cast<size_t>(g), local_mptr);
                            }
                        } else {
                            for (int64_t i = lid; i < chunk_size; i += wg_size) {
                                local_buf[i] = static_cast<float>(src[i * src_stride + src_offset]);
                            }
                        }
                    } else {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            local_buf[i] = static_cast<float>(src[i * src_stride + src_offset]);
                        }
                    }
                    sycl::group_barrier(item.get_group());

                    // Min/max accumulators, populated below either by the
                    // fused Hadamard-normalize pass (rh) or a plain scan
                    // (!rh); reduced via subgroup shuffle further down.
                    float lmin = std::numeric_limits<float>::max();
                    float lmax = std::numeric_limits<float>::lowest();

                    // Hadamard transform
                    if (rh) {
                        if (rounds_L >= 1) {
                            // Radix-4: per round, stages h=1,2 in registers, then an SLM transpose
                            // (ping-pong via scratch_buf) rotates the next base-4 digit.
                            constexpr int64_t kR = 4;
                            const int64_t num_groups = chunk_size / kR;
                            float* scratch_buf = local_scratch.get_multi_ptr<sycl::access::decorated::no>().get_raw();

                            for (int64_t round = 0; round < rounds_L; ++round) {
                                for (int64_t g = lid; g < num_groups; g += wg_size) {
                                    const int64_t base = g * kR;
                                    const float r0 = local_buf[base + 0];
                                    const float r1 = local_buf[base + 1];
                                    const float r2 = local_buf[base + 2];
                                    const float r3 = local_buf[base + 3];
                                    const float a0 = r0 + r1, a1 = r0 - r1;
                                    const float a2 = r2 + r3, a3 = r2 - r3;
                                    local_buf[base + 0] = a0 + a2;
                                    local_buf[base + 1] = a1 + a3;
                                    local_buf[base + 2] = a0 - a2;
                                    local_buf[base + 3] = a1 - a3;
                                }
                                sycl::group_barrier(item.get_group());

                                if (round + 1 < rounds_L) {
                                    // Swap the base-4 digit at position 0
                                    // with the digit at position (round+1),
                                    // so that digit becomes fast/contiguous
                                    // for the next round.
                                    const int shift1 = static_cast<int>((round + 1) * 2);
                                    for (int64_t a = lid; a < chunk_size; a += wg_size) {
                                        const int64_t d0 = a & 0x3LL;
                                        const int64_t d1 = (a >> shift1) & 0x3LL;
                                        const int64_t new_a = (a & ~0x3LL & ~(0x3LL << shift1)) | d1 | (d0 << shift1);
                                        scratch_buf[new_a] = local_buf[a];
                                    }
                                    sycl::group_barrier(item.get_group());
                                    float* tmp = local_buf;
                                    local_buf = scratch_buf;
                                    scratch_buf = tmp;
                                }
                            }

                            // Final un-transpose; write into the buffer that is not local_buf to avoid
                            // aliasing.
                            {
                                const int top_shift = static_cast<int>((rounds_L - 1) * 2);
                                for (int64_t a = lid; a < chunk_size; a += wg_size) {
                                    const int64_t bottom = a & 0x3LL;
                                    const int64_t rest = a >> 2;
                                    const int64_t n = rest | (bottom << top_shift);
                                    scratch_buf[n] = local_buf[a];
                                }
                                sycl::group_barrier(item.get_group());
                                local_buf = scratch_buf;
                            }
                        } else {
                            for (int64_t h = 1; h < chunk_size; h <<= 1) {
                                const int64_t bfly_stride = h << 1;
                                for (int64_t base = lid; base < chunk_size / 2; base += wg_size) {
                                    int64_t block = base / h;
                                    int64_t off_in_block = base % h;
                                    int64_t idx = block * bfly_stride + off_in_block;
                                    float a = local_buf[idx];
                                    float b = local_buf[idx + h];
                                    local_buf[idx]     = a + b;
                                    local_buf[idx + h] = a - b;
                                }
                                sycl::group_barrier(item.get_group());
                            }
                        }
                        // Normalize and accumulate min/max in one pass; no extra barrier needed
                        // (each lane reads only its own writes).
                        if (chunk_size % 4 == 0) {
                            sycl::vec<float, 4> vmin(std::numeric_limits<float>::max());
                            sycl::vec<float, 4> vmax(std::numeric_limits<float>::lowest());
                            auto local_mptr = sycl::address_space_cast<
                                sycl::access::address_space::local_space,
                                sycl::access::decorated::no>(local_buf);
                            const int64_t num_vec_groups = chunk_size / 4;
                            for (int64_t g = lid; g < num_vec_groups; g += wg_size) {
                                sycl::vec<float, 4> v;
                                v.load(static_cast<size_t>(g), local_mptr);
                                v *= inv_sqrt_n;
                                v.store(static_cast<size_t>(g), local_mptr);
                                vmin = sycl::fmin(vmin, v);
                                vmax = sycl::fmax(vmax, v);
                            }
                            lmin = sycl::fmin(sycl::fmin(vmin[0], vmin[1]), sycl::fmin(vmin[2], vmin[3]));
                            lmax = sycl::fmax(sycl::fmax(vmax[0], vmax[1]), sycl::fmax(vmax[2], vmax[3]));
                        } else {
                            for (int64_t i = lid; i < chunk_size; i += wg_size) {
                                float v = local_buf[i] * inv_sqrt_n;
                                local_buf[i] = v;
                                lmin = sycl::fmin(lmin, v);
                                lmax = sycl::fmax(lmax, v);
                            }
                        }
                    } else {
                        if (chunk_size % 4 == 0) {
                            sycl::vec<float, 4> vmin(std::numeric_limits<float>::max());
                            sycl::vec<float, 4> vmax(std::numeric_limits<float>::lowest());
                            auto local_mptr = sycl::address_space_cast<
                                sycl::access::address_space::local_space,
                                sycl::access::decorated::no>(local_buf);
                            const int64_t num_vec_groups = chunk_size / 4;
                            for (int64_t g = lid; g < num_vec_groups; g += wg_size) {
                                sycl::vec<float, 4> v;
                                v.load(static_cast<size_t>(g), local_mptr);
                                vmin = sycl::fmin(vmin, v);
                                vmax = sycl::fmax(vmax, v);
                            }
                            lmin = sycl::fmin(sycl::fmin(vmin[0], vmin[1]), sycl::fmin(vmin[2], vmin[3]));
                            lmax = sycl::fmax(sycl::fmax(vmax[0], vmax[1]), sycl::fmax(vmax[2], vmax[3]));
                        } else {
                            for (int64_t i = lid; i < chunk_size; i += wg_size) {
                                float v = local_buf[i];
                                lmin = sycl::fmin(lmin, v);
                                lmax = sycl::fmax(lmax, v);
                            }
                        }
                    }

                    // Subgroup shuffle reduce, then combine per-subgroup partials via SLM.
                    auto sg = item.get_sub_group();
                    const int sg_id = static_cast<int>(sg.get_group_id()[0]);
                    const int sg_lid = static_cast<int>(sg.get_local_id()[0]);
                    const int num_sg = static_cast<int>(sg.get_group_range()[0]);
                    lmin = sycl::reduce_over_group(sg, lmin, sycl::minimum<float>());
                    lmax = sycl::reduce_over_group(sg, lmax, sycl::maximum<float>());
                    if (sg_lid == 0) {
                        red_buf[sg_id] = lmin;
                        red_buf[wg_size + sg_id] = lmax;
                    }
                    // Barrier: publish local_buf and subgroup partials.
                    sycl::group_barrier(item.get_group());

                    // Compute scale
                    float scale = 0.0f, zeropoint = 0.0f;
                    if (lid == 0) {
                        float min_val = red_buf[0], max_val = red_buf[wg_size];
                        for (int s = 1; s < num_sg; ++s) {
                            min_val = sycl::fmin(min_val, red_buf[s]);
                            max_val = sycl::fmax(max_val, red_buf[wg_size + s]);
                        }
                        if (asym) {
                            scale = (max_val - min_val) / (qmax_float - qmin_float);
                            zeropoint = min_val - qmin_float * scale;
                        } else {
                            scale = sycl::fmax(sycl::fabs(min_val), sycl::fabs(max_val)) / qmax_float;
                        }
                        red_buf[0] = scale;
                        red_buf[1] = zeropoint;
                        scales_out[chunk_id] = scale;
                        zps_out[chunk_id] = zeropoint;
                    }
                    sycl::group_barrier(item.get_group());
                    scale = red_buf[0];
                    zeropoint = red_buf[1];
                    float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;

                    // Quantize
                    if constexpr (Pack4Bit) {
                        // Fused int4 packing: chunk-contiguous layout (chunk_size is even).
                        const int64_t packed_chunk_size = chunk_size / 2;
                        QType* packed_dst = dst + static_cast<int64_t>(chunk_id) * packed_chunk_size;
                        if (packed_chunk_size % 4 == 0) {
                            // Vec8 batch: 4 packed bytes (8 logical elements)
                            // per work-item. packed_chunk_size = chunk_size/2
                            // is a multiple of 4 whenever chunk_size is a
                            // power of two >= 8 (always true in practice).
                            const int64_t num_groups = packed_chunk_size / 4;
                            auto local_mptr = sycl::address_space_cast<
                                sycl::access::address_space::local_space,
                                sycl::access::decorated::no>(local_buf);
                            auto packed_mptr = sycl::address_space_cast<
                                sycl::access::address_space::global_space,
                                sycl::access::decorated::no>(packed_dst);
                            for (int64_t g = lid; g < num_groups; g += wg_size) {
                                sycl::vec<float, 8> v;
                                v.load(static_cast<size_t>(g), local_mptr);
                                sycl::vec<float, 8> qf = sycl::clamp(
                                    sycl::round((v - sycl::vec<float, 8>(zeropoint)) * inv_scale),
                                    sycl::vec<float, 8>(qmin_float), sycl::vec<float, 8>(qmax_float));
                                sycl::vec<int8_t, 4> packed;
                                for (int k = 0; k < 4; ++k) {
                                    const uint8_t lo = static_cast<uint8_t>(static_cast<int8_t>(
                                        static_cast<int>(qf[k * 2]))) & 0x0F;
                                    const uint8_t hi = static_cast<uint8_t>(static_cast<int8_t>(
                                        static_cast<int>(qf[k * 2 + 1]))) & 0x0F;
                                    packed[k] = static_cast<int8_t>(lo | (hi << 4));
                                }
                                packed.store(static_cast<size_t>(g), packed_mptr);
                            }
                        } else {
                            for (int64_t p = lid; p < packed_chunk_size; p += wg_size) {
                                const int64_t i0 = p * 2, i1 = i0 + 1;
                                const int q0 = static_cast<int>(sycl::clamp(
                                    sycl::round((local_buf[i0] - zeropoint) * inv_scale), qmin_float, qmax_float));
                                const int q1 = static_cast<int>(sycl::clamp(
                                    sycl::round((local_buf[i1] - zeropoint) * inv_scale), qmin_float, qmax_float));
                                const uint8_t lo = static_cast<uint8_t>(static_cast<int8_t>(q0)) & 0x0F;
                                const uint8_t hi = static_cast<uint8_t>(static_cast<int8_t>(q1)) & 0x0F;
                                packed_dst[p] = static_cast<QType>(static_cast<int8_t>(lo | (hi << 4)));
                            }
                        }
                    } else {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            float val = local_buf[i];
                            float q_val = sycl::clamp(sycl::round((val - zeropoint) * inv_scale), qmin_float, qmax_float);
                            dst[i * stride + offset] = static_cast<QType>(static_cast<int>(q_val));
                        }
                    }
                });
        });
    } else {
        // Large-chunk path (global scratch); also forced when profiling so each
        // stage is timed.
        sycl::queue& kq = profiling ? get_profiling_queue(q) : q;

        // Allocate a float scratch buffer for the entire element_count.
        float* scratch = sycl::malloc_device<float>(static_cast<size_t>(element_count), kq);
        DeviceScratch<float> scratch_guard(scratch, kq);

        // Step 1: Load into scratch (vec4 fast path when contiguous).
        const bool load_fast_contig = (stride == 1) && !(rh && (perm || signs)) &&
                                       (element_count % 4 == 0);
        sycl::event load_event;
        if constexpr (!std::is_same_v<KVType, sycl::ext::oneapi::bfloat16>) {
            if (load_fast_contig) {
                load_event = load_gather_contiguous_vec4<KVType>(kq, src, scratch, element_count, deps);
            } else {
                load_event = kq.submit([&](sycl::handler& cgh) {
                    cgh.depends_on(deps);
                    const int64_t global_size = ((element_count + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
                    cgh.parallel_for(
                        sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
                        [=](sycl::nd_item<1> item) {
                            const int64_t gid = static_cast<int64_t>(item.get_global_id(0));
                            if (gid >= element_count) return;
                            int64_t chunk_id = gid / chunk_size;
                            int64_t i = gid % chunk_size;
                            int64_t offset = is_per_channel
                                ? (chunk_id / stride) * single_layer_numel + (chunk_id % stride)
                                : chunk_id * chunk_size;

                            float v;
                            if (rh && (perm || signs)) {
                                int64_t src_idx = perm ? static_cast<int64_t>(perm[i]) : i;
                                v = static_cast<float>(src[src_idx * stride + offset]);
                                if (signs) v *= signs[i];
                            } else {
                                v = static_cast<float>(src[i * stride + offset]);
                            }
                            scratch[gid] = v;
                        });
                });
            }
        } else {
            load_event = kq.submit([&](sycl::handler& cgh) {
                cgh.depends_on(deps);
                const int64_t global_size = ((element_count + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
                cgh.parallel_for(
                    sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
                    [=](sycl::nd_item<1> item) {
                        const int64_t gid = static_cast<int64_t>(item.get_global_id(0));
                        if (gid >= element_count) return;
                        int64_t chunk_id = gid / chunk_size;
                        int64_t i = gid % chunk_size;
                        int64_t offset = is_per_channel
                            ? (chunk_id / stride) * single_layer_numel + (chunk_id % stride)
                            : chunk_id * chunk_size;

                        float v;
                        if (rh && (perm || signs)) {
                            int64_t src_idx = perm ? static_cast<int64_t>(perm[i]) : i;
                            v = static_cast<float>(src[src_idx * stride + offset]);
                            if (signs) v *= signs[i];
                        } else {
                            v = static_cast<float>(src[i * stride + offset]);
                        }
                        scratch[gid] = v;
                    });
            });
        }
        if (profiling) {
            load_event.wait();
            record_stage(QuantStage::LoadGather, event_duration_ns(load_event));
        }

        // Step 2: Hadamard (if rh): block-local stages in one launch, then one
        // launch per cross-block stage.
        sycl::event had_event = load_event;
        if (rh) {
            uint64_t hadamard_ns = 0;
            sycl::event stage_event = load_event;
            std::vector<sycl::event> stage_deps = {load_event};

            const int64_t block_size = std::min(max_slm_chunk, chunk_size);
            int64_t h_start = 1;
            if (block_size > 1) {
                const int64_t num_blocks = element_count / block_size;
                stage_event = hadamard_block_local_batched(kq, scratch, block_size, num_blocks, stage_deps);
                if (profiling) {
                    stage_event.wait();
                    hadamard_ns += event_duration_ns(stage_event);
                }
                stage_deps = {stage_event};
                h_start = block_size;
            }

            for (int64_t h = h_start; h < chunk_size; h <<= 1) {
                stage_event = (h >= 4)
                    ? hadamard_stage_global_batched_vec4(kq, scratch, chunk_size, num_chunks, h, stage_deps)
                    : hadamard_stage_global_batched(kq, scratch, chunk_size, num_chunks, h, stage_deps);
                if (profiling) {
                    stage_event.wait();
                    hadamard_ns += event_duration_ns(stage_event);
                }
                stage_deps = {stage_event};
            }
            had_event = scale_buffer(kq, scratch, element_count, inv_sqrt_n, {stage_event});
            if (profiling) {
                had_event.wait();
                hadamard_ns += event_duration_ns(had_event);
                record_stage(QuantStage::Hadamard, hadamard_ns);
            }
        }

        // Step 3: Min/max reduction + quantize from scratch buffer
        auto quant_event = kq.submit([&](sycl::handler& cgh) {
            cgh.depends_on({had_event});
            auto reduce_mem = sycl::local_accessor<float, 1>(sycl::range<1>(2 * WG_SIZE), cgh);

            cgh.parallel_for<QuantizeKernelLarge<KVType, QType, Pack4Bit>>(
                sycl::nd_range<1>(static_cast<size_t>(num_chunks) * WG_SIZE, WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int chunk_id = static_cast<int>(item.get_group(0));
                    const int lid = static_cast<int>(item.get_local_id(0));
                    const int wg_size = static_cast<int>(item.get_local_range(0));
                    float* red_buf = reduce_mem.get_multi_ptr<sycl::access::decorated::no>().get_raw();

                    const int64_t offset = is_per_channel
                        ? (chunk_id / stride) * single_layer_numel + (chunk_id % stride)
                        : chunk_id * chunk_size;
                    const float* chunk_data = scratch + chunk_id * chunk_size;

                    // Min/max reduction (subgroup shuffle + SLM partials).
                    float lmin = std::numeric_limits<float>::max();
                    float lmax = std::numeric_limits<float>::lowest();
                    if (chunk_size % 4 == 0) {
                        sycl::vec<float, 4> vmin(std::numeric_limits<float>::max());
                        sycl::vec<float, 4> vmax(std::numeric_limits<float>::lowest());
                        auto data_mptr = sycl::address_space_cast<
                            sycl::access::address_space::global_space,
                            sycl::access::decorated::no>(chunk_data);
                        const int64_t num_vec_groups = chunk_size / 4;
                        for (int64_t g = lid; g < num_vec_groups; g += wg_size) {
                            sycl::vec<float, 4> v;
                            v.load(static_cast<size_t>(g), data_mptr);
                            vmin = sycl::fmin(vmin, v);
                            vmax = sycl::fmax(vmax, v);
                        }
                        lmin = sycl::fmin(sycl::fmin(vmin[0], vmin[1]), sycl::fmin(vmin[2], vmin[3]));
                        lmax = sycl::fmax(sycl::fmax(vmax[0], vmax[1]), sycl::fmax(vmax[2], vmax[3]));
                    } else {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            float v = chunk_data[i];
                            lmin = sycl::fmin(lmin, v);
                            lmax = sycl::fmax(lmax, v);
                        }
                    }
                    auto sg = item.get_sub_group();
                    const int sg_id = static_cast<int>(sg.get_group_id()[0]);
                    const int sg_lid = static_cast<int>(sg.get_local_id()[0]);
                    const int num_sg = static_cast<int>(sg.get_group_range()[0]);
                    lmin = sycl::reduce_over_group(sg, lmin, sycl::minimum<float>());
                    lmax = sycl::reduce_over_group(sg, lmax, sycl::maximum<float>());
                    if (sg_lid == 0) {
                        red_buf[sg_id] = lmin;
                        red_buf[wg_size + sg_id] = lmax;
                    }
                    sycl::group_barrier(item.get_group());

                    // Compute scale
                    float scale = 0.0f, zeropoint = 0.0f;
                    if (lid == 0) {
                        float min_val = red_buf[0], max_val = red_buf[wg_size];
                        for (int s = 1; s < num_sg; ++s) {
                            min_val = sycl::fmin(min_val, red_buf[s]);
                            max_val = sycl::fmax(max_val, red_buf[wg_size + s]);
                        }
                        if (asym) {
                            scale = (max_val - min_val) / (qmax_float - qmin_float);
                            zeropoint = min_val - qmin_float * scale;
                        } else {
                            scale = sycl::fmax(sycl::fabs(min_val), sycl::fabs(max_val)) / qmax_float;
                        }
                        red_buf[0] = scale;
                        red_buf[1] = zeropoint;
                        scales_out[chunk_id] = scale;
                        zps_out[chunk_id] = zeropoint;
                    }
                    sycl::group_barrier(item.get_group());
                    scale = red_buf[0];
                    zeropoint = red_buf[1];
                    float inv_scale = (scale != 0.0f) ? (1.0f / scale) : 0.0f;

                    // Quantize from scratch buffer, write to dst
                    if constexpr (Pack4Bit) {
                        const int64_t packed_chunk_size = chunk_size / 2;
                        QType* packed_dst = dst + static_cast<int64_t>(chunk_id) * packed_chunk_size;
                        if (packed_chunk_size % 4 == 0) {
                            const int64_t num_groups = packed_chunk_size / 4;
                            auto data_mptr = sycl::address_space_cast<
                                sycl::access::address_space::global_space,
                                sycl::access::decorated::no>(chunk_data);
                            auto packed_mptr = sycl::address_space_cast<
                                sycl::access::address_space::global_space,
                                sycl::access::decorated::no>(packed_dst);
                            for (int64_t g = lid; g < num_groups; g += wg_size) {
                                sycl::vec<float, 8> v;
                                v.load(static_cast<size_t>(g), data_mptr);
                                sycl::vec<float, 8> qf = sycl::clamp(
                                    sycl::round((v - sycl::vec<float, 8>(zeropoint)) * inv_scale),
                                    sycl::vec<float, 8>(qmin_float), sycl::vec<float, 8>(qmax_float));
                                sycl::vec<int8_t, 4> packed;
                                for (int k = 0; k < 4; ++k) {
                                    const uint8_t lo = static_cast<uint8_t>(static_cast<int8_t>(
                                        static_cast<int>(qf[k * 2]))) & 0x0F;
                                    const uint8_t hi = static_cast<uint8_t>(static_cast<int8_t>(
                                        static_cast<int>(qf[k * 2 + 1]))) & 0x0F;
                                    packed[k] = static_cast<int8_t>(lo | (hi << 4));
                                }
                                packed.store(static_cast<size_t>(g), packed_mptr);
                            }
                        } else {
                            for (int64_t p = lid; p < packed_chunk_size; p += wg_size) {
                                const int64_t i0 = p * 2, i1 = i0 + 1;
                                const int q0 = static_cast<int>(sycl::clamp(
                                    sycl::round((chunk_data[i0] - zeropoint) * inv_scale), qmin_float, qmax_float));
                                const int q1 = static_cast<int>(sycl::clamp(
                                    sycl::round((chunk_data[i1] - zeropoint) * inv_scale), qmin_float, qmax_float));
                                const uint8_t lo = static_cast<uint8_t>(static_cast<int8_t>(q0)) & 0x0F;
                                const uint8_t hi = static_cast<uint8_t>(static_cast<int8_t>(q1)) & 0x0F;
                                packed_dst[p] = static_cast<QType>(static_cast<int8_t>(lo | (hi << 4)));
                            }
                        }
                    } else {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            float val = chunk_data[i];
                            float q_val = sycl::clamp(sycl::round((val - zeropoint) * inv_scale), qmin_float, qmax_float);
                            dst[i * stride + offset] = static_cast<QType>(static_cast<int>(q_val));
                        }
                    }
                });
        });
        if (profiling) {
            quant_event.wait();
            record_stage(QuantStage::ReduceQuantize, event_duration_ns(quant_event));
        }

        // Success: hand scratch off to the async free (chained on quant_event).
        scratch_guard.release();
        kq.submit([&](sycl::handler& cgh) {
            cgh.depends_on(quant_event);
            cgh.host_task([=, &kq]() { sycl::free(scratch, kq); });
        });

        return quant_event;
    }
}

// ---------------------------------------------------------------------------
// Dequantize kernel: one work-group per chunk, with Hadamard support
// ---------------------------------------------------------------------------
template<typename KVType, typename QType, bool Pack4Bit>
class DequantizeKernel;

template<typename KVType, typename QType, bool Pack4Bit>
class DequantizeKernelLarge;

// Pack4Bit: src is chunk-contiguous packed nibbles.
template<typename KVType, typename QType, bool Pack4Bit = false>
sycl::event dequantize_block_sycl_impl(
    sycl::queue& q,
    const QType* src,
    KVType* dst,
    const float* scales_in,
    const float* zps_in,
    int64_t element_count,
    const sycl_quantization_args& args,
    const std::vector<sycl::event>& deps)
{
    static_assert(!Pack4Bit || std::is_same_v<QType, int8_t>,
                  "Pack4Bit is only valid for QType=int8_t");

    int64_t chunks_per_layer = 1;
    if (args.scaling_method == "per_token") {
        chunks_per_layer = static_cast<int64_t>(args.blocks_num) * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        chunks_per_layer = args.head_dim;
    }

    const int64_t num_layers = args.num_layers > 0 ? args.num_layers : 1;
    const int64_t num_chunks = num_layers * chunks_per_layer;
    const int64_t chunk_size = element_count / num_chunks;
    // Per-layer element count (per_channel: chunk_id/stride is the layer).
    const int64_t single_layer_numel = element_count / num_layers;
    const bool is_per_channel = (args.scaling_method == "per_channel");
    const int64_t stride = is_per_channel ? args.head_dim : 1;
    const bool rh = args.rh;
    // Large-chunk path: forward scatter.
    const int32_t* perm = args.perm;
    const float* signs = args.signs;
    // SLM path: inverse-permutation gather.
    const int32_t* inv_perm = args.inv_perm;
    const float* signs_reordered = args.signs_reordered;
    const float inv_sqrt_n = 1.0f / std::sqrt(static_cast<float>(chunk_size));

    // Fused-destination addressing (SLM path only; dequantize_kvcache_sycl
    // routes fused calls that can't take the SLM path through a split scratch).
    const bool fused_dst = args.fused_dst_head_num > 0;
    const int64_t f_head_num = fused_dst ? args.fused_dst_head_num : 1;
    const int64_t f_head_dim = args.head_dim;
    const int64_t f_hidden = f_head_num * f_head_dim;
    const int64_t f_tokens = fused_dst ? single_layer_numel / f_head_dim : 0;
    const int64_t dst_stride = fused_dst ? (is_per_channel ? f_hidden : 1) : stride;

    const bool profiling = quant_profile_is_enabled();
    const int64_t max_slm_chunk = get_max_slm_chunk(q);
    const bool use_local_mem = !profiling && (chunk_size <= max_slm_chunk);

    if (!use_local_mem && profiling) {
        std::fprintf(stderr,
                      "[kvweave-quant] chunk_size=%lld exceeds detected SLM capacity "
                      "(max_slm_chunk=%lld); dequantize falling back to the global-memory "
                      "scratch path\n",
                      static_cast<long long>(chunk_size), static_cast<long long>(max_slm_chunk));
    }

    if (use_local_mem) {
        const int64_t rounds_L = rh ? compute_log4_rounds(chunk_size) : -1;
        const bool use_transpose_scheme = rounds_L >= 1;
        return q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(deps);
            auto local_data = sycl::local_accessor<float, 1>(sycl::range<1>(static_cast<size_t>(chunk_size)), cgh);
            auto local_scratch = sycl::local_accessor<float, 1>(
                sycl::range<1>(static_cast<size_t>(use_transpose_scheme ? chunk_size : 1)), cgh);

            cgh.parallel_for<DequantizeKernel<KVType, QType, Pack4Bit>>(
                sycl::nd_range<1>(static_cast<size_t>(num_chunks) * WG_SIZE, WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int chunk_id = static_cast<int>(item.get_group(0));
                    const int lid = static_cast<int>(item.get_local_id(0));
                    const int wg_size = static_cast<int>(item.get_local_range(0));
                    float* local_buf = local_data.get_multi_ptr<sycl::access::decorated::no>().get_raw();
                    const int64_t offset = is_per_channel
                        ? (chunk_id / stride) * single_layer_numel + (chunk_id % stride)
                        : chunk_id * chunk_size;
                    int64_t dst_offset = offset;
                    if (fused_dst) {
                        const int64_t unit = chunk_id / chunks_per_layer;
                        const int64_t in_unit = chunk_id % chunks_per_layer;
                        dst_offset = (unit / f_head_num) * f_tokens * f_hidden
                            + (unit % f_head_num) * f_head_dim
                            + (is_per_channel ? in_unit : in_unit * f_hidden);
                    }
                    const float scale = scales_in[chunk_id];
                    const float zeropoint = zps_in[chunk_id];

                    // Each thread unpacks both nibbles of one byte (avoids redundant byte reads).
                    if constexpr (Pack4Bit) {
                        const int64_t packed_chunk_size = chunk_size / 2;
                        const QType* packed_src = src + static_cast<int64_t>(chunk_id) * packed_chunk_size;
                        if (packed_chunk_size % 4 == 0) {
                            // Vec4 batch: 4 packed bytes (8 logical elements)
                            // per work-item.
                            const int64_t num_groups = packed_chunk_size / 4;
                            auto packed_mptr = sycl::address_space_cast<
                                sycl::access::address_space::global_space,
                                sycl::access::decorated::no>(packed_src);
                            auto local_mptr = sycl::address_space_cast<
                                sycl::access::address_space::local_space,
                                sycl::access::decorated::no>(local_buf);
                            for (int64_t g = lid; g < num_groups; g += wg_size) {
                                sycl::vec<int8_t, 4> pv;
                                pv.load(static_cast<size_t>(g), packed_mptr);
                                sycl::vec<float, 8> out;
                                for (int k = 0; k < 4; ++k) {
                                    const uint8_t byte = static_cast<uint8_t>(pv[k]);
                                    const uint8_t lo = byte & 0x0F;
                                    const uint8_t hi = (byte >> 4) & 0x0F;
                                    const int8_t qlo = (lo >= 8) ? static_cast<int8_t>(static_cast<int>(lo) - 16) : static_cast<int8_t>(lo);
                                    const int8_t qhi = (hi >= 8) ? static_cast<int8_t>(static_cast<int>(hi) - 16) : static_cast<int8_t>(hi);
                                    out[k * 2]     = static_cast<float>(qlo) * scale + zeropoint;
                                    out[k * 2 + 1] = static_cast<float>(qhi) * scale + zeropoint;
                                }
                                out.store(static_cast<size_t>(g), local_mptr);
                            }
                        } else {
                            for (int64_t p = lid; p < packed_chunk_size; p += wg_size) {
                                const uint8_t byte = static_cast<uint8_t>(packed_src[p]);
                                const uint8_t lo = byte & 0x0F;
                                const uint8_t hi = (byte >> 4) & 0x0F;
                                const int8_t qlo = (lo >= 8) ? static_cast<int8_t>(static_cast<int>(lo) - 16) : static_cast<int8_t>(lo);
                                const int8_t qhi = (hi >= 8) ? static_cast<int8_t>(static_cast<int>(hi) - 16) : static_cast<int8_t>(hi);
                                local_buf[p * 2]     = static_cast<float>(qlo) * scale + zeropoint;
                                local_buf[p * 2 + 1] = static_cast<float>(qhi) * scale + zeropoint;
                            }
                        }
                    } else {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            float qv = static_cast<float>(src[i * stride + offset]);
                            local_buf[i] = qv * scale + zeropoint;
                        }
                    }
                    sycl::group_barrier(item.get_group());

                    // Inverse Hadamard
                    if (rh) {
                        if (rounds_L >= 1) {
                            // Radix-4 Hadamard (self-inverse, same as forward path).
                            constexpr int64_t kR = 4;
                            const int64_t num_groups = chunk_size / kR;
                            float* scratch_buf = local_scratch.get_multi_ptr<sycl::access::decorated::no>().get_raw();

                            for (int64_t round = 0; round < rounds_L; ++round) {
                                for (int64_t g = lid; g < num_groups; g += wg_size) {
                                    const int64_t base = g * kR;
                                    const float r0 = local_buf[base + 0];
                                    const float r1 = local_buf[base + 1];
                                    const float r2 = local_buf[base + 2];
                                    const float r3 = local_buf[base + 3];
                                    const float a0 = r0 + r1, a1 = r0 - r1;
                                    const float a2 = r2 + r3, a3 = r2 - r3;
                                    local_buf[base + 0] = a0 + a2;
                                    local_buf[base + 1] = a1 + a3;
                                    local_buf[base + 2] = a0 - a2;
                                    local_buf[base + 3] = a1 - a3;
                                }
                                sycl::group_barrier(item.get_group());

                                if (round + 1 < rounds_L) {
                                    const int shift1 = static_cast<int>((round + 1) * 2);
                                    for (int64_t a = lid; a < chunk_size; a += wg_size) {
                                        const int64_t d0 = a & 0x3LL;
                                        const int64_t d1 = (a >> shift1) & 0x3LL;
                                        const int64_t new_a = (a & ~0x3LL & ~(0x3LL << shift1)) | d1 | (d0 << shift1);
                                        scratch_buf[new_a] = local_buf[a];
                                    }
                                    sycl::group_barrier(item.get_group());
                                    float* tmp = local_buf;
                                    local_buf = scratch_buf;
                                    scratch_buf = tmp;
                                }
                            }

                            // Write into the buffer that is not local_buf.
                            {
                                const int top_shift = static_cast<int>((rounds_L - 1) * 2);
                                for (int64_t a = lid; a < chunk_size; a += wg_size) {
                                    const int64_t bottom = a & 0x3LL;
                                    const int64_t rest = a >> 2;
                                    const int64_t n = rest | (bottom << top_shift);
                                    scratch_buf[n] = local_buf[a];
                                }
                                sycl::group_barrier(item.get_group());
                                local_buf = scratch_buf;
                            }
                        } else {
                            for (int64_t h = 1; h < chunk_size; h <<= 1) {
                                const int64_t bfly_stride = h << 1;
                                for (int64_t base = lid; base < chunk_size / 2; base += wg_size) {
                                    int64_t block = base / h;
                                    int64_t off_in_block = base % h;
                                    int64_t idx = block * bfly_stride + off_in_block;
                                    float a = local_buf[idx];
                                    float b = local_buf[idx + h];
                                    local_buf[idx]     = a + b;
                                    local_buf[idx + h] = a - b;
                                }
                                sycl::group_barrier(item.get_group());
                            }
                        }
                        for (int64_t i = lid; i < chunk_size; i += wg_size)
                            local_buf[i] *= inv_sqrt_n;
                        sycl::group_barrier(item.get_group());
                    }

                    // Iterate over physical index m (sequential HBM write); read via inv_perm[m].
                    if (rh && (inv_perm || signs_reordered)) {
                        for (int64_t m = lid; m < chunk_size; m += wg_size) {
                            int64_t k = inv_perm ? static_cast<int64_t>(inv_perm[m]) : m;
                            float v = local_buf[k];
                            if (signs_reordered) v *= signs_reordered[m];
                            dst[m * dst_stride + dst_offset] = static_cast<KVType>(v);
                        }
                    } else if constexpr (!std::is_same_v<KVType, sycl::ext::oneapi::bfloat16>) {
                        if (dst_stride == 1 && (!fused_dst || chunk_size % 4 == 0)) {
                            const int64_t num_vec_groups = chunk_size / 4;
                            auto local_mptr = sycl::address_space_cast<
                                sycl::access::address_space::local_space,
                                sycl::access::decorated::no>(local_buf);
                            auto dst_mptr = sycl::address_space_cast<
                                sycl::access::address_space::global_space,
                                sycl::access::decorated::no>(dst + dst_offset);
                            for (int64_t g = lid; g < num_vec_groups; g += wg_size) {
                                sycl::vec<float, 4> fv;
                                fv.load(static_cast<size_t>(g), local_mptr);
                                fv.template convert<KVType>().store(static_cast<size_t>(g), dst_mptr);
                            }
                        } else {
                            for (int64_t i = lid; i < chunk_size; i += wg_size) {
                                dst[i * dst_stride + dst_offset] = static_cast<KVType>(local_buf[i]);
                            }
                        }
                    } else {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            dst[i * dst_stride + dst_offset] = static_cast<KVType>(local_buf[i]);
                        }
                    }
                });
        });
    } else {
        // Large-chunk path (global scratch); also forced when profiling.
        sycl::queue& kq = profiling ? get_profiling_queue(q) : q;

        float* scratch = sycl::malloc_device<float>(static_cast<size_t>(element_count), kq);
        DeviceScratch<float> scratch_guard(scratch, kq);

        // Step 1: Dequantize into scratch buffer
        auto dequant_event = kq.submit([&](sycl::handler& cgh) {
            cgh.depends_on(deps);
            cgh.parallel_for<DequantizeKernelLarge<KVType, QType, Pack4Bit>>(
                sycl::nd_range<1>(static_cast<size_t>(num_chunks) * WG_SIZE, WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int chunk_id = static_cast<int>(item.get_group(0));
                    const int lid = static_cast<int>(item.get_local_id(0));
                    const int wg_size = static_cast<int>(item.get_local_range(0));
                    const int64_t offset = is_per_channel
                        ? (chunk_id / stride) * single_layer_numel + (chunk_id % stride)
                        : chunk_id * chunk_size;
                    const float scale = scales_in[chunk_id];
                    const float zeropoint = zps_in[chunk_id];
                    float* chunk_data = scratch + chunk_id * chunk_size;

                    if constexpr (Pack4Bit) {
                        // Unpack both nibbles per thread.
                        const int64_t packed_chunk_size = chunk_size / 2;
                        const QType* packed_src = src + static_cast<int64_t>(chunk_id) * packed_chunk_size;
                        if (packed_chunk_size % 4 == 0) {
                            const int64_t num_groups = packed_chunk_size / 4;
                            auto packed_mptr = sycl::address_space_cast<
                                sycl::access::address_space::global_space,
                                sycl::access::decorated::no>(packed_src);
                            auto data_mptr = sycl::address_space_cast<
                                sycl::access::address_space::global_space,
                                sycl::access::decorated::no>(chunk_data);
                            for (int64_t g = lid; g < num_groups; g += wg_size) {
                                sycl::vec<int8_t, 4> pv;
                                pv.load(static_cast<size_t>(g), packed_mptr);
                                sycl::vec<float, 8> out;
                                for (int k = 0; k < 4; ++k) {
                                    const uint8_t byte = static_cast<uint8_t>(pv[k]);
                                    const uint8_t lo = byte & 0x0F;
                                    const uint8_t hi = (byte >> 4) & 0x0F;
                                    const int8_t qlo = (lo >= 8) ? static_cast<int8_t>(static_cast<int>(lo) - 16) : static_cast<int8_t>(lo);
                                    const int8_t qhi = (hi >= 8) ? static_cast<int8_t>(static_cast<int>(hi) - 16) : static_cast<int8_t>(hi);
                                    out[k * 2]     = static_cast<float>(qlo) * scale + zeropoint;
                                    out[k * 2 + 1] = static_cast<float>(qhi) * scale + zeropoint;
                                }
                                out.store(static_cast<size_t>(g), data_mptr);
                            }
                        } else {
                            for (int64_t p = lid; p < packed_chunk_size; p += wg_size) {
                                const uint8_t byte = static_cast<uint8_t>(packed_src[p]);
                                const uint8_t lo = byte & 0x0F;
                                const uint8_t hi = (byte >> 4) & 0x0F;
                                const int8_t qlo = (lo >= 8) ? static_cast<int8_t>(static_cast<int>(lo) - 16) : static_cast<int8_t>(lo);
                                const int8_t qhi = (hi >= 8) ? static_cast<int8_t>(static_cast<int>(hi) - 16) : static_cast<int8_t>(hi);
                                chunk_data[p * 2]     = static_cast<float>(qlo) * scale + zeropoint;
                                chunk_data[p * 2 + 1] = static_cast<float>(qhi) * scale + zeropoint;
                            }
                        }
                    } else {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            float qv = static_cast<float>(src[i * stride + offset]);
                            chunk_data[i] = qv * scale + zeropoint;
                        }
                    }
                });
        });
        if (profiling) {
            dequant_event.wait();
            record_stage(QuantStage::DequantLoad, event_duration_ns(dequant_event));
        }

        // Step 2: Inverse Hadamard per chunk (if rh)
        sycl::event had_event = dequant_event;
        if (rh) {
            uint64_t inverse_ns = 0;
            // Batched like quantize: block-local stages first, then cross-block stages.
            sycl::event stage_event = dequant_event;
            std::vector<sycl::event> stage_deps = {dequant_event};

            const int64_t block_size = std::min(max_slm_chunk, chunk_size);
            int64_t h_start = 1;
            if (block_size > 1) {
                const int64_t num_blocks = element_count / block_size;
                stage_event = hadamard_block_local_batched(kq, scratch, block_size, num_blocks, stage_deps);
                if (profiling) {
                    stage_event.wait();
                    inverse_ns += event_duration_ns(stage_event);
                }
                stage_deps = {stage_event};
                h_start = block_size;
            }

            for (int64_t h = h_start; h < chunk_size; h <<= 1) {
                stage_event = (h >= 4)
                    ? hadamard_stage_global_batched_vec4(kq, scratch, chunk_size, num_chunks, h, stage_deps)
                    : hadamard_stage_global_batched(kq, scratch, chunk_size, num_chunks, h, stage_deps);
                if (profiling) {
                    stage_event.wait();
                    inverse_ns += event_duration_ns(stage_event);
                }
                stage_deps = {stage_event};
            }
            had_event = scale_buffer(kq, scratch, element_count, inv_sqrt_n, {stage_event});
            if (profiling) {
                had_event.wait();
                inverse_ns += event_duration_ns(had_event);
                record_stage(QuantStage::HadamardInverse, inverse_ns);
            }
        }

        // Step 3: Inverse precond + write to dst (vec4 fast path when contiguous).
        const bool write_fast_contig = (stride == 1) && !(rh && (perm || signs)) &&
                                        (element_count % 4 == 0);
        sycl::event write_event;
        if constexpr (!std::is_same_v<KVType, sycl::ext::oneapi::bfloat16>) {
            if (write_fast_contig) {
                write_event = precond_writeback_contiguous_vec4<KVType>(kq, scratch, dst, element_count, {had_event});
            } else {
                const int64_t global_size = ((element_count + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
                write_event = kq.submit([&](sycl::handler& cgh) {
                    cgh.depends_on({had_event});
                    cgh.parallel_for(
                        sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
                        [=](sycl::nd_item<1> item) {
                            const int64_t gid = static_cast<int64_t>(item.get_global_id(0));
                            if (gid >= element_count) return;
                            int64_t chunk_id = gid / chunk_size;
                            int64_t i = gid % chunk_size;
                            int64_t offset = is_per_channel
                                ? (chunk_id / stride) * single_layer_numel + (chunk_id % stride)
                                : chunk_id * chunk_size;

                            float v = scratch[gid];
                            if (rh && (perm || signs)) {
                                if (signs) v *= signs[i];
                                int64_t dst_idx = perm ? static_cast<int64_t>(perm[i]) : i;
                                dst[dst_idx * stride + offset] = static_cast<KVType>(v);
                            } else {
                                dst[i * stride + offset] = static_cast<KVType>(v);
                            }
                        });
                });
            }
        } else {
            const int64_t global_size = ((element_count + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
            write_event = kq.submit([&](sycl::handler& cgh) {
                cgh.depends_on({had_event});
                cgh.parallel_for(
                    sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
                    [=](sycl::nd_item<1> item) {
                        const int64_t gid = static_cast<int64_t>(item.get_global_id(0));
                        if (gid >= element_count) return;
                        int64_t chunk_id = gid / chunk_size;
                        int64_t i = gid % chunk_size;
                        int64_t offset = is_per_channel
                            ? (chunk_id / stride) * single_layer_numel + (chunk_id % stride)
                            : chunk_id * chunk_size;

                        float v = scratch[gid];
                        if (rh && (perm || signs)) {
                            if (signs) v *= signs[i];
                            int64_t dst_idx = perm ? static_cast<int64_t>(perm[i]) : i;
                            dst[dst_idx * stride + offset] = static_cast<KVType>(v);
                        } else {
                            dst[i * stride + offset] = static_cast<KVType>(v);
                        }
                    });
            });
        }
        if (profiling) {
            write_event.wait();
            record_stage(QuantStage::PrecondWriteback, event_duration_ns(write_event));
        }

        // Success: hand scratch off to the async free (chained on write_event).
        scratch_guard.release();
        kq.submit([&](sycl::handler& cgh) {
            cgh.depends_on(write_event);
            cgh.host_task([=, &kq]() { sycl::free(scratch, kq); });
        });

        return write_event;
    }
}

// ---------------------------------------------------------------------------
// 4-bit packing kernel
// ---------------------------------------------------------------------------
class PackInt4Kernel;

sycl::event pack_int4_sycl(
    sycl::queue& q,
    const int8_t* logical,
    int8_t* packed,
    int64_t logical_count,
    const std::vector<sycl::event>& deps)
{
    const int64_t packed_count = (logical_count + 1) / 2;
    const int64_t global_size = ((packed_count + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;

    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        cgh.parallel_for<PackInt4Kernel>(
            sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t idx = static_cast<int64_t>(item.get_global_id(0));
                if (idx >= packed_count) return;

                int64_t lo_idx = idx * 2;
                int64_t hi_idx = lo_idx + 1;
                uint8_t lo_nibble = static_cast<uint8_t>(logical[lo_idx]) & 0x0F;
                uint8_t hi_nibble = (hi_idx < logical_count)
                    ? (static_cast<uint8_t>(logical[hi_idx]) & 0x0F)
                    : 0;
                packed[idx] = static_cast<int8_t>(lo_nibble | (hi_nibble << 4));
            });
    });
}

// ---------------------------------------------------------------------------
// 4-bit unpacking kernel
// ---------------------------------------------------------------------------
class UnpackInt4Kernel;

sycl::event unpack_int4_sycl(
    sycl::queue& q,
    const int8_t* packed,
    int8_t* logical,
    int64_t logical_count,
    const std::vector<sycl::event>& deps)
{
    const int64_t global_size = ((logical_count + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;

    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        cgh.parallel_for<UnpackInt4Kernel>(
            sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t idx = static_cast<int64_t>(item.get_global_id(0));
                if (idx >= logical_count) return;

                int64_t byte_idx = idx / 2;
                uint8_t byte = static_cast<uint8_t>(packed[byte_idx]);
                uint8_t nibble = ((idx & 1) == 0)
                    ? (byte & 0x0F)
                    : ((byte >> 4) & 0x0F);
                // Sign-extend 4-bit: if bit 3 set, value is negative
                int8_t value = (nibble >= 8)
                    ? static_cast<int8_t>(static_cast<int>(nibble) - 16)
                    : static_cast<int8_t>(nibble);
                logical[idx] = value;
            });
    });
}

// ---------------------------------------------------------------------------
// Fused [layers, tokens, head_num*head_dim] -> split
// [layers*head_num, tokens, head_dim] gather, used only when a fused-source
// quantize can't take the SLM path (which reads the fused layout in place).
// ---------------------------------------------------------------------------
template<typename KVType>
class SplitFusedHeadsKernel;

template<typename KVType>
static sycl::event split_fused_heads_sycl(
    sycl::queue& q,
    const KVType* src,
    KVType* dst,
    int64_t element_count,
    int64_t tokens,
    int64_t head_num,
    int64_t head_dim,
    const std::vector<sycl::event>& deps)
{
    const int64_t unit_elems = tokens * head_dim;
    const int64_t hidden = head_num * head_dim;
    const int64_t global_size = ((element_count + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        cgh.parallel_for<SplitFusedHeadsKernel<KVType>>(
            sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t i = static_cast<int64_t>(item.get_global_id(0));
                if (i >= element_count) return;
                const int64_t unit = i / unit_elems;
                const int64_t r = i % unit_elems;
                const int64_t t = r / head_dim;
                const int64_t d = r % head_dim;
                dst[i] = src[((unit / head_num) * tokens + t) * hidden
                             + (unit % head_num) * head_dim + d];
            });
    });
}

// Inverse of split_fused_heads_sycl, for fused-dst dequantize off the SLM path.
template<typename KVType>
class MergeFusedHeadsKernel;

template<typename KVType>
static sycl::event merge_fused_heads_sycl(
    sycl::queue& q,
    const KVType* src,
    KVType* dst,
    int64_t element_count,
    int64_t tokens,
    int64_t head_num,
    int64_t head_dim,
    const std::vector<sycl::event>& deps)
{
    const int64_t unit_elems = tokens * head_dim;
    const int64_t hidden = head_num * head_dim;
    const int64_t global_size = ((element_count + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        cgh.parallel_for<MergeFusedHeadsKernel<KVType>>(
            sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t i = static_cast<int64_t>(item.get_global_id(0));
                if (i >= element_count) return;
                const int64_t unit = i / unit_elems;
                const int64_t r = i % unit_elems;
                const int64_t t = r / head_dim;
                const int64_t d = r % head_dim;
                dst[((unit / head_num) * tokens + t) * hidden
                    + (unit % head_num) * head_dim + d] = src[i];
            });
    });
}

// ---------------------------------------------------------------------------
// Top-level quantize dispatch (handles qbit=4 packing)
// ---------------------------------------------------------------------------
template<typename KVType, typename QType>
sycl::event quantize_kvcache_sycl(
    sycl::queue& q,
    const KVType* src,
    QType* dst,
    float* scales_out,
    float* zps_out,
    int64_t element_count,
    const sycl_quantization_args& args,
    const std::vector<sycl::event>& deps)
{
    if (args.fused_src_head_num > 0) {
        const int64_t num_layers = args.num_layers > 0 ? args.num_layers : 1;
        const int64_t tokens = element_count / (num_layers * args.head_dim);
        const int64_t chunk_size = (args.scaling_method == "per_channel") ? tokens : args.head_dim;
        if (quant_profile_is_enabled() || chunk_size > get_max_slm_chunk(q)) {
            KVType* split = sycl::malloc_device<KVType>(static_cast<size_t>(element_count), q);
            DeviceScratch<KVType> split_guard(split, q);
            auto split_event = split_fused_heads_sycl<KVType>(
                q, src, split, element_count, tokens, args.fused_src_head_num,
                args.head_dim, deps);
            sycl_quantization_args split_args = args;
            split_args.fused_src_head_num = 0;
            auto quant_event = quantize_kvcache_sycl<KVType, QType>(
                q, split, dst, scales_out, zps_out, element_count, split_args, {split_event});
            split_guard.release();
            q.submit([&](sycl::handler& cgh) {
                cgh.depends_on(quant_event);
                cgh.host_task([=, &q]() {
                    sycl::free(split, q);
                });
            });
            return quant_event;
        }
    }

    if (args.qbit == 4) {
        int64_t chunks_per_layer = 1;
        if (args.scaling_method == "per_token") {
            chunks_per_layer = static_cast<int64_t>(args.blocks_num) * args.block_size;
        } else if (args.scaling_method == "per_channel") {
            chunks_per_layer = args.head_dim;
        }
        const int64_t num_layers = args.num_layers > 0 ? args.num_layers : 1;
        const int64_t num_chunks = num_layers * chunks_per_layer;
        const int64_t chunk_size = element_count / num_chunks;

        if (chunk_size % 2 == 0) {
            // Fused path: the quantize kernel writes packed nibbles directly.
            return quantize_block_sycl_impl<KVType, int8_t, /*Pack4Bit=*/true>(
                q, src, reinterpret_cast<int8_t*>(dst), scales_out, zps_out, element_count, args, deps);
        }

        // Odd chunk_size fallback: quantize to int8, then pack.
        const bool profiling = quant_profile_is_enabled();
        sycl::queue& kq = profiling ? get_profiling_queue(q) : q;

        int8_t* logical_buf = sycl::malloc_device<int8_t>(static_cast<size_t>(element_count), kq);
        DeviceScratch<int8_t> logical_guard(logical_buf, kq);

        auto quant_event = quantize_block_sycl_impl<KVType, int8_t>(
            kq, src, logical_buf, scales_out, zps_out,
            element_count, args, deps);

        auto pack_event = pack_int4_sycl(
            kq, logical_buf, reinterpret_cast<int8_t*>(dst),
            element_count, {quant_event});
        if (profiling) {
            pack_event.wait();
            record_stage(QuantStage::Pack4bit, event_duration_ns(pack_event));
        }

        // Success: hand logical_buf off to the async free (chained on pack).
        logical_guard.release();
        kq.submit([&](sycl::handler& cgh) {
            cgh.depends_on(pack_event);
            cgh.host_task([=, &kq]() {
                sycl::free(logical_buf, kq);
            });
        });

        return pack_event;
    }

    return quantize_block_sycl_impl<KVType, QType>(
        q, src, dst, scales_out, zps_out, element_count, args, deps);
}

// ---------------------------------------------------------------------------
// Top-level dequantize dispatch (handles qbit=4 unpacking)
// ---------------------------------------------------------------------------
template<typename KVType, typename QType>
sycl::event dequantize_kvcache_sycl(
    sycl::queue& q,
    const QType* src,
    KVType* dst,
    const float* scales_in,
    const float* zps_in,
    int64_t element_count,
    const sycl_quantization_args& args,
    const std::vector<sycl::event>& deps)
{
    if (args.fused_dst_head_num > 0) {
        const int64_t num_layers = args.num_layers > 0 ? args.num_layers : 1;
        const int64_t tokens = element_count / (num_layers * args.head_dim);
        const bool per_channel = args.scaling_method == "per_channel";
        const int64_t chunk_size = per_channel ? tokens : args.head_dim;
        // per_channel: dequantize in split layout, then merge contiguously.
        if (per_channel || quant_profile_is_enabled() || chunk_size > get_max_slm_chunk(q)) {
            KVType* split = sycl::malloc_device<KVType>(static_cast<size_t>(element_count), q);
            DeviceScratch<KVType> split_guard(split, q);
            sycl_quantization_args split_args = args;
            split_args.fused_dst_head_num = 0;
            auto dequant_event = dequantize_kvcache_sycl<KVType, QType>(
                q, src, split, scales_in, zps_in, element_count, split_args, deps);
            auto merge_event = merge_fused_heads_sycl<KVType>(
                q, split, dst, element_count, tokens, args.fused_dst_head_num,
                args.head_dim, {dequant_event});
            split_guard.release();
            q.submit([&](sycl::handler& cgh) {
                cgh.depends_on(merge_event);
                cgh.host_task([=, &q]() {
                    sycl::free(split, q);
                });
            });
            return merge_event;
        }
    }

    if (args.qbit == 4) {
        int64_t chunks_per_layer = 1;
        if (args.scaling_method == "per_token") {
            chunks_per_layer = static_cast<int64_t>(args.blocks_num) * args.block_size;
        } else if (args.scaling_method == "per_channel") {
            chunks_per_layer = args.head_dim;
        }
        const int64_t num_layers = args.num_layers > 0 ? args.num_layers : 1;
        const int64_t num_chunks = num_layers * chunks_per_layer;
        const int64_t chunk_size = element_count / num_chunks;

        if (chunk_size % 2 == 0) {
            // Fused path: reads packed nibbles directly.
            return dequantize_block_sycl_impl<KVType, int8_t, /*Pack4Bit=*/true>(
                q, reinterpret_cast<const int8_t*>(src), dst, scales_in, zps_in, element_count, args, deps);
        }

        // Fallback for odd chunk_size: unpack, then dequantize.
        const bool profiling = quant_profile_is_enabled();
        sycl::queue& kq = profiling ? get_profiling_queue(q) : q;

        int8_t* logical_buf = sycl::malloc_device<int8_t>(static_cast<size_t>(element_count), kq);
        DeviceScratch<int8_t> logical_guard(logical_buf, kq);

        auto unpack_event = unpack_int4_sycl(
            kq, reinterpret_cast<const int8_t*>(src), logical_buf,
            element_count, deps);
        if (profiling) {
            unpack_event.wait();
            record_stage(QuantStage::Unpack4bit, event_duration_ns(unpack_event));
        }

        auto dequant_event = dequantize_block_sycl_impl<KVType, int8_t>(
            kq, logical_buf, dst, scales_in, zps_in,
            element_count, args, {unpack_event});

        // Success: hand logical_buf off to the async free (chained on dequant).
        logical_guard.release();
        kq.submit([&](sycl::handler& cgh) {
            cgh.depends_on(dequant_event);
            cgh.host_task([=, &kq]() {
                sycl::free(logical_buf, kq);
            });
        });

        return dequant_event;
    }

    return dequantize_block_sycl_impl<KVType, QType>(
        q, src, dst, scales_in, zps_in, element_count, args, deps);
}

// ---------------------------------------------------------------------------
// Explicit template instantiations
// ---------------------------------------------------------------------------
// fp16 (sycl::half)
template sycl::event quantize_kvcache_sycl<sycl::half, int8_t>(
    sycl::queue&, const sycl::half*, int8_t*, float*, float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);
template sycl::event dequantize_kvcache_sycl<sycl::half, int8_t>(
    sycl::queue&, const int8_t*, sycl::half*, const float*, const float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);

// bf16 (sycl::ext::oneapi::bfloat16)
template sycl::event quantize_kvcache_sycl<sycl::ext::oneapi::bfloat16, int8_t>(
    sycl::queue&, const sycl::ext::oneapi::bfloat16*, int8_t*, float*, float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);
template sycl::event dequantize_kvcache_sycl<sycl::ext::oneapi::bfloat16, int8_t>(
    sycl::queue&, const int8_t*, sycl::ext::oneapi::bfloat16*, const float*, const float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);

// fp32
template sycl::event quantize_kvcache_sycl<float, int8_t>(
    sycl::queue&, const float*, int8_t*, float*, float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);
template sycl::event dequantize_kvcache_sycl<float, int8_t>(
    sycl::queue&, const int8_t*, float*, const float*, const float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);

// int16 variants (for qbit > 8)
template sycl::event quantize_kvcache_sycl<sycl::half, int16_t>(
    sycl::queue&, const sycl::half*, int16_t*, float*, float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);
template sycl::event dequantize_kvcache_sycl<sycl::half, int16_t>(
    sycl::queue&, const int16_t*, sycl::half*, const float*, const float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);

template sycl::event quantize_kvcache_sycl<sycl::ext::oneapi::bfloat16, int16_t>(
    sycl::queue&, const sycl::ext::oneapi::bfloat16*, int16_t*, float*, float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);
template sycl::event dequantize_kvcache_sycl<sycl::ext::oneapi::bfloat16, int16_t>(
    sycl::queue&, const int16_t*, sycl::ext::oneapi::bfloat16*, const float*, const float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);

// fp32 + int16
template sycl::event quantize_kvcache_sycl<float, int16_t>(
    sycl::queue&, const float*, int16_t*, float*, float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);
template sycl::event dequantize_kvcache_sycl<float, int16_t>(
    sycl::queue&, const int16_t*, float*, const float*, const float*,
    int64_t, const sycl_quantization_args&, const std::vector<sycl::event>&);
