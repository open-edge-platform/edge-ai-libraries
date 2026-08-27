// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

#include "quant_sycl.hpp"
#include <cmath>
#include <limits>

// Work-group size for quantization kernels.
static constexpr int WG_SIZE = 256;

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
// Quantize kernel: one work-group per chunk
// Two paths based on chunk_size:
//   - Small (≤ MAX_SLM_CHUNK): local memory for data + single-kernel Hadamard
//   - Large (> MAX_SLM_CHUNK): global scratch buffer + multi-kernel Hadamard
// Both paths support all configurations including rh + per_tensor.
// ---------------------------------------------------------------------------
static constexpr int64_t MAX_SLM_CHUNK = 8192;  // 32KB of float local memory

// ---------------------------------------------------------------------------
// Global-memory Hadamard: one butterfly stage per kernel launch.
// For chunks > MAX_SLM_CHUNK, we run log2(chunk_size) kernel launches.
// ---------------------------------------------------------------------------
class HadamardStageKernel;

static sycl::event hadamard_stage_global(
    sycl::queue& q,
    float* buf,
    int64_t n,
    int64_t h,  // butterfly half-stride for this stage
    const std::vector<sycl::event>& deps)
{
    const int64_t num_pairs = n / 2;
    const int64_t global_size = ((num_pairs + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;

    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        cgh.parallel_for<HadamardStageKernel>(
            sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t idx = static_cast<int64_t>(item.get_global_id(0));
                if (idx >= num_pairs) return;
                const int64_t stride = h << 1;
                int64_t block = idx / h;
                int64_t off_in_block = idx % h;
                int64_t i = block * stride + off_in_block;
                float a = buf[i];
                float b = buf[i + h];
                buf[i]     = a + b;
                buf[i + h] = a - b;
            });
    });
}

// Scale (multiply) a device buffer by a constant
class ScaleKernel;

