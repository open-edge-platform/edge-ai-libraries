// SPDX-License-Identifier: Apache-2.0
// Copyright (C) 2025 Intel Corporation

#include "orb_extractor.h"
#include "../src/TestUtil.h"
#include "opencv2/core/base.hpp"
#include "gtest/gtest.h"
#include <unistd.h>
#include <fstream>
#include <memory>

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <opencv2/opencv.hpp>
#include <iostream>
#include <random>

using namespace cv;

using namespace std;

constexpr uint32_t max_num_keypts_ = 2000;
constexpr int num_levels_ = 1;
constexpr int ini_fast_thr_ = 20;
constexpr int min_fast_thr_ = 7;
constexpr float scale_factor_ = 1.1f;

// Function to generate a random integer within a range
int randomInt(int min, int max) {
    static std::random_device rd;
    static std::mt19937 gen(rd());
    std::uniform_int_distribution<int> distribution(min, max);
    return distribution(gen);
}

bool compareKeyPointsDescriptor(vector<cv::KeyPoint> &left_keypts, std::vector<cv::KeyPoint> &right_keypts, uchar *left, uchar *right)
{
    int desc_size = 32;
    for( int i =0; i < left_keypts.size(); i++)
    {
        cv::KeyPoint expectedResult = left_keypts[i];
        auto it = std::find_if(right_keypts.begin(), right_keypts.end(),
                [&expectedResult](const cv::KeyPoint& element)
                {
                return ((element.pt.x == expectedResult.pt.x) &&
                        (element.pt.y == expectedResult.pt.y));
                });
        if (it != right_keypts.end())
        {
            int right_index = std::distance(right_keypts.begin(), it);
            int desc_col = i*32;
            int n = 0;
            for(int j = desc_col; j < desc_size + desc_col; j++)
            {
                if(left[j] != right[right_index*32 + n])
                {
                    std::cout << "\n i=" << i << " right=" << right_index << "\n";
                    std::cout << "\n keypoint:" << i << " decriptor is not matching";
                    std::cout << "\n descriptor:" << j << " expected=" << left[j] << " actual=" << right[right_index*32 + j];
                    std::cout << "\n left_keypoint_x:" << left_keypts[i].pt.x << " left_keypoint_y:" << left_keypts[i].pt.y;
                    std::cout << "\n right_keypoint_x:" << right_keypts[right_index].pt.x << " right_keypoint_y:" << right_keypts[right_index].pt.y << "\n";
                    return false;
                }
                n++;
            }
        }
        else
        {
            std::cout << "left keypts " << i << " is missing in right keypts\n";
            return false;
        }
    }
    return true;
}


extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    try {
            if (size < sizeof(int))
            {
               return 0;
            }

            //Extract integers from data
            int numIntegers = size / sizeof(int);
            const int *integers = reinterpret_cast<const int*>(data);

            for (int i = 0; i < numIntegers; ++i)
            {
                if ((integers[i] < 5000) && (integers[i] > 1 ))
                {
                     //std::cout << "Valid Integer: " << integers[i] << std::endl;

                     //Image size
                     int width = 848;
                     int height = 480;

                     //Create a blank image
                     Mat src(height, width, CV_8UC1, Scalar(255, 255, 255)); // White background (BGR)

                     //Number of objects to generate
                     int num_objects = integers[i];

                     //Generate random objects (rectangles in this case)
                     for (int i = 0; i < num_objects; ++i)
                     {
                         // Random rectangle parameters
                         int rect_width = randomInt(20, 200);
                         int rect_height = randomInt(20, 200);
                         int rect_x = randomInt(0, width - rect_width);
                         int rect_y = randomInt(0, height - rect_height);

                         // Random color for each rectangle
                         Scalar color(randomInt(0, 255), randomInt(0, 255), randomInt(0, 255)); // BGR color

                         // Draw the rectangle
                         rectangle(src, Point(rect_x, rect_y), Point(rect_x + rect_width, rect_y + rect_height), color, 2);
                     }

                     //Save the image to disk
                     //imwrite("random_objects_image.jpg", src);

                     // Display the image (optional)
                     //imshow("Random Objects Image", src);
                     //waitKey(0);

                     std::vector<cv::Mat> stereo_images;
                     stereo_images.resize(2);

                     stereo_images[0] = src;
                     stereo_images[1] = src;

                     std::vector<std::vector<cv::KeyPoint>> keypts;
                     keypts.resize(2);

                     std::vector<cv::Mat> stereo_descriptors;

                     const cv::_InputArray in_image_array(stereo_images);
                     const cv::_InputArray in_image_mask_array;
                     const cv::_OutputArray descriptor_array(stereo_descriptors);

                     std::vector<std::vector<float>> mask_rect;

                     constexpr int no_of_camera = 2;
                     auto extractor = std::make_shared<orb_extractor>(max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, no_of_camera, mask_rect);
                     extractor->set_gpu_kernel_path(ORBLZE_KERNEL_PATH_STRING);

                     extractor->extract(in_image_array, in_image_mask_array, keypts, descriptor_array);

                     std::vector<cv::KeyPoint> left_keypts =  keypts.at(0);
                     std::vector<cv::KeyPoint> right_keypts = keypts.at(1);

                     //Comapre keypoints size left image and right image
                     //std::cout << "\nLeft keypoints size=" << left_keypts.size() << " Right keypoints size= " << right_keypts.size() << "\n";
                     if( left_keypts.size() != right_keypts.size())
                     {
                         throw std::invalid_argument( "left image and right image KeyPoints are not same" );
                     }
                     if(!(compareKeyPointsDescriptor(left_keypts, right_keypts, stereo_descriptors.at(0).data, stereo_descriptors.at(0).data)))
                     {
                         throw std::invalid_argument( "left image and right image KeyPoints Descriptor are not same" );
                     }
                     break;
                }
           }

       } catch (std::exception& e) {
          cout << "Exception occured in StereoTest:" << e.what() << endl;
          exit(1);
    }
    return 0;
}
