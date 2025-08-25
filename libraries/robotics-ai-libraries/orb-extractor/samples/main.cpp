// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation
#include "orb_extractor.h"
#include "cmd_parser.h"
#include <opencv2/opencv.hpp>
#include <opencv2/features2d.hpp>
#include <opencv2/highgui/highgui.hpp>
#include <fstream>
#include <chrono>
#include <memory>
#include <thread>

using namespace std;

constexpr uint32_t max_num_keypts_ = 2000;
constexpr int num_levels_ = 8;
constexpr int ini_fast_thr_ = 20;
constexpr int min_fast_thr_ = 7;
constexpr float scale_factor_ = 1.2f;

struct All_Images
{
    std::string image_title;
    cv::Mat img;
};

std::vector<All_Images> gl_images;

inline double getTimeStamp()
{
    std::chrono::system_clock::duration d = std::chrono::system_clock::now().time_since_epoch();
    std::chrono::seconds s = std::chrono::duration_cast<std::chrono::seconds>(d);
    return s.count() + (std::chrono::duration_cast<std::chrono::microseconds>(d - s).count()) / 1e6;
}

void extract(int num_cam, const std::string& image_path, const std::string& thread_name, int iterations)
{
    int num_of_cameras = num_cam;
    std::vector<cv::Mat> all_images;
    all_images.resize(num_of_cameras);
    for(int i = 0; i < num_of_cameras; i++)
    {
       all_images[i] = cv::imread(image_path, cv::IMREAD_GRAYSCALE);
    }

    std::vector<std::vector<KeyType>> keypts(num_of_cameras);
    std::vector<MatType> all_descriptors(num_of_cameras);

#ifdef OPENCV_FREE
    Mat2d *images = new Mat2d[num_of_cameras];
    std::vector<MatType> in_image_array;
    for( int i = 0; i < num_of_cameras; i++)
    {
        images[i] = Mat2d(all_images[i].rows, all_images[i].cols, all_images[i].data);
        in_image_array.push_back(images[i]);
    }
    std::vector<MatType> in_image_mask_array;
    std::vector<MatType> descriptor_array;
#else
    const cv::_InputArray in_image_array(all_images);
    const cv::_InputArray in_image_mask_array;
    const cv::_OutputArray descriptor_array(all_descriptors);
#endif

    std::vector<std::vector<float>> mask_rect;

    std::string thread_id = thread_name;

    try
    {
        auto extractor = std::make_shared<orb_extractor>(max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, num_of_cameras, mask_rect);
        extractor->set_gpu_kernel_path(ORBLZE_KERNEL_PATH_STRING);

        //warm up GPU
        extractor->extract(in_image_array, in_image_mask_array, keypts, descriptor_array);

        double total_host_time = 0.0;

        for (int i = 0; i < iterations; i++)
        {
            std::cout << "iteration " << i+1 <<"/" << iterations << "\r";
            std::cout.flush();
            double host_start = getTimeStamp();
            //extractor->set_max_keypoints_gpu_buffer_size(50000,50000);
            extractor->extract(in_image_array, in_image_mask_array, keypts, descriptor_array);

            double host_end = getTimeStamp();
            double host_time_diff = (host_end - host_start)/(float)iterations;
            total_host_time += host_time_diff;
        }

        std::cout << "\n" << thread_id << ": gpu host time=" << total_host_time*1000.0 << std::endl;
    }
    catch(const std::exception& e)
    {
        std::cout << "\n Exception caught:" << e.what();
        exit(1);
    }
    std::vector<std::vector<cv::KeyPoint>> all_keypts(num_of_cameras);

#ifdef OPENCV_FREE
    for(int i=0; i < num_of_cameras; i++)
    {
        auto& gpu_keypts = keypts.at(i);
        for (int pt=0; pt < gpu_keypts.size(); pt++)
        {
            all_keypts[i].emplace_back(cv::KeyPoint(gpu_keypts[pt].x, gpu_keypts[pt].y,
                        gpu_keypts[pt].size, gpu_keypts[pt].angle, gpu_keypts[pt].response,
                        gpu_keypts[pt].octave, -1));
        }
    }
#else
    for(int i=0; i < num_of_cameras; i++)
    {
        all_keypts.at(i) = keypts.at(i);
    }
#endif

    std::vector<cv::Mat> out;
    out.resize(num_of_cameras);

    thread_id  =  thread_id + "_and_";

    for( int i = 0; i < num_of_cameras; i++)
    {
        out.at(i).create(all_images.at(i).rows, all_images.at(i).cols, CV_8U);
        cv::drawKeypoints(all_images.at(i), all_keypts[i], out[i], cv::Scalar(255,0,0));
        char no[20];
        sprintf(no,"Img:%d",i+1);
        All_Images obj;
        obj.image_title = thread_id + no;
        obj.img = out[i];
        gl_images.push_back(obj);
    }
}

int main(int argc, char** argv)
{
   if(!ParseCommandLine(argc, argv))
   {
       return 0;
   }

   const int num_images = FLAGS_images;
   const int num_of_threads = FLAGS_threads;
   const int num_of_iter = FLAGS_iterations;
   std::string image_path = FLAGS_image_path;

   std::vector<std::thread> threads;

    for (int i = 0; i < num_of_threads; ++i)
    {
        std::string thread_name = "Thread:" + std::to_string(i + 1);
        threads.emplace_back(extract, num_images, image_path.c_str(), thread_name, num_of_iter);
    }
    for (auto& thread : threads)
        thread.join();

    //show the images
    for (int i = 0; i < (num_images * num_of_threads); i++)
    {
        cv::imshow(gl_images[i].image_title, gl_images[i].img);
    }
    cv::waitKey(0);

    return 0;
}
