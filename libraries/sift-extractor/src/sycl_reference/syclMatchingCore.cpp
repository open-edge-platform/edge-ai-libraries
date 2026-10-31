#include "syclSift.h"
#include "syclutils.h"
#include "syclSiftH.h"
#include <sycl/sycl.hpp>
#include <cstdio>

namespace {

void MatchSiftDataSYCL(sycl::queue &queue, SiftPoint *first,
                       SiftPoint *second, int first_count,
                       int second_count) {
  constexpr int tile_size = 16;

  queue.submit([&](sycl::handler &command_group) {
    sycl::local_accessor<float, 1> second_tile(tile_size * 128,
                                               command_group);

    command_group.parallel_for(
        sycl::nd_range<1>(
            sycl::range<1>(iDivUp(first_count, tile_size) * tile_size),
            sycl::range<1>(tile_size)),
        [=](sycl::nd_item<1> item) {
          const int lane = static_cast<int>(item.get_local_id(0));
          const int first_index =
              static_cast<int>(item.get_group(0)) * tile_size + lane;
          float best_score = -1.0f;
          float second_score = -1.0f;
          int best_index = -1;

          for (int base = 0; base < second_count; base += tile_size) {
            const int load_index = base + lane;
            if (load_index < second_count) {
              for (int dimension = 0; dimension < 128; ++dimension) {
                second_tile[lane * 128 + dimension] =
                    second[load_index].data[dimension];
              }
            }
            item.barrier(sycl::access::fence_space::local_space);

            const int tile_count = sycl::min(tile_size, second_count - base);
            if (first_index < first_count) {
              for (int candidate = 0; candidate < tile_count; ++candidate) {
                float dot = 0.0f;
                const float *descriptor = first[first_index].data;
                const float *candidate_descriptor =
                    second_tile.get_pointer() + candidate * 128;
                for (int dimension = 0; dimension < 128; ++dimension)
                  dot += descriptor[dimension] * candidate_descriptor[dimension];

                if (dot > best_score) {
                  second_score = best_score;
                  best_score = dot;
                  best_index = base + candidate;
                } else if (dot > second_score) {
                  second_score = dot;
                }
              }
            }
            item.barrier(sycl::access::fence_space::local_space);
          }

          if (first_index < first_count) {
            first[first_index].score = best_score;
            first[first_index].match = best_index;
            first[first_index].match_xpos =
                best_index >= 0 ? second[best_index].xpos : 0.0f;
            first[first_index].match_ypos =
                best_index >= 0 ? second[best_index].ypos : 0.0f;
            first[first_index].ambiguity = second_score / (best_score + 1e-6f);
          }
        });
  });
  queue.wait();
}

} // namespace

double MatchSiftData(SiftData &first, SiftData &second) {
  if (first.numPts == 0 || second.numPts == 0)
    return 0.0;

  TimerGPU timer;
  auto &queue = GetSyclQueue();
  MatchSiftDataSYCL(queue, first.d_data, second.d_data, first.numPts,
                    second.numPts);

  if (first.h_data) {
    queue.memcpy(first.h_data, first.d_data,
                 sizeof(SiftPoint) * first.numPts)
        .wait();
  }

  const double elapsed_ms = timer.read();
  std::printf("MatchSiftData time =          %.2f ms\n", elapsed_ms);
  return elapsed_ms;
}
