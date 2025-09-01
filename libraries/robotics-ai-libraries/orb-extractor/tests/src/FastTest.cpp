// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include "orb_extractor.h"
#include "gpu/gpu_kernels.h"
#include "gpu/kernel_base.h"
#include "gpu/device_image.h"
#include "TestUtil.h"
#include "opencv2/core/base.hpp"
#include "gtest/gtest.h"
#include <unistd.h>

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/highgui.hpp>

#define EDGE_THRESHOLD 19
#define OVERLAP 6
#define WIDTHBLOCK 32

using namespace cv;


template<typename pt>
struct cmp_pt
{
    bool operator()(const pt&a, const pt&b) const
    {
        return a.pt.y < b.pt.y || (a.pt.y == b.pt.y && a.pt.x < b.pt.x);
    }
};

void cpuFastExt(std::vector<cv::Mat>& input, std::vector<std::vector<cv::KeyPoint>>& raw_keypts, int num_levels, int ini_fast_thr_, int min_fast_thr_)
{
    const int max_num_keypts_ = 35000;
    const float cell_size = WIDTHBLOCK;
    const int overlap = OVERLAP;

    raw_keypts.resize(num_levels);

    for (unsigned int level = 0; level < num_levels ; ++level) {

        constexpr unsigned int min_border_x = EDGE_THRESHOLD;
        constexpr unsigned int min_border_y = EDGE_THRESHOLD;
        const unsigned int max_border_x = input.at(level).cols - EDGE_THRESHOLD;
        const unsigned int max_border_y = input.at(level).rows - EDGE_THRESHOLD;

        const unsigned int width = max_border_x - min_border_x;
        const unsigned int height = max_border_y - min_border_y;

        const unsigned int num_cols = std::ceil(width / cell_size) + 1;
        const unsigned int num_rows = std::ceil(height / cell_size) + 1;

        std::vector<cv::KeyPoint> & keypts_to_distribute = raw_keypts.at(level);
        keypts_to_distribute.reserve(max_num_keypts_ * 10);

        for (unsigned int i = 0; i < num_rows; ++i) {
            const unsigned int min_y = min_border_y + i * cell_size;
            if (max_border_y - overlap <= min_y) {
                continue;
            }
            unsigned int max_y = min_y + cell_size + overlap;
            if (max_border_y < max_y) {
                max_y = max_border_y;
            }
            for (unsigned int j = 0; j < num_cols; ++j) {
                const unsigned int min_x = min_border_x + j * cell_size;
                if (max_border_x - overlap <= min_x) {
                    continue;
                }
                unsigned int max_x = min_x + cell_size + overlap;
                if (max_border_x < max_x) {
                    max_x = max_border_x;
                }
                std::vector<cv::KeyPoint> keypts_in_cell;

                cv::FAST(input.at(level).rowRange(min_y, max_y).colRange(min_x, max_x),
                        keypts_in_cell, ini_fast_thr_, false);

                // Re-compute FAST keypoint with reduced threshold if enough keypoint was not got
                if (keypts_in_cell.empty()) {
                    cv::FAST(input.at(level).rowRange(min_y, max_y).colRange(min_x, max_x),
                            keypts_in_cell, min_fast_thr_, false);
                }
                if (keypts_in_cell.empty()) {
                    continue;
                }

                // Collect keypoints for every scale
                {
                    for (auto& keypt : keypts_in_cell) {
                        keypt.pt.x += j * cell_size;
                        keypt.pt.y += i * cell_size;
                        keypts_to_distribute.push_back(keypt);
                    }
                }
            }
        }
        std::sort(keypts_to_distribute.begin(), keypts_to_distribute.end(), cmp_pt<cv::KeyPoint>());
    }
}

