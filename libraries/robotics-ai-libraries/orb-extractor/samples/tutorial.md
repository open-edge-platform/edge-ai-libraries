# ORB Extarctor library
### In this tutorial we will learn how to use ORB Extratctor library API for getting keypoints and descriptors of image.
```
ORB Library provide mono and stereo support API
```
# The code - mono
create file sample.cpp with following code: 
```
#include "orb_extractor.h"
#include <opencv2/opencv.hpp>
#include <opencv2/features2d.hpp>
#include <fstream>
#include <chrono>
#include <memory>

int main()
{   
    cv::Mat cv_image = cv::imread("../../images/market.jpg", cv::IMREAD_GRAYSCALE);
    std::vector<std::vector<cv::KeyPoint>> all_keypts;
    all_keypts.resize(1);
    cv::Mat descriptor;

    const cv::_InputArray in_image_array(cv_image);
    const cv::_InputArray in_image_mask_array;
    const cv::_OutputArray descriptor_array(descriptor);

    std::vector<std::vector<float>> mask_rect;
    
    auto extractor = std::make_shared<orb_extractor>(max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, mask_rect);
    extractor->set_gpu_kernel_path("../../build");
    
    extractor->extract(in_image_array, in_image_mask_array, all_keypts, descriptor_array);
    auto& keypts = all_keypts.at(0);
    cv::Mat out (cv_image.rows, cv_image.cols, CV_8U);;
    cv::drawKeypoints(cv_image, keypts, out, cv::Scalar(255,0,0));
    cv::imshow("result", out);
    cv::waitKey(0);
}
```
# Mono code explanation

Configuration for getting keypoints and descriptors: 
```
  constexpr uint32_t max_num_keypts_ = 2000;
  constexpr int num_levels_ = 8;
  constexpr int ini_fast_thr_ = 20;
  constexpr int min_fast_thr_ = 7;
  constexpr float scale_factor_ = 1.2f;
```
Initialize the input and output parameters:
```
  cv::Mat cv_image = cv::imread("../../images/market.jpg", cv::IMREAD_GRAYSCALE);
  std::vector<std::vector<cv::KeyPoint>> all_keypts; 
  all_keypts.resize(1);
  cv::Mat descriptor;
  const cv::_InputArray in_image_array(cv_image);
  const cv::_InputArray in_image_mask_array;
  const cv::_OutputArray descriptor_array(descriptor);
  std::vector<std::vector<float>> mask_rect;
```
Create orb_extract object:
```
auto extractor = std::make_shared<orb_extractor>(max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, mask_rect)
```
Set gpu kernel path:
In this path have to provide orb extratctor gpu kerenl libraries.

To build this gpu kernel libraries please follow the README.md.

After build this gpu kernels provide this gpu kernel path to "set(gpu_kernel_path()" function.
```
extractor->set_gpu_kernel_path("../../build");
```
Call orb extract mono API:
```
extractor->extract(in_image_array, in_image_mask_array, keypts, descriptor_array);
```
Draw the keypoint on the image:
```
 cv::Mat out (cv_image.rows, cv_image.cols, CV_8U);;
 cv::drawKeypoints(cv_image, keypts, out, cv::Scalar(255,0,0));
 cv::imshow("result", out);
 cv::waitKey(0);
```    
# The code - stereo:
create file sample.cpp with following code
```
int main()
{
    std::vector<cv::Mat> stereo_images;
    stereo_images.resize(2); //left and right image 
    stereo_images[0] = cv::imread("../../images/market.jpg", cv::IMREAD_GRAYSCALE);
    stereo_images[1] = cv::imread("../../images/market.jpg", cv::IMREAD_GRAYSCALE);
    std::vector<std::vector<cv::KeyPoint>> keypts;
    keypts.resize(2); //for left and right image keypoint
    std::vector<cv::Mat> stereo_descriptors;
    stereo_descriptors.resize(2);

    const cv::_InputArray in_image_array(stereo_images);
    const cv::_InputArray in_image_mask_array;
    const cv::_OutputArray descriptor_array(stereo_descriptors);

    std::vector<std::vector<float>> mask_rect;

    auto extractor = std::make_shared<orb_extractor>(max_num_keypts_, scale_factor_, num_levels_, ini_fast_thr_, min_fast_thr_, mask_rect);
    extractor->set_gpu_kernel_path("../../build");

    double total_host_time = 0.0;

    for (int i = 0; i < iterations; i++)
    {
        std::cout << "iteration " << i <<"/" << iterations << "\r";
        std::cout.flush();
        double host_start = getTimeStamp();

        extractor->extract(in_image_array, in_image_mask_array, keypts, descriptor_array);

        double host_end = getTimeStamp();
        double host_time_diff = (host_end - host_start)/(float)iterations;
        total_host_time += host_time_diff;
    }

    std::vector<cv::KeyPoint> left_keypts =  keypts.at(0);
    std::vector<cv::KeyPoint> right_keypts = keypts.at(1);
    //left image
    cv::Mat left_out (left_cv_image.rows, left_cv_image.cols, CV_8U);;
    cv::drawKeypoints(left_cv_image, left_keypts, left_out, cv::Scalar(255,0,0));
    cv::imshow("left_result", left_out);

    //right image
    cv::Mat right_out (right_cv_image.rows, right_cv_image.cols, CV_8U);;
    cv::drawKeypoints(right_cv_image, right_keypts, right_out, cv::Scalar(255,0,0));
    cv::imshow("right_result", right_out);
    cv::waitKey(0);
}
```
# Stereo code explanation 

call stereo orb extractor API:
```
extract(in_image_array, in_image_mask_array, keypts, descriptor_array);

in Stereo API all input and output parameter will be same as mono.
only Image Mat vector, keypoints vector and Mat descriptor vector need to resize 2.
```

# Compiling and running the program

outside orb library folder make sample folder:
```
make sample
cd sample
```

Add the following lines to your CMakeLists.txt file:
```
cmake_minimum_required(VERSION 3.4)

set(NAME feature_extract)
project (${NAME})

#set(OUTPUT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../bin")
#set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${OUTPUT_DIR}")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED TRUE)

add_compile_options(-Wpedantic -Werror)

find_package(OpenCV REQUIRED)

set_property(TARGET PROPERTY CXX_STANDARD 11)
add_executable(${NAME} sample.cpp)

include_directories (
   ${CMAKE_CURRENT_LIST_DIR}/../include
)

target_link_libraries(${NAME} "${CMAKE_CURRENT_LIST_DIR}/../build/libgpu_orb.so" ${OpenCV_LIBS})

set_property(TARGET ${NAME} PROPERTY INSTALL_RPATH_USE_LINK_PATH TRUE)
```

Build the code:
```
cd sample 
cmake ../
make -j 
```
After you have made the executable, you can run it. Simply do:

```
$ ./extract_feature
```

After executing this will see keypoints blue color dots on the image