static sycl::event scale_buffer(
    sycl::queue& q,
    float* buf,
    int64_t n,
    float factor,
    const std::vector<sycl::event>& deps)
{
    const int64_t global_size = ((n + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
    return q.submit([&](sycl::handler& cgh) {
        cgh.depends_on(deps);
        cgh.parallel_for<ScaleKernel>(
            sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
            [=](sycl::nd_item<1> item) {
                const int64_t idx = static_cast<int64_t>(item.get_global_id(0));
                if (idx >= n) return;
                buf[idx] *= factor;
            });
    });
}

template<typename KVType, typename QType>
class QuantizeKernel;

template<typename KVType, typename QType>
class QuantizeKernelLarge;

template<typename KVType, typename QType>
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
    int64_t num_chunks = 1;
    if (args.scaling_method == "per_token") {
        num_chunks = static_cast<int64_t>(args.blocks_num) * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        num_chunks = args.head_dim;
    }

    const int64_t chunk_size = element_count / num_chunks;
    const bool is_per_channel = (args.scaling_method == "per_channel");
    const int64_t stride = is_per_channel ? args.head_dim : 1;

    const int qbit = args.qbit;
    const bool asym = args.asym;
    const bool rh = args.rh;
    const int32_t* perm = args.perm;
    const float* signs = args.signs;

    const int64_t qmax_int = (1 << (qbit - 1)) - 1;
    const int64_t qmin_int = -(1 << (qbit - 1));
    const float qmax_float = static_cast<float>(qmax_int);
    const float qmin_float = static_cast<float>(qmin_int);
    const float inv_sqrt_n = 1.0f / std::sqrt(static_cast<float>(chunk_size));

    const bool use_local_mem = (chunk_size <= MAX_SLM_CHUNK);

    if (use_local_mem) {
        // Small-chunk path: local memory for data + Hadamard
        return q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(deps);
            auto local_data = sycl::local_accessor<float, 1>(sycl::range<1>(static_cast<size_t>(chunk_size)), cgh);
            auto reduce_mem = sycl::local_accessor<float, 1>(sycl::range<1>(2 * WG_SIZE), cgh);

            cgh.parallel_for<QuantizeKernel<KVType, QType>>(
                sycl::nd_range<1>(static_cast<size_t>(num_chunks) * WG_SIZE, WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int chunk_id = static_cast<int>(item.get_group(0));
                    const int lid = static_cast<int>(item.get_local_id(0));
                    const int wg_size = static_cast<int>(item.get_local_range(0));
                    float* local_buf = local_data.get_multi_ptr<sycl::access::decorated::no>().get_raw();
                    float* red_buf = reduce_mem.get_multi_ptr<sycl::access::decorated::no>().get_raw();

                    const int64_t offset = is_per_channel ? chunk_id : chunk_id * chunk_size;

                    // Load into local memory with optional precond
                    if (rh && (perm || signs)) {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            int64_t src_idx = perm ? static_cast<int64_t>(perm[i]) : i;
                            float v = static_cast<float>(src[src_idx * stride + offset]);
                            if (signs) v *= signs[i];
                            local_buf[i] = v;
                        }
                    } else {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            local_buf[i] = static_cast<float>(src[i * stride + offset]);
                        }
                    }
                    sycl::group_barrier(item.get_group());

                    // Hadamard transform
                    if (rh) {
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
                        for (int64_t i = lid; i < chunk_size; i += wg_size)
                            local_buf[i] *= inv_sqrt_n;
                        sycl::group_barrier(item.get_group());
                    }

                    // Min/max reduction
                    float lmin = std::numeric_limits<float>::max();
                    float lmax = std::numeric_limits<float>::lowest();
                    for (int64_t i = lid; i < chunk_size; i += wg_size) {
                        float v = local_buf[i];
                        lmin = sycl::fmin(lmin, v);
                        lmax = sycl::fmax(lmax, v);
                    }
                    red_buf[lid] = lmin;
                    red_buf[lid + wg_size] = lmax;
                    sycl::group_barrier(item.get_group());
                    for (int s = wg_size / 2; s > 0; s >>= 1) {
                        if (lid < s) {
                            red_buf[lid] = sycl::fmin(red_buf[lid], red_buf[lid + s]);
                            red_buf[lid + wg_size] = sycl::fmax(red_buf[lid + wg_size], red_buf[lid + wg_size + s]);
                        }
                        sycl::group_barrier(item.get_group());
                    }

                    // Compute scale
                    float scale = 0.0f, zeropoint = 0.0f;
                    if (lid == 0) {
                        float min_val = red_buf[0], max_val = red_buf[wg_size];
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
                    for (int64_t i = lid; i < chunk_size; i += wg_size) {
                        float val = local_buf[i];
                        float q_val = sycl::clamp(sycl::round((val - zeropoint) * inv_scale), qmin_float, qmax_float);
                        dst[i * stride + offset] = static_cast<QType>(static_cast<int>(q_val));
                    }
                });
        });
    } else {
        // Large-chunk path: use global memory scratch for data + Hadamard.
        // Allocate a float scratch buffer for the entire element_count.
        float* scratch = sycl::malloc_device<float>(static_cast<size_t>(element_count), q);
        DeviceScratch<float> scratch_guard(scratch, q);

        // Step 1: Load data into scratch (with optional precond gather)
        auto load_event = q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(deps);
            const int64_t global_size = ((element_count + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
            cgh.parallel_for(
                sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int64_t gid = static_cast<int64_t>(item.get_global_id(0));
                    if (gid >= element_count) return;
                    // Map flat gid to (chunk_id, i_within_chunk)
                    int64_t chunk_id = gid / chunk_size;
                    int64_t i = gid % chunk_size;
                    int64_t offset = is_per_channel ? chunk_id : chunk_id * chunk_size;

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

        // Step 2: Hadamard transform per chunk in global memory (if rh)
        sycl::event had_event = load_event;
        if (rh) {
            // Run Hadamard independently for each chunk
            for (int64_t c = 0; c < num_chunks; ++c) {
                float* chunk_buf = scratch + c * chunk_size;
                std::vector<sycl::event> chunk_deps = {had_event};
                for (int64_t h = 1; h < chunk_size; h <<= 1) {
                    had_event = hadamard_stage_global(q, chunk_buf, chunk_size, h, chunk_deps);
                    chunk_deps = {had_event};
                }
            }
            // Normalize all chunks
            had_event = scale_buffer(q, scratch, element_count, inv_sqrt_n, {had_event});
        }

        // Step 3: Min/max reduction + quantize from scratch buffer
        auto quant_event = q.submit([&](sycl::handler& cgh) {
            cgh.depends_on({had_event});
            auto reduce_mem = sycl::local_accessor<float, 1>(sycl::range<1>(2 * WG_SIZE), cgh);

            cgh.parallel_for<QuantizeKernelLarge<KVType, QType>>(
                sycl::nd_range<1>(static_cast<size_t>(num_chunks) * WG_SIZE, WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int chunk_id = static_cast<int>(item.get_group(0));
                    const int lid = static_cast<int>(item.get_local_id(0));
                    const int wg_size = static_cast<int>(item.get_local_range(0));
                    float* red_buf = reduce_mem.get_multi_ptr<sycl::access::decorated::no>().get_raw();

                    const int64_t offset = is_per_channel ? chunk_id : chunk_id * chunk_size;
                    const float* chunk_data = scratch + chunk_id * chunk_size;

                    // Min/max reduction from scratch
                    float lmin = std::numeric_limits<float>::max();
                    float lmax = std::numeric_limits<float>::lowest();
                    for (int64_t i = lid; i < chunk_size; i += wg_size) {
                        float v = chunk_data[i];
                        lmin = sycl::fmin(lmin, v);
                        lmax = sycl::fmax(lmax, v);
                    }
                    red_buf[lid] = lmin;
                    red_buf[lid + wg_size] = lmax;
                    sycl::group_barrier(item.get_group());
                    for (int s = wg_size / 2; s > 0; s >>= 1) {
                        if (lid < s) {
                            red_buf[lid] = sycl::fmin(red_buf[lid], red_buf[lid + s]);
                            red_buf[lid + wg_size] = sycl::fmax(red_buf[lid + wg_size], red_buf[lid + wg_size + s]);
                        }
                        sycl::group_barrier(item.get_group());
                    }

                    // Compute scale
                    float scale = 0.0f, zeropoint = 0.0f;
                    if (lid == 0) {
                        float min_val = red_buf[0], max_val = red_buf[wg_size];
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
                    for (int64_t i = lid; i < chunk_size; i += wg_size) {
                        float val = chunk_data[i];
                        float q_val = sycl::clamp(sycl::round((val - zeropoint) * inv_scale), qmin_float, qmax_float);
                        dst[i * stride + offset] = static_cast<QType>(static_cast<int>(q_val));
                    }
                });
        });

        // Success: hand scratch off to the async free (chained on quant_event).
        scratch_guard.release();
        q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(quant_event);
            cgh.host_task([=, &q]() { sycl::free(scratch, q); });
        });

        return quant_event;
    }
}

// ---------------------------------------------------------------------------
// Dequantize kernel: one work-group per chunk, with Hadamard support
// ---------------------------------------------------------------------------
template<typename KVType, typename QType>
class DequantizeKernel;

template<typename KVType, typename QType>
class DequantizeKernelLarge;

template<typename KVType, typename QType>
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
    int64_t num_chunks = 1;
    if (args.scaling_method == "per_token") {
        num_chunks = static_cast<int64_t>(args.blocks_num) * args.block_size;
    } else if (args.scaling_method == "per_channel") {
        num_chunks = args.head_dim;
    }

    const int64_t chunk_size = element_count / num_chunks;
    const bool is_per_channel = (args.scaling_method == "per_channel");
    const int64_t stride = is_per_channel ? args.head_dim : 1;
    const bool rh = args.rh;
    const int32_t* perm = args.perm;
    const float* signs = args.signs;
    const float inv_sqrt_n = 1.0f / std::sqrt(static_cast<float>(chunk_size));

    const bool use_local_mem = (chunk_size <= MAX_SLM_CHUNK);

    if (use_local_mem) {
        return q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(deps);
            auto local_data = sycl::local_accessor<float, 1>(sycl::range<1>(static_cast<size_t>(chunk_size)), cgh);

            cgh.parallel_for<DequantizeKernel<KVType, QType>>(
                sycl::nd_range<1>(static_cast<size_t>(num_chunks) * WG_SIZE, WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int chunk_id = static_cast<int>(item.get_group(0));
                    const int lid = static_cast<int>(item.get_local_id(0));
                    const int wg_size = static_cast<int>(item.get_local_range(0));
                    float* local_buf = local_data.get_multi_ptr<sycl::access::decorated::no>().get_raw();
                    const int64_t offset = is_per_channel ? chunk_id : chunk_id * chunk_size;
                    const float scale = scales_in[chunk_id];
                    const float zeropoint = zps_in[chunk_id];

                    // Dequantize into local memory
                    for (int64_t i = lid; i < chunk_size; i += wg_size) {
                        float qv = static_cast<float>(src[i * stride + offset]);
                        local_buf[i] = qv * scale + zeropoint;
                    }
                    sycl::group_barrier(item.get_group());

                    // Inverse Hadamard
                    if (rh) {
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
                        for (int64_t i = lid; i < chunk_size; i += wg_size)
                            local_buf[i] *= inv_sqrt_n;
                        sycl::group_barrier(item.get_group());
                    }

                    // Inverse precond + write
                    if (rh && (perm || signs)) {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            float v = local_buf[i];
                            if (signs) v *= signs[i];
                            int64_t dst_idx = perm ? static_cast<int64_t>(perm[i]) : i;
                            dst[dst_idx * stride + offset] = static_cast<KVType>(v);
                        }
                    } else {
                        for (int64_t i = lid; i < chunk_size; i += wg_size) {
                            dst[i * stride + offset] = static_cast<KVType>(local_buf[i]);
                        }
                    }
                });
        });
    } else {
        // Large-chunk path: use global memory scratch for Hadamard
        float* scratch = sycl::malloc_device<float>(static_cast<size_t>(element_count), q);
        DeviceScratch<float> scratch_guard(scratch, q);

        // Step 1: Dequantize into scratch buffer
        auto dequant_event = q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(deps);
            cgh.parallel_for<DequantizeKernelLarge<KVType, QType>>(
                sycl::nd_range<1>(static_cast<size_t>(num_chunks) * WG_SIZE, WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int chunk_id = static_cast<int>(item.get_group(0));
                    const int lid = static_cast<int>(item.get_local_id(0));
                    const int wg_size = static_cast<int>(item.get_local_range(0));
                    const int64_t offset = is_per_channel ? chunk_id : chunk_id * chunk_size;
                    const float scale = scales_in[chunk_id];
                    const float zeropoint = zps_in[chunk_id];
                    float* chunk_data = scratch + chunk_id * chunk_size;

                    for (int64_t i = lid; i < chunk_size; i += wg_size) {
                        float qv = static_cast<float>(src[i * stride + offset]);
                        chunk_data[i] = qv * scale + zeropoint;
                    }
                });
        });

        // Step 2: Inverse Hadamard per chunk (if rh)
        sycl::event had_event = dequant_event;
        if (rh) {
            for (int64_t c = 0; c < num_chunks; ++c) {
                float* chunk_buf = scratch + c * chunk_size;
                std::vector<sycl::event> chunk_deps = {had_event};
                for (int64_t h = 1; h < chunk_size; h <<= 1) {
                    had_event = hadamard_stage_global(q, chunk_buf, chunk_size, h, chunk_deps);
                    chunk_deps = {had_event};
                }
            }
            had_event = scale_buffer(q, scratch, element_count, inv_sqrt_n, {had_event});
        }

        // Step 3: Inverse precond + write to dst
        const int64_t global_size = ((element_count + WG_SIZE - 1) / WG_SIZE) * WG_SIZE;
        auto write_event = q.submit([&](sycl::handler& cgh) {
            cgh.depends_on({had_event});
            cgh.parallel_for(
                sycl::nd_range<1>(static_cast<size_t>(global_size), WG_SIZE),
                [=](sycl::nd_item<1> item) {
                    const int64_t gid = static_cast<int64_t>(item.get_global_id(0));
                    if (gid >= element_count) return;
                    int64_t chunk_id = gid / chunk_size;
                    int64_t i = gid % chunk_size;
                    int64_t offset = is_per_channel ? chunk_id : chunk_id * chunk_size;

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

        // Success: hand scratch off to the async free (chained on write_event).
        scratch_guard.release();
        q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(write_event);
            cgh.host_task([=, &q]() { sycl::free(scratch, q); });
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
    if (args.qbit == 4) {
        // For 4-bit: quantize to int8 logical values, then pack
        int8_t* logical_buf = sycl::malloc_device<int8_t>(static_cast<size_t>(element_count), q);
        DeviceScratch<int8_t> logical_guard(logical_buf, q);

        auto quant_event = quantize_block_sycl_impl<KVType, int8_t>(
            q, src, logical_buf, scales_out, zps_out,
            element_count, args, deps);

        auto pack_event = pack_int4_sycl(
            q, logical_buf, reinterpret_cast<int8_t*>(dst),
            element_count, {quant_event});

        // Success: hand logical_buf off to the async free (chained on pack).
        logical_guard.release();
        q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(pack_event);
            cgh.host_task([=, &q]() {
                sycl::free(logical_buf, q);
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
    if (args.qbit == 4) {
        // For 4-bit: unpack to int8 logical values, then dequantize
        int8_t* logical_buf = sycl::malloc_device<int8_t>(static_cast<size_t>(element_count), q);
        DeviceScratch<int8_t> logical_guard(logical_buf, q);

        auto unpack_event = unpack_int4_sycl(
            q, reinterpret_cast<const int8_t*>(src), logical_buf,
            element_count, deps);

        auto dequant_event = dequantize_block_sycl_impl<KVType, int8_t>(
            q, logical_buf, dst, scales_in, zps_in,
            element_count, args, {unpack_event});

        // Success: hand logical_buf off to the async free (chained on dequant).
        logical_guard.release();
        q.submit([&](sycl::handler& cgh) {
            cgh.depends_on(dequant_event);
            cgh.host_task([=, &q]() {
                sycl::free(logical_buf, q);
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