bool compareKeyPoints(vector<cv::KeyPoint> &cpuKeypts, std::vector<gpu::PartKey> &gpuKeypts)
{
    if( cpuKeypts.size() != gpuKeypts.size())
    {
        std::cout <<"\n gpukeypts and cpukeypts are not same size\n";
        return false;
    }

    for( int i =0; i < gpuKeypts.size(); i++)
    {
        if(cpuKeypts[i].pt.x != gpuKeypts[i].pt.x && cpuKeypts[i].pt.y != gpuKeypts[i].pt.y)
        {
            std::cout <<"\n gpukeypts and cpukeypts are not matching\n" << i << "\n";
            return false;
        }
    }
    return true;
}

void PartkeyToCVkey(std::vector<gpu::PartKey> &in_gpuKeypts, vector<cv::KeyPoint> &out_cvKeypts)
{
    for(int i = 0; i < in_gpuKeypts.size(); i++)
    {
        out_cvKeypts[i].pt.x = in_gpuKeypts[i].pt.x;
        out_cvKeypts[i].pt.y = in_gpuKeypts[i].pt.y;
    }
}


void fastTest()
{
    const auto width = 1920;
    const auto height = 1280;

    int total_level = 1;
    float scale_factor = 1.2;
    unsigned int num_levels = 8;
    unsigned int ini_fast_thr = 20;
    unsigned int min_fast_thr = 7;

    static constexpr unsigned int orb_patch_radius = 19;
    static constexpr unsigned int orb_overlap_size = 6;
    static constexpr unsigned int orb_cell_size = 32;

    static constexpr unsigned int min_border_x = orb_patch_radius;
    static constexpr unsigned int min_border_y = orb_patch_radius;

    std::vector<cv::Mat> src(1);
    cv::Mat src2;
    cv::Size sz(width, height);

    src2 = cv::imread(DATAPATH+"/market.jpg", IMREAD_GRAYSCALE);
    cv::resize(src2, src.at(0), std::move(sz), cv::INTER_LINEAR);

    auto orbKernel = std::make_shared<gpu::ORBKernel>();
    auto device_base = orbKernel->getDeviceBase();

    orbKernel->setKernelPath(ORBLZE_KERNEL_PATH_STRING);

    gpu::Image8u srcImg;
    srcImg.setDeviceBase(device_base);
    srcImg.resize(src.at(0).cols, src.at(0).rows);
    srcImg.upload(src.at(0).data, gpu::kImmediate);

    gpu::Vec8u srcBuf;
    srcBuf.setDeviceBase(device_base);
    srcBuf.resize(src.at(0).cols, src.at(0).rows);
    srcBuf.upload(src.at(0).data, gpu::kImmediate);

    //partkey
    std::vector<gpu::PartKey> gpuKeypts;
    gpu::Vec8u gpu_mask_buffer;
    gpu_mask_buffer.setDeviceBase(device_base);
    bool mask_check = false;

    size_t max_nms_buf_size = 327680;
    size_t max_fast_buf_size = 458752;

    orbKernel->fastExt( srcImg,
                  srcBuf,
                  gpuKeypts,
                  gpu_mask_buffer,
                  scale_factor,
                  mask_check,
                  gpu_mask_buffer.width(),
                  ini_fast_thr,
                  min_fast_thr,
                  orb_patch_radius,
                  orb_overlap_size,
                  orb_cell_size,
                  1,
                  max_nms_buf_size,
                  max_fast_buf_size,
                  false
                );
    orbKernel->execute(gpu::kCmdList0);

    for (auto& keypt : gpuKeypts)
    {
        keypt.pt.x -= min_border_x;
        keypt.pt.y -= min_border_y;
    }
    //sort gpuKeypts
    std::sort(gpuKeypts.begin(), gpuKeypts.end(), cmp_pt<gpu::PartKey>());

    int gpuKeypntSize = gpuKeypts.size();

    vector<vector<cv::KeyPoint>> cpuKeypts;

    //call cpufastExt
    cpuFastExt(src, cpuKeypts, total_level, ini_fast_thr, min_fast_thr);
    int cpu_KeypntSize = cpuKeypts[0].size();

    //compare GPU and CPU result
    ASSERT_TRUE(compareKeyPoints(cpuKeypts[0], gpuKeypts));
}

TEST(FastTest, Positive)
{
    fastTest();
}

